"""
技术面筛选引擎：可配置形态规则，不填则用默认。

默认目标：全市场初筛（OR / 命中≥1）压到约数百～一千只，再可二次 AND 精筛。
"""

from __future__ import annotations

import json
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime

import pandas as pd

from modules.stocks.market_data import list_a_shares, get_daily_bars, is_tradable_a_share
from modules.stocks.ta import add_indicators

# ---- 默认可配置规则（用户不传 conditions 时启用 enabled=true 的项）----
DEFAULT_PATTERN_RULES = [
    {
        'key': 'ma_all_rising',
        'label': '多周期均线全部朝上',
        'enabled': True,
        'params': {'periods': [5, 10, 20, 30, 60, 250], 'slope_days': 3},
        'desc': 'MA5/10/20/30/60/年线均高于N个交易日前',
    },
    {
        'key': 'recent_limit_up',
        'label': '近1个月有涨停',
        'enabled': True,
        'params': {'lookback': 22},
        'desc': '近N个交易日出现过涨停（自动区分5%/10%/20%）',
    },
    {
        'key': 'macd_golden_cross',
        'label': 'MACD金叉',
        'enabled': False,
        'params': {},
        'desc': '昨日 DIF≤DEA，今日 DIF>DEA',
    },
    {
        'key': 'ma_bullish',
        'label': '均线多头排列',
        'enabled': False,
        'params': {'fast': 5, 'mid': 10, 'slow': 20},
        'desc': 'MA快 > MA中 > MA慢',
    },
    {
        'key': 'volume_increase',
        'label': '成交量放大',
        'enabled': False,
        'params': {'ratio': 1.5, 'base': 5},
        'desc': '今日量 > 近N日均量 × 倍数',
    },
    {
        'key': 'breakthrough',
        'label': '突破平台',
        'enabled': False,
        'params': {'lookback': 20},
        'desc': '收盘创近 N 日新高',
    },
    {
        'key': 'rsi_low',
        'label': 'RSI低位',
        'enabled': False,
        'params': {'period': 6, 'threshold': 30},
        'desc': 'RSI 低于阈值（超卖区）',
    },
    {
        'key': 'boll_lower',
        'label': '触及布林下轨',
        'enabled': False,
        'params': {},
        'desc': '收盘 ≤ 布林下轨',
    },
    {
        'key': 'pullback_support',
        'label': '回踩支撑',
        'enabled': False,
        'params': {'ma': 20, 'tol': 0.02},
        'desc': '价格回踩均线附近且未有效跌破',
    },
    {
        'key': 'kdj_golden_cross',
        'label': 'KDJ金叉',
        'enabled': False,
        'params': {},
        'desc': '昨日 K≤D，今日 K>D',
    },
]

# 前端勾选中文 → key
LABEL_TO_KEY = {r['label']: r['key'] for r in DEFAULT_PATTERN_RULES}
# 兼容旧前端短标签
LABEL_TO_KEY.update({
    '均线多头': 'ma_bullish',
    '布林下轨': 'boll_lower',
    '回踩支撑': 'pullback_support',
})


def list_default_rules():
    return deepcopy(DEFAULT_PATTERN_RULES)


