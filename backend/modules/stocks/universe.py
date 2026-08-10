"""
全市场 A 股列表：入库、夜间全量刷新、新股自动加入。

数据源：AKShare list_a_shares（东财现货 / 代码表回退）
设置项（stock）：
  universe_auto_refresh: true/false（默认 true）
  universe_refresh_hour: 0-23（默认 18，收盘后全量更新）
  universe_last_refresh_date: YYYY-MM-DD
"""

from __future__ import annotations

import threading
import time
from datetime import datetime

_scheduler_started = False
_lock = threading.Lock()


def _board_of(code: str) -> str:
    c = (code or '').strip()
    if c.startswith('68'):
        return '科创板'
    if c.startswith('30'):
        return '创业板'
    if c.startswith('60'):
        return '沪市主板'
    if c.startswith('00'):
        return '深市主板'
    return '其他'


def _market_of(code: str) -> str:
    c = (code or '').strip()
    if c.startswith(('5', '6', '9')):
        return 'SH'
    return 'SZ'


def refresh_stock_universe(force_refresh=True):
    """
    拉取全市场 A 股并 upsert 到 stock_universe。
    - 有则更新名称/行情
    - 新股自动 INSERT
    - 本次未出现的标记 is_active=false（退市/过滤）
    """
    from config import get_db, update_setting
    from modules.stocks.market_data import list_a_shares, _normalize_stock_code, is_tradable_a_share

    now = datetime.now()
    rows = list_a_shares(force_refresh=force_refresh) or []
    # 再滤一遍，避免缓存里残留 ST/退市
    rows = [
        r for r in rows
        if is_tradable_a_share(r.get('code'), r.get('name'), r.get('price'))
    ]
    if not rows:
        return {
            'total': 0,
            'inserted': 0,
            'updated': 0,
            'deactivated': 0,
            'message': '未拉到股票列表，请稍后重试',
            'refreshed_at': now.strftime('%Y-%m-%d %H:%M:%S'),
        }

    conn = get_db()
    existing = {
        _normalize_stock_code(r['code']): dict(r)
        for r in conn.execute('SELECT code, id FROM stock_universe').fetchall()
    }

    seen = set()
    inserted = 0
    updated = 0

    for item in rows:
        code = _normalize_stock_code(item.get('code'))
        if not code or code in seen:
            continue
        seen.add(code)
        name = (item.get('name') or '').strip()
        price = item.get('price')
        pct_chg = item.get('pct_chg')
        volume = item.get('volume')
        amount = item.get('amount')
        turnover = item.get('turnover')
        try:
            price = float(price) if price is not None and price != '' else None
            if price is not None and (price != price):  # NaN
                price = None
        except (TypeError, ValueError):
            price = None
        try:
            pct_chg = float(pct_chg) if pct_chg is not None and pct_chg != '' else None
            if pct_chg is not None and (pct_chg != pct_chg):
                pct_chg = None
        except (TypeError, ValueError):
            pct_chg = None
        try:
            volume = float(volume) if volume is not None and volume != '' else None
            if volume is not None and (volume != volume):
                volume = None
        except (TypeError, ValueError):
            volume = None
        try:
            amount = float(amount) if amount is not None and amount != '' else None
            if amount is not None and (amount != amount):
                amount = None
        except (TypeError, ValueError):
            amount = None
        try:
            turnover = float(turnover) if turnover is not None and turnover != '' else None
            if turnover is not None and (turnover != turnover):
                turnover = None
        except (TypeError, ValueError):
            turnover = None

        market = _market_of(code)
        board = _board_of(code)

        if code in existing:
            conn.execute(
                '''UPDATE stock_universe SET
                     name=?, market=?, board=?,
                     price=COALESCE(?, price),
                     pct_chg=COALESCE(?, pct_chg),
                     volume=COALESCE(?, volume),
                     amount=COALESCE(?, amount),
                     turnover=COALESCE(?, turnover),
                     is_active=TRUE,
                     refreshed_at=CURRENT_TIMESTAMP
                   WHERE code=?''',
                (name, market, board, price, pct_chg, volume, amount, turnover, code),
            )
            updated += 1
        else:
            conn.execute(
                '''INSERT INTO stock_universe
                   (code, name, market, board, price, pct_chg, volume, amount, turnover,
                    is_active, source, refreshed_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)''',
                (code, name, market, board, price, pct_chg, volume, amount, turnover,
                 True, 'akshare'),
            )
            inserted += 1

    deactivated = 0
    for code in existing:
        if code not in seen:
            conn.execute(
                'UPDATE stock_universe SET is_active=FALSE, refreshed_at=CURRENT_TIMESTAMP WHERE code=?',
                (code,),
            )
            deactivated += 1

    conn.commit()
    active_count = conn.execute(
        'SELECT COUNT(*) AS c FROM stock_universe WHERE is_active=TRUE'
    ).fetchone()['c']
    conn.close()

    try:
        update_setting('stock', 'universe_last_refresh_date', now.strftime('%Y-%m-%d'))
        update_setting('stock', 'universe_last_refresh_at', now.strftime('%Y-%m-%d %H:%M:%S'))
    except Exception:
        pass

    msg = f'全市场同步完成：活跃 {active_count} 只（新增 {inserted}，更新 {updated}'
    if deactivated:
        msg += f'，下架 {deactivated}'
    msg += '）'
    src = ''
    for item in rows[:20]:
        if item.get('_quote_source'):
            src = item.get('_quote_source')
            break
    if src == 'tencent':
        msg += '；行情由腾讯接口补全（东财现货暂不可用）'
    elif src == 'eastmoney':
        msg += '；行情来自东财现货'
    elif src == 'code_name':
        msg += '；仅同步了代码名称，行情未取到'

    return {
        'total': active_count,
        'fetched': len(seen),
        'inserted': inserted,
        'updated': updated,
        'deactivated': deactivated,
        'message': msg,
        'refreshed_at': now.strftime('%Y-%m-%d %H:%M:%S'),
    }


