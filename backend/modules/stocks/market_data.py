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


# 证券账户通常搜不到/不可正常买入：退市、ST、暂停上市等
_EXCLUDE_NAME_KEYWORDS = (
    '退市', '退', '暂停上市', '整理期',
    'ST', '*ST', '＊ST', 'S*ST', 'SST', 'PT',
)


def is_tradable_a_share(code: str = '', name: str = '', price=None) -> bool:
    """
    是否更可能在普通证券账户搜到并可交易。
    排除：名称含 ST/*ST/退市/暂停上市；代码非主板/创业/科创常见前缀；
    若传入 price 且无效（空/NaN/≤0），也视为不可交易（退市/长期停牌常见）。
    """
    code = _normalize_stock_code(code)
    if not code or not code.startswith(('00', '30', '60', '68')):
        return False
    raw = str(name or '')
    # 统一全角星号，便于匹配 ＊ST
    n = raw.upper().replace('＊', '*').replace(' ', '')
    if 'ST' in n:  # ST / *ST / S*ST / SST
        return False
    if 'PT' in n:
        return False
    for kw in ('退市', '暂停上市', '整理期'):
        if kw in raw:
            return False
    # 「退」单独判断：避免误伤含「退」但非退市的极少数名字；常见为「退市XX」已覆盖
    if raw.startswith('退') or '退市' in raw:
        return False
    if price is not None and price != '':
        try:
            p = float(price)
            if pd.isna(p) or p <= 0:
                return False
        except (TypeError, ValueError):
            return False
    return True


def _ak():
    import akshare as ak
    return ak


def _normalize_stock_code(code) -> str:
    """统一成 6 位数字代码。支持 600519 / sh600519 / 600519.SH / 600519.0。"""
    raw = str(code or '').strip().upper()
    if not raw or raw.lower() in ('nan', 'none'):
        return ''
    raw = raw.replace('SH', '').replace('SZ', '').replace('.', '')
    # 去掉非数字（如前缀残留）
    digits = ''.join(ch for ch in raw if ch.isdigit())
    if not digits:
        return ''
    # 处理 float 残留：6005190 来自 600519.0 去掉点后多一位 0
    if len(digits) == 7 and digits.endswith('0'):
        digits = digits[:-1]
    if len(digits) > 6:
        digits = digits[-6:]
    return digits.zfill(6)


def list_a_shares(force_refresh=False):
    """
    返回 [{'code','name','price','pct_chg','volume','amount','turnover'}, ...]
    优先读当日缓存；东财现货失败时回退代码表，再用腾讯行情补全现价/涨跌幅等。
    """
    cache_file = _cache_dir() / f"spot_{datetime.now().strftime('%Y%m%d')}.csv"
    if cache_file.exists() and not force_refresh:
        try:
            df = pd.read_csv(cache_file, dtype={'code': str})
            rows = df.to_dict('records')
            return [
                r for r in rows
                if is_tradable_a_share(r.get('code'), r.get('name'), r.get('price'))
            ]
        except Exception:
            pass

    ak = _ak()
    df = None
    from_spot = False
    quote_source = ''

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
            from_spot = 'price' in df.columns
            quote_source = 'eastmoney'
            break
        except Exception as e:
            print(f'[market_data] spot_em failed ({attempt}): {e}')
            time.sleep(1.5)

    # 2) 回退：A股代码名称表（稳，但无价格）→ 再用腾讯批量补行情
    if df is None or df.empty:
        try:
            raw = ak.stock_info_a_code_name()
            df = raw.rename(columns={'code': 'code', 'name': 'name'})[['code', 'name']].copy()
            from_spot = False
            quote_source = 'code_name'
        except Exception as e:
            raise RuntimeError(f'无法获取 A 股列表: {e}')

    df['code'] = df['code'].map(_normalize_stock_code)
    df = df[df['code'].str.match(r'^\d{6}$', na=False)]
    if 'name' in df.columns:
        has_price = 'price' in df.columns
        mask = df.apply(
            lambda r: is_tradable_a_share(
                r.get('code'),
                r.get('name'),
                r.get('price') if has_price else None,
            ),
            axis=1,
        )
        df = df[mask]
    # 过滤北交所/基金等常见前缀：只保留主板/创业板/科创常见
    df = df[df['code'].str.startswith(('00', '30', '60', '68'))]

    # 东财失败时：用腾讯行情补全现价/涨跌幅/成交额（否则全市场表只有代码名）
    need_quote = (not from_spot) or ('price' not in df.columns) or df['price'].isna().all()
    if need_quote and not df.empty:
        print(f'[market_data] enriching {len(df)} symbols via Tencent quotes…')
        quotes = fetch_spot_quotes(df['code'].tolist())
        if quotes:
            qdf = pd.DataFrame(list(quotes.values()))
            keep_q = [c for c in ('code', 'price', 'pct_chg', 'volume', 'amount', 'turnover') if c in qdf.columns]
            qdf = qdf[keep_q]
            df = df.drop(columns=[c for c in ('price', 'pct_chg', 'volume', 'amount', 'turnover') if c in df.columns], errors='ignore')
            df = df.merge(qdf, on='code', how='left')
            from_spot = bool(qdf['price'].notna().any()) if 'price' in qdf.columns else False
            quote_source = 'tencent' if from_spot else 'code_name'
            print(f'[market_data] tencent enriched {int(qdf["price"].notna().sum()) if "price" in qdf.columns else 0} / {len(df)}')

    # 带行情才写缓存，避免无价代码表污染
    if from_spot and 'price' in df.columns:
        try:
            df.to_csv(cache_file, index=False)
        except Exception:
            pass
    # 附加来源标记（不入库，供调试）
    records = df.to_dict('records')
    for r in records:
        r['_quote_source'] = quote_source
    return records