def resolve_rules(conditions=None, rules=None):
    """
    解析用户输入：
    - rules: 完整规则列表（带 enabled/params）优先
    - conditions: ['MACD金叉', 'macd_golden_cross', ...] 勾选列表
    - 都空：用默认 enabled=true 的规则
    """
    if rules and isinstance(rules, list) and len(rules) > 0:
        base = {r['key']: deepcopy(r) for r in DEFAULT_PATTERN_RULES}
        out = []
        for r in rules:
            key = r.get('key') or LABEL_TO_KEY.get(r.get('label', ''), '')
            if not key:
                continue
            item = deepcopy(base.get(key, {
                'key': key, 'label': r.get('label') or key, 'params': {}, 'enabled': True,
            }))
            item['enabled'] = bool(r.get('enabled', True))
            if isinstance(r.get('params'), dict):
                item['params'] = {**item.get('params', {}), **r['params']}
            if r.get('label'):
                item['label'] = r['label']
            out.append(item)
        enabled = [x for x in out if x.get('enabled')]
        return enabled or [x for x in DEFAULT_PATTERN_RULES if x.get('enabled')]

    if conditions:
        keys = []
        for c in conditions:
            if isinstance(c, dict):
                keys.append(c.get('key') or LABEL_TO_KEY.get(c.get('label', ''), ''))
            else:
                s = str(c)
                keys.append(LABEL_TO_KEY.get(s, s if s in {r['key'] for r in DEFAULT_PATTERN_RULES} else ''))
        keys = [k for k in keys if k]
        base = {r['key']: deepcopy(r) for r in DEFAULT_PATTERN_RULES}
        out = []
        for k in keys:
            if k in base:
                item = base[k]
                item['enabled'] = True
                out.append(item)
        if out:
            return out

    return [deepcopy(r) for r in DEFAULT_PATTERN_RULES if r.get('enabled')]


# 文字策略 → 筛选规则：关键词命中即启用对应技术条件
_STRATEGY_TEXT_ALIASES = [
    ('ma_all_rising', (
        '多周期均线', '全部朝上', '均线全部朝上', '均线朝上', '年线朝上',
        'ma全部朝上', '多均线向上',
    )),
    ('recent_limit_up', (
        '涨停', '近1个月有涨停', '近一个月涨停', '近期涨停', '有过涨停',
    )),
    ('macd_golden_cross', (
        'macd金叉', 'macd 金叉', 'macd金', 'dif上穿', 'macd上穿',
    )),
    ('ma_bullish', (
        '均线多头', '多头排列', 'ma多头', '均线多头排列',
    )),
    ('volume_increase', (
        '成交量放大', '放量', '量能放大', '倍量', '量比放大',
    )),
    ('breakthrough', (
        '突破平台', '突破新高', '创近', '突破高点', '向上突破', '突破',
    )),
    ('rsi_low', (
        'rsi低位', 'rsi超卖', 'rsi偏低', '超卖', 'rsi低',
    )),
    ('boll_lower', (
        '布林下轨', '触及下轨', '布林带下轨', 'boll下轨', '下轨支撑',
    )),
    ('kdj_golden_cross', (
        'kdj金叉', 'kdj 金叉', 'k上穿d', 'kdj金',
    )),
    ('pullback_support', (
        '回踩支撑', '回踩均线', '回踩', '支撑位', '不破支撑',
    )),
]


def _extract_number(text: str, patterns, default=None):
    import re
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            try:
                return float(m.group(1))
            except Exception:
                continue
    return default


