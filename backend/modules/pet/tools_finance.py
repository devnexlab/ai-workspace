"""
智仔工具 · 金融/股票实时数据（北向资金、行业资金等）。
不入库知识库，按需拉取行情源。

说明：沪/深股通（北向）日度成交净买额在东财等源常为未披露（null/0），
不可当成真实「净流入 0」。南向与行业资金相对可用。
"""

from __future__ import annotations

import time
from typing import Any

import requests

_CACHE: dict[str, Any] = {'ts': 0.0, 'payload': None}
_CACHE_TTL = 180  # 秒

_MUTUAL_LABEL = {
    '001': '沪股通（北向）',
    '003': '深股通（北向）',
    '002': '港股通(沪)（南向）',
    '004': '港股通(深)（南向）',
}


def _ak():
    import akshare as ak
    return ak


def _num(v, default=None):
    try:
        if v is None:
            return default
        import math
        x = float(v)
        if math.isnan(x):
            return default
        return x
    except Exception:
        return default


def _fmt_yi(v) -> str:
    if v is None:
        return '—'
    return f'{v:.2f}'


def _fetch_mutual_deal_history() -> list[dict[str, Any]]:
    """东财沪深港通成交历史；北向净买额字段近年常为 null。"""
    headers = {'User-Agent': 'Mozilla/5.0'}
    rows = []
    for mt, label in _MUTUAL_LABEL.items():
        url = (
            'https://datacenter-web.eastmoney.com/api/data/v1/get'
            '?sortColumns=TRADE_DATE&sortTypes=-1&pageSize=1&pageNumber=1'
            '&reportName=RPT_MUTUAL_DEAL_HISTORY&columns=ALL&source=WEB&client=WEB'
            f'&filter=(MUTUAL_TYPE%3D%22{mt}%22)'
        )
        try:
            resp = requests.get(url, headers=headers, timeout=12)
            data = (resp.json().get('result') or {}).get('data') or []
            if not data:
                continue
            d = data[0]
            net_yiwan = _num(d.get('NET_DEAL_AMT'))  # 多为百万元
            net_yi = round(net_yiwan / 100.0, 4) if net_yiwan is not None else None
            rows.append({
                'mutual_type': mt,
                'label': label,
                'date': str(d.get('TRADE_DATE') or '')[:10],
                'net_yi': net_yi,
                'disclosed': net_yi is not None,
                'leader': str(d.get('LEAD_STOCKS_NAME') or ''),
                'buy': _num(d.get('BUY_AMT')),
                'sell': _num(d.get('SELL_AMT')),
            })
        except Exception:
            continue
    return rows


