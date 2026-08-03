"""
A股行情数据。

日 K 优先腾讯前复权直连接口（一次返回 N 日），失败再退到不复权 / AKShare 新浪。
"""

from __future__ import annotations

import json
import random
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd

from config import BASE_DIR

_SOURCE_COOLDOWN = {}
_COOLDOWN_LOCK = threading.Lock()
_SINA_LOCK = threading.Lock()


class WafBlocked(Exception):
    """腾讯 WAF 限流。"""


def _cache_dir() -> Path:
    path = BASE_DIR / 'data' / 'stock_cache'
    path.mkdir(parents=True, exist_ok=True)
    return path


def _ak():
    import akshare as ak
    return ak


def _market_symbol(code: str) -> str:
    code = str(code).zfill(6)
    if code.startswith(('5', '6', '9')):
        return f'sh{code}'
    return f'sz{code}'


def _source_available(name: str) -> bool:
    with _COOLDOWN_LOCK:
        return time.time() >= _SOURCE_COOLDOWN.get(name, 0)


def _mark_source_blocked(name: str, seconds: int = 180):
    with _COOLDOWN_LOCK:
        _SOURCE_COOLDOWN[name] = time.time() + seconds
    print(f'[market_data] {name} 被限流，冷却 {seconds}s')


def _normalize_bars(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    rename = {}
    for c in df.columns:
        cl = str(c).lower()
        if c in ('日期',) or cl == 'date':
            rename[c] = 'date'
        elif c in ('开盘',) or cl == 'open':
            rename[c] = 'open'
        elif c in ('收盘',) or cl == 'close':
            rename[c] = 'close'
        elif c in ('最高',) or cl == 'high':
            rename[c] = 'high'
        elif c in ('最低',) or cl == 'low':
            rename[c] = 'low'
        elif c in ('成交量',) or cl == 'volume':
            rename[c] = 'volume'
        elif c in ('成交额',) or cl == 'amount':
            rename[c] = 'amount'
    df = df.rename(columns=rename)
    need = ['date', 'open', 'high', 'low', 'close', 'volume']
    if not all(c in df.columns for c in need):
        return pd.DataFrame()
    keep = need + (['amount'] if 'amount' in df.columns else [])
    out = df[keep].copy()
    out['date'] = pd.to_datetime(out['date'])
    for c in ('open', 'high', 'low', 'close', 'volume'):
        out[c] = pd.to_numeric(out[c], errors='coerce')
    return out.dropna(subset=['close']).sort_values('date').reset_index(drop=True)


def _get_json(url: str, timeout: int = 8):
    req = Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Referer': 'https://gu.qq.com/',
    })
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode('utf-8', 'ignore')
    except Exception as e:
        if '501' in str(e):
            raise WafBlocked(str(e))
        raise
    if body.lstrip().startswith('<'):
        raise WafBlocked('WAF 拦截页')
    return json.loads(body)


def _rows_to_bars(rows) -> pd.DataFrame:
    records = [
        {
            'date': row[0], 'open': row[1], 'close': row[2],
            'high': row[3], 'low': row[4], 'volume': row[5],
        }
        for row in rows if len(row) >= 6
    ]
    return _normalize_bars(pd.DataFrame(records))


def _fetch_tencent_fq(code: str, days: int) -> pd.DataFrame:
    symbol = _market_symbol(code)
    count = max(60, min(int(days) + 5, 800))
    payload = _get_json(
        'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get'
        f'?param={symbol},day,,,{count},qfq'
    )
    node = (payload.get('data') or {}).get(symbol) or {}
    return _rows_to_bars(node.get('qfqday') or node.get('day') or [])


def _fetch_tencent_raw(code: str, days: int) -> pd.DataFrame:
    symbol = _market_symbol(code)
    count = max(60, min(int(days) + 5, 800))
    payload = _get_json(
        'https://web.ifzq.gtimg.cn/appstock/app/kline/kline'
        f'?param={symbol},day,,,{count}'
    )
    node = (payload.get('data') or {}).get(symbol) or {}
    return _rows_to_bars(node.get('day') or [])