def parse_strategy_text(text: str) -> dict:
    """
    把用户白话策略解析成可执行筛选配置。
    返回: {text, match_mode, min_hits, rules, matched_labels, unmatched_hint}
    """
    raw = (text or '').strip()
    lowered = raw.lower()
    # 匹配模式
    match_mode = 'and'
    min_hits = 1
    if any(k in raw for k in ('命中任一', '满足任一', '或者', '任意一条', '初筛')) or ' or ' in f' {lowered} ':
        match_mode = 'or'
    if any(k in raw for k in ('至少', '不少于')):
        match_mode = 'min'
        n = _extract_number(raw, [r'至少\s*(\d+)', r'不少于\s*(\d+)'], default=2)
        min_hits = max(1, int(n or 2))
    if any(k in raw for k in ('全部命中', '全部满足', '同时满足', '且全部', '精筛')):
        match_mode = 'and'

    matched_keys = []
    for key, aliases in _STRATEGY_TEXT_ALIASES:
        if any(a.lower() in lowered or a in raw for a in aliases):
            matched_keys.append(key)

    # 去重保持顺序
    seen = set()
    ordered_keys = []
    for k in matched_keys:
        if k not in seen:
            seen.add(k)
            ordered_keys.append(k)

    base = {r['key']: deepcopy(r) for r in DEFAULT_PATTERN_RULES}
    rules = []
    for key in ordered_keys:
        item = deepcopy(base[key])
        item['enabled'] = True
        params = dict(item.get('params') or {})
        # 从文字里捞一点常见参数
        if key == 'volume_increase':
            ratio = _extract_number(raw, [r'(\d+(?:\.\d+)?)\s*倍'], default=None)
            if ratio:
                params['ratio'] = ratio
            base_n = _extract_number(raw, [r'近\s*(\d+)\s*日均量', r'(\d+)\s*日均量'], default=None)
            if base_n:
                params['base'] = int(base_n)
        elif key == 'breakthrough':
            lookback = _extract_number(raw, [
                r'近\s*(\d+)\s*日高点', r'近\s*(\d+)\s*日新高', r'近\s*(\d+)\s*日平台',
                r'(\d+)\s*日高点', r'(\d+)\s*日平台', r'突破近\s*(\d+)\s*日',
            ], default=None)
            if lookback:
                params['lookback'] = int(lookback)
        elif key == 'recent_limit_up':
            lookback = _extract_number(raw, [
                r'近\s*(\d+)\s*个交易日', r'近\s*(\d+)\s*日有涨停', r'近\s*(\d+)\s*天有涨停',
                r'(\d+)\s*个交易日',
            ], default=None)
            if lookback:
                params['lookback'] = int(lookback)
        elif key == 'rsi_low':
            thr = _extract_number(raw, [r'低于\s*(\d+)', r'RSI\s*[<>＜＞]\s*(\d+)', r'rsi.*?(\d+)'], default=None)
            if thr and thr <= 50:
                params['threshold'] = thr
        elif key == 'pullback_support':
            ma_n = _extract_number(raw, [r'MA\s*(\d+)', r'ma\s*(\d+)', r'(\d+)\s*日均线'], default=None)
            if ma_n:
                params['ma'] = int(ma_n)
        elif key == 'ma_all_rising':
            slope = _extract_number(raw, [r'(\d+)\s*个?交易日前', r'高于\s*(\d+)\s*日前'], default=None)
            if slope:
                params['slope_days'] = int(slope)
        item['params'] = params
        rules.append(item)

    unmatched_hint = ''
    if not rules:
        unmatched_hint = (
            '未识别到可用技术条件。可写：均线多头、放量、突破、涨停、MACD金叉、'
            'KDJ金叉、RSI低位、布林下轨、回踩支撑、多周期均线朝上 等关键词。'
        )

    return {
        'text': raw,
        'match_mode': match_mode,
        'min_hits': min_hits,
        'rules': rules,
        'matched_labels': [r['label'] for r in rules],
        'unmatched_hint': unmatched_hint,
    }


def build_strategy_payload(text: str, status: str = 'active') -> dict:
    """保存策略时统一结构：原文 + 解析出的可执行规则。"""
    parsed = parse_strategy_text(text)
    return {
        'text': parsed['text'],
        'match_mode': parsed['match_mode'],
        'min_hits': parsed['min_hits'],
        'rules': parsed['rules'],
        'matched_labels': parsed['matched_labels'],
        'unmatched_hint': parsed['unmatched_hint'],
        'status_hint': status,
    }


