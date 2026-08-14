"""
内容工作台：作品数据低频自动同步（只读创作者后台，不发私信）。

设置项（category=workbench）：
  sync_auto_enabled / sync_run_hour / sync_last_run / sync_last_run_date
"""

from __future__ import annotations

import threading
import time
from datetime import datetime

_lock = threading.Lock()


def _should_run_workbench_sync() -> bool:
    from config import get_setting

    enabled = str(get_setting('workbench', 'sync_auto_enabled', 'false')).lower() == 'true'
    if not enabled:
        return False
    try:
        hour = int(get_setting('workbench', 'sync_run_hour', '3') or 3)
    except (TypeError, ValueError):
        hour = 3
    hour = max(0, min(23, hour))
    now = datetime.now()
    if now.hour != hour or now.minute > 50:
        return False
    last = get_setting('workbench', 'sync_last_run_date', '')
    today = now.strftime('%Y-%m-%d')
    return last != today


def run_workbench_auto_sync() -> dict:
    """执行一次全平台作品同步（供调度与手动触发）。"""
    from config import get_db, update_setting
    from modules.publish.workbench import batch_sync_workbench

    conn = get_db()
    try:
        # 自动同步：每平台导入上限适中，避免长时间占满浏览器
        result = batch_sync_workbench(conn, platform='', limit=40)
    finally:
        conn.close()

    now = datetime.now()
    update_setting('workbench', 'sync_last_run_date', now.strftime('%Y-%m-%d'))
    update_setting('workbench', 'sync_last_run', now.strftime('%Y-%m-%d %H:%M:%S'))
    return result if isinstance(result, dict) else {'ok': True, 'message': '同步完成'}


def tick_workbench_sync():
    """由日更调度器每分钟调用。"""
    if not _should_run_workbench_sync():
        return
    with _lock:
        if not _should_run_workbench_sync():
            return
        print(f'[WorkbenchSync] 触发自动同步 {datetime.now().isoformat(timespec="seconds")}')
        try:
            result = run_workbench_auto_sync()
            ok = result.get('ok', True)
            msg = result.get('message') or ('完成' if ok else '失败')
            print(f'[WorkbenchSync] {msg}')
        except Exception as e:
            print(f'[WorkbenchSync] 失败: {e}')
            # 仍写入日期，避免同日窗口内反复打爆平台
            try:
                from config import update_setting
                now = datetime.now()
                update_setting('workbench', 'sync_last_run_date', now.strftime('%Y-%m-%d'))
                update_setting(
                    'workbench',
                    'sync_last_run',
                    f'{now.strftime("%Y-%m-%d %H:%M:%S")} error:{e}',
                )
            except Exception:
                pass
        # 平台间已在 scrape 内耗时；此处略歇，降低与其他任务叠加
        time.sleep(2)
