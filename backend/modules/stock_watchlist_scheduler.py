"""
自选股现价定时刷新：交易日收盘后更新 current_price，前端据此显示盈亏。

设置项（stock）：
  watchlist_auto_refresh: true/false（默认 true）
  watchlist_refresh_hour: 0-23（默认 15，收盘后）
  watchlist_last_refresh_date: YYYY-MM-DD
"""

from __future__ import annotations

import threading
import time
from datetime import datetime

_scheduler_started = False
_lock = threading.Lock()


def refresh_watchlist_prices(force_spot=True):
    """按自选股代码拉取腾讯实时行情，回写 current_price。"""
    from config import get_db, update_setting
    from modules.market_data import fetch_spot_prices, _normalize_stock_code

    conn = get_db()
    rows = conn.execute(
        'SELECT id, stock_code, buy_price, quantity FROM stock_watchlist'
    ).fetchall()
    codes = [_normalize_stock_code(r['stock_code']) for r in rows]
    price_map = fetch_spot_prices(codes)

    updated = 0
    skipped = 0
    details = []
    for r in rows:
        code = _normalize_stock_code(r['stock_code'])
        price = price_map.get(code)
        if price is None:
            skipped += 1
            continue
        conn.execute(
            'UPDATE stock_watchlist SET current_price=%s WHERE id=%s',
            (round(float(price), 3), r['id']),
        )
        updated += 1
        buy = float(r['buy_price'] or 0)
        qty = float(r['quantity'] or 0)
        pnl_pct = ((price - buy) / buy * 100) if buy else None
        pnl_amt = (price - buy) * qty if buy and qty else None
        details.append({
            'id': r['id'],
            'stock_code': code,
            'current_price': round(float(price), 3),
            'pnl_pct': round(pnl_pct, 2) if pnl_pct is not None else None,
            'pnl_amount': round(pnl_amt, 2) if pnl_amt is not None else None,
        })
    conn.commit()
    conn.close()

    now = datetime.now()
    try:
        update_setting('stock', 'watchlist_last_refresh_date', now.strftime('%Y-%m-%d'))
        update_setting('stock', 'watchlist_last_refresh_at', now.strftime('%Y-%m-%d %H:%M:%S'))
    except Exception:
        pass

    msg = f'已更新 {updated}/{len(rows)} 只自选股现价'
    if skipped:
        msg += f'（{skipped} 只未取到行情）'

    return {
        'updated': updated,
        'total': len(rows),
        'skipped': skipped,
        'details': details,
        'refreshed_at': now.strftime('%Y-%m-%d %H:%M:%S'),
        'message': msg,
    }


def _should_run_now():
    from config import get_setting
    enabled = str(get_setting('stock', 'watchlist_auto_refresh', 'true')).lower() == 'true'
    if not enabled:
        return False
    # 周末跳过（A股休市）
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    try:
        hour = int(get_setting('stock', 'watchlist_refresh_hour', '15') or 15)
    except (TypeError, ValueError):
        hour = 15
    hour = max(0, min(23, hour))
    if now.hour != hour:
        return False
    # 整点后 20 分钟窗口（收盘数据更稳）
    if now.minute > 20:
        return False
    last = get_setting('stock', 'watchlist_last_refresh_date', '')
    today = now.strftime('%Y-%m-%d')
    return last != today


def _tick():
    if not _should_run_now():
        return
    with _lock:
        if not _should_run_now():
            return
        print(f'[WatchlistScheduler] 刷新现价 {datetime.now().isoformat(timespec="seconds")}')
        try:
            result = refresh_watchlist_prices(force_spot=True)
            print(f'[WatchlistScheduler] 完成: {result.get("message")}')
        except Exception as e:
            print(f'[WatchlistScheduler] 失败: {e}')


def _loop():
    time.sleep(20)
    while True:
        try:
            _tick()
        except Exception as e:
            print(f'[WatchlistScheduler] tick error: {e}')
        time.sleep(60)


def start_watchlist_scheduler():
    global _scheduler_started
    if _scheduler_started:
        return
    import os
    from config import FLASK_DEBUG
    if FLASK_DEBUG and os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        return
    _scheduler_started = True
    t = threading.Thread(target=_loop, name='watchlist-scheduler', daemon=True)
    t.start()
    print('[WatchlistScheduler] 已启动（交易日默认 15 点刷新自选股现价）')