def strategy_from_row(row: dict) -> dict:
    """把数据库行补上可执行筛选字段，兼容旧纯文本/JSON。"""
    item = dict(row or {})
    raw = item.get('rules_json') or ''
    text = ''
    parsed = None
    if isinstance(raw, str) and raw.strip():
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict) and (obj.get('rules') or obj.get('text') is not None):
                text = obj.get('text') or ''
                if obj.get('rules'):
                    parsed = {
                        'text': text,
                        'match_mode': obj.get('match_mode') or 'and',
                        'min_hits': int(obj.get('min_hits') or 1),
                        'rules': obj.get('rules') or [],
                        'matched_labels': obj.get('matched_labels') or [
                            r.get('label') for r in (obj.get('rules') or []) if isinstance(r, dict)
                        ],
                        'unmatched_hint': obj.get('unmatched_hint') or '',
                    }
                elif text:
                    parsed = parse_strategy_text(text)
            elif isinstance(obj, str):
                text = obj
        except Exception:
            text = raw
            parsed = parse_strategy_text(raw)
    if parsed is None:
        if not text:
            text = raw if isinstance(raw, str) else ''
        parsed = parse_strategy_text(text)
    item['rules_text'] = parsed.get('text') or text
    item['screen_rules'] = parsed.get('rules') or []
    item['screen_match_mode'] = parsed.get('match_mode') or 'and'
    item['screen_min_hits'] = int(parsed.get('min_hits') or 1)
    item['matched_labels'] = parsed.get('matched_labels') or []
    item['unmatched_hint'] = parsed.get('unmatched_hint') or ''
    return item


def _hit_macd_golden(df, params):
    if len(df) < 2 or 'DIF' not in df.columns:
        return False
    a, b = df.iloc[-2], df.iloc[-1]
    return float(a['DIF']) <= float(a['DEA']) and float(b['DIF']) > float(b['DEA'])


def _hit_ma_bullish(df, params):
    fast = int(params.get('fast', 5))
    mid = int(params.get('mid', 10))
    slow = int(params.get('slow', 20))
    cols = [f'MA{fast}', f'MA{mid}', f'MA{slow}']
    if any(c not in df.columns for c in cols):
        return False
    row = df.iloc[-1]
    vals = [row[c] for c in cols]
    if any(pd.isna(v) for v in vals):
        return False
    return float(vals[0]) > float(vals[1]) > float(vals[2])


def _hit_volume(df, params):
    ratio = float(params.get('ratio', 1.5))
    base = int(params.get('base', 5))
    col = f'VOL_MA{base}' if f'VOL_MA{base}' in df.columns else 'VOL_MA5'
    if col not in df.columns or 'volume' not in df.columns:
        return False
    row = df.iloc[-1]
    if pd.isna(row[col]) or float(row[col]) <= 0:
        return False
    return float(row['volume']) > float(row[col]) * ratio


def _hit_breakthrough(df, params):
    lookback = int(params.get('lookback', 20))
    if len(df) < lookback + 1:
        return False
    window = df.iloc[-(lookback + 1):-1]['close']
    last = float(df.iloc[-1]['close'])
    return last >= float(window.max())


def _hit_rsi_low(df, params):
    period = int(params.get('period', 6))
    thr = float(params.get('threshold', 30))
    col = f'RSI{period}'
    if col not in df.columns:
        return False
    val = df.iloc[-1][col]
    return (not pd.isna(val)) and float(val) < thr


def _hit_boll_lower(df, params):
    if 'BOLL_LOW' not in df.columns:
        return False
    row = df.iloc[-1]
    if pd.isna(row['BOLL_LOW']):
        return False
    return float(row['close']) <= float(row['BOLL_LOW']) * 1.005


def _hit_pullback(df, params):
    ma_n = int(params.get('ma', 20))
    tol = float(params.get('tol', 0.02))
    col = f'MA{ma_n}'
    if col not in df.columns or len(df) < 3:
        return False
    row = df.iloc[-1]
    prev = df.iloc[-2]
    ma = row[col]
    if pd.isna(ma) or float(ma) <= 0:
        return False
    close = float(row['close'])
    # 近期曾在均线上方，今日贴近均线且未大跌破
    near = abs(close - float(ma)) / float(ma) <= tol
    above_before = float(prev['close']) >= float(prev.get(col) or ma) * 0.98
    return near and above_before and close >= float(ma) * (1 - tol)