def _fetch_northbound() -> dict[str, Any]:
    ak = _ak()
    out: dict[str, Any] = {
        'summary': [],
        'mutual': [],
        'hist_latest': None,
        'north_disclosed': False,
        'north_net_buy_yi': None,
        'errors': [],
    }

    try:
        mutual = _fetch_mutual_deal_history()
        out['mutual'] = mutual
        north_vals = [m['net_yi'] for m in mutual if m['mutual_type'] in ('001', '003') and m.get('disclosed')]
        if north_vals:
            out['north_disclosed'] = True
            out['north_net_buy_yi'] = round(sum(north_vals), 4)
    except Exception as e:
        out['errors'].append(f'mutual:{e}')

    try:
        df = ak.stock_hsgt_fund_flow_summary_em()
        rows = []
        for _, r in df.iterrows():
            net_buy = _num(r.get('成交净买额'))
            direction = str(r.get('资金方向') or '')
            item = {
                'date': str(r.get('交易日') or ''),
                'type': str(r.get('类型') or ''),
                'board': str(r.get('板块') or ''),
                'direction': direction,
                'net_buy': net_buy,
                'net_flow': _num(r.get('资金净流入')),
                'index': str(r.get('相关指数') or ''),
                'index_pct': _num(r.get('指数涨跌幅')),
                # 北向且为 0：更可能是未披露占位，不当作真实 0
                'likely_placeholder': direction == '北向' and net_buy == 0.0,
            }
            rows.append(item)
        out['summary'] = rows
        # 仅当摘要里北向净买额存在且不全是占位 0 时，才采信摘要合计
        north_real = [
            x['net_buy'] for x in rows
            if x['direction'] == '北向' and x['net_buy'] is not None and not x['likely_placeholder']
        ]
        if north_real and not out['north_disclosed']:
            out['north_disclosed'] = True
            out['north_net_buy_yi'] = round(sum(north_real), 4)
    except Exception as e:
        out['errors'].append(f'summary:{e}')

    try:
        hist = ak.stock_hsgt_hist_em(symbol='北向资金')
        if hist is not None and len(hist) > 0:
            from datetime import date, timedelta
            today = date.today()
            cutoff = today - timedelta(days=10)
            latest = None
            for i in range(len(hist) - 1, -1, -1):
                row = hist.iloc[i]
                d_raw = row.get('日期')
                try:
                    if hasattr(d_raw, 'year'):
                        d = date(int(d_raw.year), int(d_raw.month), int(d_raw.day))
                    else:
                        d = date.fromisoformat(str(d_raw)[:10])
                except Exception:
                    d = None
                if d and d < cutoff:
                    break
                net = _num(row.get('当日成交净买额'))
                inflow = _num(row.get('当日资金流入'))
                if net is None and inflow is None:
                    continue
                latest = {
                    'date': str(d_raw or ''),
                    'net_buy': net,
                    'inflow': inflow,
                    'hs300': _num(row.get('沪深300')),
                    'hs300_pct': _num(row.get('沪深300-涨跌幅')),
                    'leader': str(row.get('领涨股') or ''),
                    'leader_pct': _num(row.get('领涨股-涨跌幅')),
                }
                break
            out['hist_latest'] = latest
            if latest and latest.get('net_buy') is not None and not out['north_disclosed']:
                out['north_disclosed'] = True
                out['north_net_buy_yi'] = latest['net_buy']
    except Exception as e:
        out['errors'].append(f'hist:{e}')

    return out


def _fetch_industry_flow(top_n: int = 8) -> dict[str, Any]:
    ak = _ak()
    out: dict[str, Any] = {'inflow_top': [], 'outflow_top': [], 'errors': []}
    try:
        df = ak.stock_fund_flow_industry(symbol='即时')
        if df is None or len(df) == 0:
            return out
        work = df.copy()
        work['_net'] = work['净额'].map(lambda x: _num(x, 0.0) or 0.0)
        inflow = work.sort_values('_net', ascending=False).head(top_n)
        outflow = work.sort_values('_net', ascending=True).head(top_n)

        def _rows(frame):
            items = []
            for _, r in frame.iterrows():
                items.append({
                    'industry': str(r.get('行业') or ''),
                    'pct': _num(r.get('行业-涨跌幅')),
                    'in': _num(r.get('流入资金')),
                    'out': _num(r.get('流出资金')),
                    'net': _num(r.get('净额')),
                    'leader': str(r.get('领涨股') or ''),
                    'leader_pct': _num(r.get('领涨股-涨跌幅')),
                })
            return items

        out['inflow_top'] = _rows(inflow)
        out['outflow_top'] = _rows(outflow)
    except Exception as e:
        out['errors'].append(str(e))
    return out


