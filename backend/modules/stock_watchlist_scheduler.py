"""
自选股现价定时刷新：交易日收盘后更新 current_price，前端据此显示盈亏。
刷新后检查目标价 / 跌破成本，写入 reminder（type=stock_alert）。

设置项（stock）：
  watchlist_auto_refresh: true/false（默认 true）
  watchlist_refresh_hour: 0-23（默认 15，收盘后）
  watchlist_last_refresh_date: YYYY-MM-DD
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, date

_scheduler_started = False
_lock = threading.Lock()


def _upsert_stock_alert(conn, *, code, name, title, content):
    """同日同股同标题不重复创建 pending 提醒。"""
    today = date.today().isoformat()
    existing = conn.execute(
        '''SELECT id FROM reminder
           WHERE type='stock_alert' AND status='pending'
             AND title=? AND remind_date=? LIMIT 1''',
        (title, today),
    ).fetchone()
    if existing:
        return False
    conn.execute(
        '''INSERT INTO reminder (customer_id, type, title, content, remind_date, status, priority, suggested_action)
           VALUES (NULL, 'stock_alert', ?, ?, ?, 'pending', 'high', ?)''',
        (title, content, today, f'查看自选股 {code}'),
    )
    return True


def _check_price_alerts(conn, rows, price_map):
    """根据最新价写入股票预警提醒。"""
    from modules.market_data import _normalize_stock_code

    created = 0
    for r in rows:
        code = _normalize_stock_code(r['stock_code'])
        price = price_map.get(code)
        if price is None:
            continue
        price = float(price)
        name = r.get('stock_name') or code
        buy = float(r.get('buy_price') or 0)
        target = float(r.get('target_price') or 0)
        alert_below = r.get('alert_below_cost')
        alert_target = r.get('alert_on_target')
        if alert_below is None:
            alert_below = True
        if alert_target is None:
            alert_target = True

        if alert_below and buy > 0 and price < buy:
            title = f'{name}({code}) 跌破成本'
            content = f'现价 {price:.3f}，成本 {buy:.3f}，已跌破买入价。'
            if _upsert_stock_alert(conn, code=code, name=name, title=title, content=content):
                created += 1

        if alert_target and target > 0 and price <= target:
            title = f'{name}({code}) 触及目标价'
            content = f'现价 {price:.3f}，目标价 {target:.3f}。'
            if _upsert_stock_alert(conn, code=code, name=name, title=title, content=content):
                created += 1
    return created


def refresh_watchlist_prices(force_spot=True):
    """按自选股代码拉取腾讯实时行情，回写 current_price，并检查预警。"""
    from config import get_db, update_setting
    from modules.market_data import fetch_spot_prices, _normalize_stock_code

    conn = get_db()
    rows = conn.execute(
        '''SELECT id, stock_code, stock_name, buy_price, quantity,
                  target_price, alert_below_cost, alert_on_target
           FROM stock_watchlist'''
    ).fetchall()
    rows = [dict(r) for r in rows]
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

    alerts_created = 0
    try:
        alerts_created = _check_price_alerts(conn, rows, price_map)
    except Exception as e:
        print(f'[WatchlistScheduler] alert check failed: {e}')

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
    if alerts_created:
        msg += f'，新增 {alerts_created} 条股价预警'

    return {
        'updated': updated,
        'total': len(rows),
        'skipped': skipped,
        'alerts_created': alerts_created,
        'details': details,
        'refreshed_at': now.strftime('%Y-%m-%d %H:%M:%S'),
        'message': msg,
    }


def _should_run_now():
    from config import get_setting
    enabled = str(get_setting('stock', 'watchlist_auto_refresh', 'true')).lower() == 'true'
    if not enabled:
        return False
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