def _hit_kdj_golden(df, params):
    if len(df) < 2 or 'K' not in df.columns:
        return False
    a, b = df.iloc[-2], df.iloc[-1]
    return float(a['K']) <= float(a['D']) and float(b['K']) > float(b['D'])


def _hit_ma_all_rising(df, params):
    periods = params.get('periods') or [5, 10, 20, 30, 60, 250]
    periods = [int(n) for n in periods]
    slope_days = max(1, int(params.get('slope_days', 3)))
    if len(df) <= max(periods) + slope_days:
        return False
    now = df.iloc[-1]
    before = df.iloc[-1 - slope_days]
    for period in periods:
        col = f'MA{period}'
        if col not in df.columns or pd.isna(now[col]) or pd.isna(before[col]):
            return False
        if float(now[col]) <= float(before[col]):
            return False
    return True


def _limit_up_threshold(code, name):
    """A股常见涨停幅度；留少量撮合误差。"""
    name = str(name or '').upper()
    if 'ST' in name:
        return 4.8
    if str(code).startswith(('30', '68')):
        return 19.5
    return 9.5


def _hit_recent_limit_up(df, params):
    lookback = max(1, int(params.get('lookback', 22)))
    if len(df) < 2:
        return False
    code = params.get('_code', '')
    name = params.get('_name', '')
    threshold = float(params.get('threshold') or _limit_up_threshold(code, name))
    pct = df['close'].pct_change() * 100
    return bool((pct.tail(lookback) >= threshold).any())


RULE_FUNCS = {
    'ma_all_rising': _hit_ma_all_rising,
    'recent_limit_up': _hit_recent_limit_up,
    'macd_golden_cross': _hit_macd_golden,
    'ma_bullish': _hit_ma_bullish,
    'volume_increase': _hit_volume,
    'breakthrough': _hit_breakthrough,
    'rsi_low': _hit_rsi_low,
    'boll_lower': _hit_boll_lower,
    'pullback_support': _hit_pullback,
    'kdj_golden_cross': _hit_kdj_golden,
}


def evaluate_stock(code, name, rules, days=300, max_bar_age_days=20):
    """评估单只股票，返回命中信息（含未命中时的空 hits）或 None。

    久无日 K（疑似退市/停牌过久）直接跳过，避免筛出证券账户搜不到的票。
    """
    if not is_tradable_a_share(code, name):
        return None
    df = get_daily_bars(code, days=days)
    if df is None or len(df) < 35:
        return None
    try:
        last_dt = pd.Timestamp(df['date'].iloc[-1]).to_pydatetime()
        age = (datetime.now() - last_dt).days
        if age > int(max_bar_age_days or 20):
            return None
    except Exception:
        pass
    df = add_indicators(df)
    hits = []
    hit_keys = []
    for rule in rules:
        fn = RULE_FUNCS.get(rule['key'])
        if not fn:
            continue
        try:
            params = {**(rule.get('params') or {}), '_code': code, '_name': name}
            if fn(df, params):
                hits.append(rule.get('label') or rule['key'])
                hit_keys.append(rule['key'])
        except Exception:
            continue
    last = df.iloc[-1]
    prev = df.iloc[-2]
    close = float(last['close'])
    prev_c = float(prev['close']) or close
    return {
        'code': code,
        'name': name or '',
        'close': round(close, 2),
        'pct_chg': round((close - prev_c) / prev_c * 100, 2),
        'hits': hits,
        'hit_keys': hit_keys,
        'hit_count': len(hits),
        'ma5': round(float(last['MA5']), 2) if not pd.isna(last.get('MA5')) else None,
        'ma10': round(float(last['MA10']), 2) if not pd.isna(last.get('MA10')) else None,
        'ma20': round(float(last['MA20']), 2) if not pd.isna(last.get('MA20')) else None,
        'ma30': round(float(last['MA30']), 2) if not pd.isna(last.get('MA30')) else None,
        'ma60': round(float(last['MA60']), 2) if not pd.isna(last.get('MA60')) else None,
        'ma250': round(float(last['MA250']), 2) if not pd.isna(last.get('MA250')) else None,
        'dif': round(float(last['DIF']), 4) if not pd.isna(last.get('DIF')) else None,
        'dea': round(float(last['DEA']), 4) if not pd.isna(last.get('DEA')) else None,
    }