def get_finance_snapshot(force: bool = False) -> dict[str, Any]:
    now = time.time()
    if (
        not force
        and _CACHE['payload'] is not None
        and (now - float(_CACHE['ts'])) < _CACHE_TTL
    ):
        return _CACHE['payload']

    payload = {
        'northbound': _fetch_northbound(),
        'industry': _fetch_industry_flow(),
        'fetched_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    _CACHE['ts'] = now
    _CACHE['payload'] = payload
    return payload


def tool_finance_market(question: str = '') -> tuple[list[dict], str]:
    """金融/股票实时工具。Returns: (cites, context_text)"""
    cites = [{
        'score': '工具',
        'title': '金融实时 · 北向资金 / 行业资金',
        'meta': '行情源 · 北向或未披露',
        'source_type': 'finance_tool',
        'source_id': 0,
        'path': '/stocks',
        'snippet': '',
    }]

    try:
        # 强制刷新，避免旧缓存把 0 当成有效值
        data = get_finance_snapshot(force=True)
    except Exception as e:
        return cites, f'金融实时工具暂时不可用：{e}\n（不构成投资建议）'

    lines = [f'【金融/股票实时快照】拉取时间 {data.get("fetched_at")}']
    nb = data.get('northbound') or {}
    hist = nb.get('hist_latest') or {}
    summary = nb.get('summary') or []
    mutual = nb.get('mutual') or []

    lines.append('\n一、北向 / 沪深港通资金')
    if nb.get('north_disclosed') and nb.get('north_net_buy_yi') is not None:
        lines.append(
            f"- 北向成交净买额（有披露）：{_fmt_yi(nb['north_net_buy_yi'])} 亿元"
        )
    else:
        lines.append(
            '- 【重要】今日北向（沪股通+深股通）成交净买额：**数据源未披露**（字段为空或占位 0），'
            '**不要回答「净流入 0 亿元」**，应明确告诉用户「暂未披露/公开渠道不可用」。'
        )

    if mutual:
        lines.append('- 分渠道最近交易日：')
        for m in mutual:
            if m.get('disclosed'):
                lines.append(
                    f"  · {m.get('date')} {m.get('label')} 净买额={_fmt_yi(m.get('net_yi'))} 亿元"
                    + (f" 领涨={m.get('leader')}" if m.get('leader') else '')
                )
            else:
                lines.append(
                    f"  · {m.get('date')} {m.get('label')} 净买额=未披露"
                    + (f" 领涨={m.get('leader')}" if m.get('leader') else '')
                )

    # 南向：摘要里非占位的仍可展示
    south = [s for s in summary if s.get('direction') == '南向' and s.get('net_buy') is not None]
    if south:
        lines.append('- 南向（摘要，相对可参考）：')
        for s in south:
            lines.append(
                f"  · {s.get('date')} {s.get('board')} 净买额={_fmt_yi(s.get('net_buy'))} 亿元"
                f" {s.get('index')} {s.get('index_pct')}%"
            )

    if hist and hist.get('net_buy') is not None:
        lines.append(
            f"- 历史序列近日有效值 {hist.get('date')}：净买额={_fmt_yi(hist.get('net_buy'))} 亿元"
        )

    if nb.get('errors'):
        lines.append('- 接口告警：' + '；'.join(nb['errors']))

    ind = data.get('industry') or {}
    lines.append('\n二、行业资金（即时，相对可靠，可直接用于回答「哪些行业流入多」）')
    if ind.get('inflow_top'):
        lines.append('- 净流入靠前：')
        for i, r in enumerate(ind['inflow_top'][:8], 1):
            lines.append(
                f"  {i}. {r.get('industry')} 净额={_fmt_yi(r.get('net'))} "
                f"涨跌={_fmt_yi(r.get('pct'))}% 领涨={r.get('leader')}"
            )
    if ind.get('outflow_top'):
        lines.append('- 净流出靠前：')
        for i, r in enumerate(ind['outflow_top'][:5], 1):
            lines.append(
                f"  {i}. {r.get('industry')} 净额={_fmt_yi(r.get('net'))} "
                f"涨跌={_fmt_yi(r.get('pct'))}%"
            )
    if ind.get('errors'):
        lines.append('- 行业资金告警：' + '；'.join(ind['errors']))

    lines.append(
        '\n回答要求：北向未披露时先说明未披露，再答行业资金；'
        '勿把占位 0 写成真实净流入。仅供参考，不构成投资建议。'
    )
    return cites, '\n'.join(lines)