def _should_run_now():
    from config import get_setting
    enabled = str(get_setting('stock', 'universe_auto_refresh', 'true')).lower() == 'true'
    if not enabled:
        return False
    now = datetime.now()
    # 全市场列表：工作日晚上跑（周末也可可选；默认工作日）
    if now.weekday() >= 5:
        return False
    try:
        hour = int(get_setting('stock', 'universe_refresh_hour', '18') or 18)
    except (TypeError, ValueError):
        hour = 18
    hour = max(0, min(23, hour))
    if now.hour != hour:
        return False
    if now.minute > 25:
        return False
    last = get_setting('stock', 'universe_last_refresh_date', '')
    today = now.strftime('%Y-%m-%d')
    return last != today


def _tick():
    if not _should_run_now():
        return
    with _lock:
        if not _should_run_now():
            return
        print(f'[UniverseScheduler] 全市场刷新 {datetime.now().isoformat(timespec="seconds")}')
        try:
            result = refresh_stock_universe(force_refresh=True)
            print(f'[UniverseScheduler] 完成: {result.get("message")}')
        except Exception as e:
            print(f'[UniverseScheduler] 失败: {e}')


def _loop():
    time.sleep(35)
    while True:
        try:
            _tick()
        except Exception as e:
            print(f'[UniverseScheduler] tick error: {e}')
        time.sleep(60)


def start_universe_scheduler():
    global _scheduler_started
    if _scheduler_started:
        return
    import os
    from config import FLASK_DEBUG
    if FLASK_DEBUG and os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        return
    _scheduler_started = True
    t = threading.Thread(target=_loop, name='universe-scheduler', daemon=True)
    t.start()
    print('[UniverseScheduler] 已启动（交易日默认 18 点同步全部 A 股）')
