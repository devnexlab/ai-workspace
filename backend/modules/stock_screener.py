"""技术面筛选引擎：可配置形态规则，不填则用默认。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import threading

import pandas as pd

from modules.market_data import list_a_shares, get_daily_bars
from modules.stock_ta import add_indicators

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

LABEL_TO_KEY = {r['label']: r['key'] for r in DEFAULT_PATTERN_RULES}
LABEL_TO_KEY.update({
    '均线多头': 'ma_bullish',
    '布林下轨': 'boll_lower',
    '回踩支撑': 'pullback_support',
})


def list_default_rules():
    return deepcopy(DEFAULT_PATTERN_RULES)


def resolve_rules(conditions=None, rules=None):
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


def evaluate_stock(code, name, rules, days=300):
    df = get_daily_bars(code, days=days)
    if df is None or len(df) < 35:
        return None
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
    match_mode='and',
    min_hits=1,
    max_stocks=300,
    workers=8,
    days=300,
    progress_cb=None,
):
    active_rules = resolve_rules(conditions=conditions, rules=rules)
    if not active_rules:
        return {'results': [], 'rules': [], 'scanned': 0, 'message': '无启用规则'}

    universe = list_a_shares()
    total_universe = len(universe)
    limit = int(max_stocks or 0)
    if 0 < limit < total_universe:
        stride = total_universe / limit
        universe = [universe[int(i * stride)] for i in range(limit)]

    results = []
    scanned = 0
    errors = 0
    no_data = 0
    rule_hits = {r['key']: 0 for r in active_rules}
    lock = threading.Lock()

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
            else:
                ok = hc >= max(1, int(min_hits))
            if ok:
                with lock:
                    results.append(hit)

    results.sort(key=lambda x: (-x.get('hit_count', 0), -abs(x.get('pct_chg') or 0)))
    label_of = {r['key']: r.get('label') or r['key'] for r in active_rules}
    rule_stats = [{'key': k, 'label': label_of.get(k, k), 'hits': v} for k, v in rule_hits.items()]
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
