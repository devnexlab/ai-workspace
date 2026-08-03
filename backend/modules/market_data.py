"""
A股行情数据（AKShare）。

- 全市场列表：东方财富现货快照（一次拉全）
- 日 K：按代码拉取并本地缓存，供指标/筛选复用
"""

from __future__ import annotations

import os
import json
import random
import threading
import time
from urllib.request import Request, urlopen
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from config import BASE_DIR

def _cache_dir() -> Path:
    try:
        from config import get_setting
        raw = get_setting('stock', 'cache_dir', '') or ''
    except Exception:
        raw = ''
    path = Path(raw) if raw else (BASE_DIR / 'data' / 'stock_cache')
    path.mkdir(parents=True, exist_ok=True)
    return path


# 排除 ST / 北交所 / 退市等时可在筛选层再滤
_EXCLUDE_NAME_KEYWORDS = ('退',)


def _ak():
    import akshare as ak
    return ak


def list_a_shares(force_refresh=False):
    """
    返回 [{'code','name',...}, ...]
    优先读当日缓存；东财现货失败时回退到代码表。
    """
    cache_file = _cache_dir() / f"spot_{datetime.now().strftime('%Y%m%d')}.csv"
    if cache_file.exists() and not force_refresh:
        try:
            df = pd.read_csv(cache_file, dtype={'code': str})
            return df.to_dict('records')
        except Exception:
            pass

    ak = _ak()
    df = None
    # 1) 东财现货（字段全，但偶发断连）
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
                elif c in ('成交量',):
                    colmap[c] = 'volume'
                elif c in ('成交额',):
                    colmap[c] = 'amount'
                elif c in ('换手率',):
                    colmap[c] = 'turnover'
            raw = raw.rename(columns=colmap)
            keep = [c for c in ('code', 'name', 'price', 'pct_chg', 'volume', 'amount', 'turnover') if c in raw.columns]
            df = raw[keep].copy()
            break
        except Exception as e:
            print(f'[market_data] spot_em failed ({attempt}): {e}')
            time.sleep(1.5)

    # 2) 回退：A股代码名称表（稳）
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
    # 过滤北交所/基金等常见前缀：只保留主板/创业板/科创常见
    df = df[df['code'].str.startswith(('00', '30', '60', '68'))]

    try:
        df.to_csv(cache_file, index=False)
    except Exception:
        pass
    return df.to_dict('records')


def _market_symbol(code: str) -> str:
    """腾讯/新浪日 K 需要 sh/sz 前缀。"""
    code = str(code).zfill(6)
    if code.startswith(('5', '6', '9')):
        return f'sh{code}'
    return f'sz{code}'


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


class WafBlocked(Exception):
    """腾讯 WAF 限流（返回 501 拦截页）。"""


# 某数据源被限流后，在该时间点之前不再尝试
_SOURCE_COOLDOWN = {}
_COOLDOWN_LOCK = threading.Lock()


def _source_available(name: str) -> bool:
    with _COOLDOWN_LOCK:
        return time.time() >= _SOURCE_COOLDOWN.get(name, 0)


def _mark_source_blocked(name: str, seconds: int = 180):
    with _COOLDOWN_LOCK:
        _SOURCE_COOLDOWN[name] = time.time() + seconds
    print(f'[market_data] {name} 被限流，冷却 {seconds}s')


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
    """腾讯 K 线数组顺序：date, open, close, high, low, volume。"""
    records = [
        {
            'date': row[0], 'open': row[1], 'close': row[2],
            'high': row[3], 'low': row[4], 'volume': row[5],
        }
        for row in rows if len(row) >= 6
    ]
    return _normalize_bars(pd.DataFrame(records))


def _fetch_tencent_fq(code: str, days: int) -> pd.DataFrame:
    """腾讯前复权日K（首选）。"""
    symbol = _market_symbol(code)
    count = max(60, min(int(days) + 5, 800))
    payload = _get_json(
        'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get'
        f'?param={symbol},day,,,{count},qfq'
    )
    node = (payload.get('data') or {}).get(symbol) or {}
    return _rows_to_bars(node.get('qfqday') or node.get('day') or [])


def _fetch_tencent_raw(code: str, days: int) -> pd.DataFrame:
    """腾讯不复权日K（前复权被限流时备用）。"""
    symbol = _market_symbol(code)
    count = max(60, min(int(days) + 5, 800))
    payload = _get_json(
        'https://web.ifzq.gtimg.cn/appstock/app/kline/kline'
        f'?param={symbol},day,,,{count}'
    )
    node = (payload.get('data') or {}).get(symbol) or {}
    return _rows_to_bars(node.get('day') or [])


# akshare 的新浪接口内部用 py_mini_racer 执行 JS，多线程并发会直接把进程打崩，必须串行
_SINA_LOCK = threading.Lock()


def _fetch_sina(code: str, days: int) -> pd.DataFrame:
    """新浪前复权日K（最后兜底：串行、较慢）。"""
    ak = _ak()
    end = datetime.now().strftime('%Y%m%d')
    start = (datetime.now() - timedelta(days=max(days * 2, 420))).strftime('%Y%m%d')
    with _SINA_LOCK:
        raw = ak.stock_zh_a_daily(
            symbol=_market_symbol(code), start_date=start, end_date=end, adjust='qfq',
        )
    return _normalize_bars(raw)


def get_daily_bars(code: str, days: int = 120, force_refresh=False) -> pd.DataFrame:
    """
    日 K：columns = date, open, high, low, close, volume, amount
    优先读当日缓存；未缓存时腾讯前复权 → 腾讯不复权 → 新浪逐级兜底。
    """
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
    # 腾讯前复权最快最准；被 WAF 限流时退到腾讯不复权；新浪串行只作最后兜底
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
                    time.sleep(0.4 + random.random() * 0.4)
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


def clear_old_spot_cache(keep_days=3):
    cutoff = datetime.now() - timedelta(days=keep_days)
    for f in _cache_dir().glob('spot_*.csv'):
        try:
            if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                f.unlink()
        except Exception:
            pass
