"""
日更定时调度：进程内守护线程，按设置的整点每天跑一次。

设置项（system）：
  daily_auto_enabled: true/false
  daily_run_hour: 0-23（默认 8）
  daily_last_run_date: YYYY-MM-DD（防同日重复）
"""

import threading
import time
from datetime import datetime

_scheduler_started = False
_lock = threading.Lock()


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
    # 整点后 10 分钟窗口内触发，避免漏跑
    if now.minute > 10:
        return False
    last = get_setting('system', 'daily_last_run_date', '')
    today = now.strftime('%Y-%m-%d')
    return last != today


def _tick():
    if not _should_run_now():
        return
    with _lock:
        if not _should_run_now():
            return
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


def _loop():
    # 启动后稍等，避免和 init_db 抢连接
    time.sleep(15)
    while True:
        try:
            _tick()
        except Exception as e:
            print(f'[DailyScheduler] tick error: {e}')
        time.sleep(60)


def start_daily_scheduler():
    """在主进程启动一次守护线程（Flask debug reloader 下只跑子进程）。"""
    global _scheduler_started
    if _scheduler_started:
        return
    import os
    from config import FLASK_DEBUG
    # debug reloader 会起父子双进程；只在真正服务请求的子进程启动
    if FLASK_DEBUG and os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        return
    _scheduler_started = True
    t = threading.Thread(target=_loop, name='daily-scheduler', daemon=True)
    t.start()
    print('[DailyScheduler] 已启动（每分钟检查；开启 daily_auto_enabled 后按整点执行）')