def _fetch_sina(code: str, days: int) -> pd.DataFrame:
    ak = _ak()
    end = datetime.now().strftime('%Y%m%d')
    start = (datetime.now() - timedelta(days=max(days * 2, 420))).strftime('%Y%m%d')
    with _SINA_LOCK:
        raw = ak.stock_zh_a_daily(
            symbol=_market_symbol(code), start_date=start, end_date=end, adjust='qfq',
        )
    return _normalize_bars(raw)


def get_daily_bars(code: str, days: int = 120, force_refresh=False) -> pd.DataFrame:
    """日 K：date, open, high, low, close, volume[, amount]。"""
    code = str(code).zfill(6)
    cache_file = _cache_dir() / f'hist_{code}.csv'
    if cache_file.exists() and not force_refresh:
        mtime = datetime.fromtimestamp(cache_file.stat().st_mtime)
        if mtime.date() == datetime.now().date():
            try:
                df = pd.read_csv(cache_file, parse_dates=['date'])
                if len(df) >= max(30, days // 2):
                    return df.tail(days).reset_index(drop=True)
            except Exception:
                pass

    df = pd.DataFrame()
    sources = (
        ('tencent_qfq', _fetch_tencent_fq),
        ('tencent_raw', _fetch_tencent_raw),
        ('sina', _fetch_sina),
    )
    for name, fetch in sources:
        if not _source_available(name):
            continue
        for attempt in range(2):
            try:
                df = fetch(code, days)
                break
            except WafBlocked:
                _mark_source_blocked(name)
                df = pd.DataFrame()
                break
            except Exception as e:
                if attempt == 0:
                    time.sleep(0.3 + random.random() * 0.3)
                    continue
                print(f'[market_data] {name} failed for {code}: {e}')
                df = pd.DataFrame()
        if not df.empty:
            break

    if df.empty:
        return pd.DataFrame()

    try:
        df.to_csv(cache_file, index=False)
    except Exception:
        pass
    return df.tail(days).reset_index(drop=True)


_EXCLUDE_NAME_KEYWORDS = ('退',)


def list_a_shares(force_refresh=False):
    """返回 [{'code','name',...}, ...]；东财失败时回退代码表。"""
    cache_file = _cache_dir() / f"spot_{datetime.now().strftime('%Y%m%d')}.csv"
    if cache_file.exists() and not force_refresh:
        try:
            df = pd.read_csv(cache_file, dtype={'code': str})
            return df.to_dict('records')
        except Exception:
            pass

    ak = _ak()
    df = None
    for attempt in range(2):
        try:
            raw = ak.stock_zh_a_spot_em()
            colmap = {}
            for c in raw.columns:
                if c in ('代码', '股票代码'):
                    colmap[c] = 'code'
                elif c in ('名称', '股票名称'):
                    colmap[c] = 'name'
                elif c in ('最新价',):
                    colmap[c] = 'price'
                elif c in ('涨跌幅',):
                    colmap[c] = 'pct_chg'
            raw = raw.rename(columns=colmap)
            keep = [c for c in ('code', 'name', 'price', 'pct_chg') if c in raw.columns]
            df = raw[keep].copy()
            break
        except Exception as e:
            print(f'[market_data] spot_em failed ({attempt}): {e}')
            time.sleep(1)

    if df is None or df.empty:
        try:
            raw = ak.stock_info_a_code_name()
            df = raw.rename(columns={'code': 'code', 'name': 'name'})[['code', 'name']].copy()
        except Exception as e:
            raise RuntimeError(f'无法获取 A 股列表: {e}')

    df['code'] = df['code'].astype(str).str.zfill(6)
    df = df[df['code'].str.match(r'^\d{6}$', na=False)]
    if 'name' in df.columns:
        mask = ~df['name'].astype(str).apply(lambda n: any(k in n for k in _EXCLUDE_NAME_KEYWORDS))
        df = df[mask]
    df = df[df['code'].str.startswith(('00', '30', '60', '68'))]
    try:
        df.to_csv(cache_file, index=False)
    except Exception:
        pass
    return df.to_dict('records')
