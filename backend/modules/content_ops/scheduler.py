"""
日更定时调度：进程内守护线程，按设置的整点每天跑一次。

设置项（system）：
  daily_auto_enabled / daily_run_hour / daily_last_run_date
  stock_briefing_auto / stock_briefing_hour / stock_briefing_last_date
  （早间把财经新闻推送到股票情报页，不做微信推送）

另：内容工作台作品同步见 modules.publish.scheduler_sync（workbench.sync_*）
"""

import threading
import time
from datetime import datetime

_scheduler_started = False
_lock = threading.Lock()
_stock_lock = threading.Lock()


def _should_run_now():
    from config import get_setting
    enabled = str(get_setting('system', 'daily_auto_enabled', 'false')).lower() == 'true'
    if not enabled:
        return False
    try:
        hour = int(get_setting('system', 'daily_run_hour', '8') or 8)
    except (TypeError, ValueError):
        hour = 8
    hour = max(0, min(23, hour))
    now = datetime.now()
    if now.hour != hour:
        return False
    if now.minute > 10:
        return False
    last = get_setting('system', 'daily_last_run_date', '')
    today = now.strftime('%Y-%m-%d')
    return last != today


def _should_run_stock_briefing():
    from config import get_setting
    enabled = str(get_setting('system', 'stock_briefing_auto', 'false')).lower() == 'true'
    if not enabled:
        return False
    try:
        hour = int(get_setting('system', 'stock_briefing_hour', '8') or 8)
    except (TypeError, ValueError):
        hour = 8
    hour = max(0, min(23, hour))
    now = datetime.now()
    if now.hour != hour or now.minute > 10:
        return False
    last = get_setting('system', 'stock_briefing_last_date', '')
    today = now.strftime('%Y-%m-%d')
    return last != today


def _tick():
    if _should_run_now():
        with _lock:
            if _should_run_now():
                print(f'[DailyScheduler] 触发日更 {datetime.now().isoformat(timespec="seconds")}')
                try:
                    from modules.content_ops.daily_runner import run_daily_pipeline
                    result = run_daily_pipeline(
                        refresh=True,
                        include_platforms=False,
                        produce_video=True,
                    )
                    print(f'[DailyScheduler] 完成: {result.get("message")}')
                except Exception as e:
                    print(f'[DailyScheduler] 失败: {e}')

    if _should_run_stock_briefing():
        with _stock_lock:
            if _should_run_stock_briefing():
                print(
                    f'[DailyScheduler] 早间推送财经新闻到股票情报页 '
                    f'{datetime.now().isoformat(timespec="seconds")}'
                )
                try:
                    from modules.stocks.news import run_stock_briefing_job
                    result = run_stock_briefing_job()
                    print(f'[DailyScheduler] 财经新闻已推送到页面: {result}')
                except Exception as e:
                    print(f'[DailyScheduler] 财经新闻推送失败: {e}')

    try:
        from modules.publish.scheduler_sync import tick_workbench_sync
        tick_workbench_sync()
    except Exception as e:
        print(f'[DailyScheduler] workbench sync tick error: {e}')


def _loop():
    time.sleep(15)
    while True:
        try:
            _tick()
        except Exception as e:
            print(f'[DailyScheduler] tick error: {e}')
        time.sleep(60)


def start_daily_scheduler():
    global _scheduler_started
    if _scheduler_started:
        return
    import os
    from config import FLASK_DEBUG
    if FLASK_DEBUG and os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        return
    _scheduler_started = True
    t = threading.Thread(target=_loop, name='daily-scheduler', daemon=True)
    t.start()
    print('[DailyScheduler] 已启动（每分钟检查；日更 / 财经新闻 / 工作台作品同步按设置执行）')