def run_screen(
    conditions=None,
    rules=None,
    match_mode='or',
    min_hits=1,
    max_stocks=300,
    workers=8,
    days=300,
    progress_cb=None,
):
    """
    执行筛选。
    match_mode: or = 命中任意; and = 全部命中; min = 命中数 >= min_hits
    max_stocks: 限制扫描数量（0=全部）；小于全市场时按等间隔抽样，覆盖各板块
    """
    active_rules = resolve_rules(conditions=conditions, rules=rules)
    if not active_rules:
        return {'results': [], 'rules': [], 'scanned': 0, 'message': '无启用规则'}

    universe = [
        it for it in (list_a_shares() or [])
        if is_tradable_a_share(it.get('code'), it.get('name'), it.get('price'))
    ]
    total_universe = len(universe)
    limit = int(max_stocks or 0)
    if 0 < limit < total_universe:
        # 按代码顺序截断会全是 0000xx，这里等间隔抽样保证沪深创科都覆盖
        stride = total_universe / limit
        universe = [universe[int(i * stride)] for i in range(limit)]

    results = []
    scanned = 0
    errors = 0
    no_data = 0
    rule_hits = {r['key']: 0 for r in active_rules}
    lock = __import__('threading').Lock()

    def _one(item):
        code = str(item.get('code', '')).zfill(6)
        name = item.get('name', '')
        try:
            return evaluate_stock(code, name, active_rules, days=days)
        except Exception:
            return {'__error__': True}

    workers = max(2, min(int(workers or 8), 12))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_one, it): it for it in universe}
        for fut in as_completed(futs):
            scanned += 1
            if progress_cb and (scanned % 10 == 0 or scanned == len(universe)):
                try:
                    progress_cb(scanned, len(universe))
                except Exception:
                    pass
            try:
                hit = fut.result(timeout=25)
            except Exception:
                errors += 1
                continue
            if not hit:
                no_data += 1
                continue
            if hit.get('__error__'):
                errors += 1
                continue

            for key in hit.get('hit_keys') or []:
                if key in rule_hits:
                    rule_hits[key] += 1

            hc = hit['hit_count']
            n_rules = len(active_rules)
            if match_mode == 'and':
                ok = hc >= n_rules
            elif match_mode == 'min':
                ok = hc >= int(min_hits)
            else:  # or
                ok = hc >= max(1, int(min_hits))
            if ok:
                with lock:
                    results.append(hit)

    results.sort(key=lambda x: (-x.get('hit_count', 0), -abs(x.get('pct_chg') or 0)))

    label_of = {r['key']: r.get('label') or r['key'] for r in active_rules}
    rule_stats = [
        {'key': k, 'label': label_of.get(k, k), 'hits': v}
        for k, v in rule_hits.items()
    ]
    breakdown = '、'.join(f'{s["label"]} {s["hits"]}' for s in rule_stats)

    return {
        'results': results,
        'rules': active_rules,
        'rule_stats': rule_stats,
        'scanned': scanned,
        'universe': total_universe,
        'limited_to': len(universe),
        'matched': len(results),
        'errors': errors,
        'no_data': no_data,
        'match_mode': match_mode,
        'min_hits': min_hits,
        'message': (
            f'扫描 {scanned}/{total_universe} 只（本次上限 {len(universe)}），'
            f'最终命中 {len(results)} 只；模式 {match_mode}；'
            f'各条件单独命中：{breakdown}'
            + (f'；无数据 {no_data}' if no_data else '')
            + (f'；失败 {errors}' if errors else '')
        ),
    }