def _market_symbol(code: str) -> str:
    """腾讯/新浪日 K 需要 sh/sz 前缀。"""
    code = _normalize_stock_code(code)
    if code.startswith(('5', '6', '9')):
        return f'sh{code}'
    return f'sz{code}'


def _parse_tencent_line(line: str) -> dict | None:
    """解析腾讯 qt.gtimg.cn 单行行情。"""
    line = (line or '').strip()
    if '="' not in line:
        return None
    payload = line.split('="', 1)[1].rstrip('";')
    if not payload:
        return None
    parts = payload.split('~')
    if len(parts) < 5:
        return None
    code = _normalize_stock_code(parts[2])
    try:
        price = float(parts[3])
    except (TypeError, ValueError):
        return None
    if not code or price <= 0:
        return None

    def _f(idx):
        try:
            if idx >= len(parts):
                return None
            v = parts[idx]
            if v is None or v == '':
                return None
            return float(v)
        except (TypeError, ValueError):
            return None

    # 成交额：优先 parts[35] 第三段（元），否则 parts[37]（万元）
    amount = None
    if len(parts) > 35 and parts[35]:
        segs = str(parts[35]).split('/')
        if len(segs) >= 3:
            try:
                amount = float(segs[2])
            except (TypeError, ValueError):
                amount = None
    if amount is None:
        wan = _f(37)
        if wan is not None:
            amount = wan * 10000

    return {
        'code': code,
        'name': parts[1] if len(parts) > 1 else '',
        'price': price,
        'pct_chg': _f(32),
        'volume': _f(36),
        'amount': amount,
        'turnover': _f(38),
    }


def fetch_spot_quotes(codes, workers: int = 8) -> dict:
    """
    批量取腾讯实时行情，返回
    { '600519': {'price', 'pct_chg', 'volume', 'amount', 'turnover', 'name'}, ... }
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    uniq = []
    seen = set()
    for c in codes or []:
        code = _normalize_stock_code(c)
        if code and code not in seen:
            seen.add(code)
            uniq.append(code)
    if not uniq:
        return {}

    batches = [uniq[i:i + 60] for i in range(0, len(uniq), 60)]

    def _fetch_batch(batch):
        symbols = ','.join(_market_symbol(c) for c in batch)
        url = f'https://qt.gtimg.cn/q={symbols}'
        req = Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Referer': 'https://gu.qq.com/',
        })
        out = {}
        try:
            with urlopen(req, timeout=12) as resp:
                body = resp.read().decode('gbk', 'ignore')
        except Exception as e:
            print(f'[market_data] tencent quote batch failed: {e}')
            return out
        for line in body.replace('\n', '').split(';'):
            parsed = _parse_tencent_line(line)
            if parsed:
                out[parsed['code']] = parsed
        return out

    quote_map = {}
    workers = max(1, min(int(workers or 8), 16))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_fetch_batch, b) for b in batches]
        for fut in as_completed(futs):
            try:
                quote_map.update(fut.result() or {})
            except Exception as e:
                print(f'[market_data] tencent worker error: {e}')
    return quote_map


def fetch_spot_prices(codes) -> dict:
    """
    按代码批量取实时/最新价（腾讯行情），返回 { '600519': 1333.0, ... }。
    适合自选股刷新；不要依赖全市场东财快照（易失败且缓存可能无价）。
    """
    quotes = fetch_spot_quotes(codes)
    price_map = {c: q['price'] for c, q in quotes.items() if q.get('price')}

    # 个别失败时用最近日K收盘兜底
    uniq = []
    seen = set()
    for c in codes or []:
        code = _normalize_stock_code(c)
        if code and code not in seen:
            seen.add(code)
            uniq.append(code)
    missing = [c for c in uniq if c not in price_map]
    for code in missing:
        try:
            bars = get_daily_bars(code, days=5, force_refresh=False)
            if bars is not None and not bars.empty:
                close = float(bars.iloc[-1]['close'])
                if close > 0:
                    price_map[code] = close
        except Exception as e:
            print(f'[market_data] daily close fallback failed for {code}: {e}')

    return price_map


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
    code = _normalize_stock_code(code)
    if not code:
        return pd.DataFrame()
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
