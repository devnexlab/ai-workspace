# -*- coding: utf-8 -*-
"""智仔专属定时任务：存储 + 进程内调度。"""

from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime
from typing import Any

from config import get_db

_scheduler_started = False
_lock = threading.Lock()


def ensure_pet_job_table(cur=None) -> None:
    """可在 init_db 或首次使用时调用。"""
    sql = '''CREATE TABLE IF NOT EXISTS pet_job (
        id SERIAL PRIMARY KEY,
        title TEXT DEFAULT '',
        action TEXT NOT NULL,
        enabled BOOLEAN DEFAULT TRUE,
        hour INTEGER,
        minute INTEGER DEFAULT 0,
        interval_hours INTEGER,
        params_json TEXT DEFAULT '{}',
        last_run_at TIMESTAMP,
        last_run_date TEXT DEFAULT '',
        last_result TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )'''
    if cur is not None:
        cur.execute(sql)
        return
    conn = get_db()
    try:
        conn.execute(sql)
        conn.commit()
    finally:
        conn.close()


def _schedule_label(hour, minute, interval_hours) -> str:
    if interval_hours:
        return f'每 {interval_hours} 小时'
    if hour is None:
        return '未设置'
    return f'每天 {int(hour):02d}:{int(minute or 0):02d}'


def _row_to_job(r) -> dict:
    d = dict(r)
    return {
        'id': d['id'],
        'title': d.get('title') or '',
        'action': d.get('action') or '',
        'enabled': bool(d.get('enabled')),
        'hour': d.get('hour'),
        'minute': d.get('minute') or 0,
        'interval_hours': d.get('interval_hours'),
        'schedule_label': _schedule_label(d.get('hour'), d.get('minute'), d.get('interval_hours')),
        'last_run_at': str(d.get('last_run_at') or ''),
        'last_result': d.get('last_result') or '',
        'params': _parse_params(d.get('params_json')),
    }


def _parse_params(raw) -> dict:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return {}


def list_jobs(include_paused: bool = False) -> list[dict]:
    ensure_pet_job_table()
    conn = get_db()
    try:
        if include_paused:
            rows = conn.execute(
                'SELECT * FROM pet_job ORDER BY id DESC'
            ).fetchall()
        else:
            rows = conn.execute(
                'SELECT * FROM pet_job WHERE enabled=TRUE ORDER BY id DESC'
            ).fetchall()
        return [_row_to_job(r) for r in rows]
    finally:
        conn.close()


def create_job(
    *,
    action: str,
    title: str = '',
    hour: int | None = None,
    minute: int = 0,
    interval_hours: int | None = None,
    params: dict | None = None,
) -> dict:
    ensure_pet_job_table()
    conn = get_db()
    try:
        cur = conn.execute(
            '''INSERT INTO pet_job
               (title, action, enabled, hour, minute, interval_hours, params_json)
               VALUES (%s,%s,TRUE,%s,%s,%s,%s)''',
            (
                title or action,
                action,
                hour,
                minute or 0,
                interval_hours,
                json.dumps(params or {}, ensure_ascii=False),
            ),
        )
        conn.commit()
        jid = cur.lastrowid
        row = conn.execute('SELECT * FROM pet_job WHERE id=%s', (jid,)).fetchone()
        return _row_to_job(row)
    finally:
        conn.close()


def pause_all_jobs() -> int:
    ensure_pet_job_table()
    conn = get_db()
    try:
        cur = conn.execute('UPDATE pet_job SET enabled=FALSE, updated_at=CURRENT_TIMESTAMP WHERE enabled=TRUE')
        conn.commit()
        return cur.rowcount if hasattr(cur, 'rowcount') else 0
    finally:
        conn.close()


def pause_jobs_by_action(action: str) -> int:
    ensure_pet_job_table()
    conn = get_db()
    try:
        cur = conn.execute(
            '''UPDATE pet_job SET enabled=FALSE, updated_at=CURRENT_TIMESTAMP
               WHERE action=%s AND enabled=TRUE''',
            (action,),
        )
        conn.commit()
        return cur.rowcount if hasattr(cur, 'rowcount') else 0
    finally:
        conn.close()


def parse_schedule_from_text(text: str) -> dict[str, Any] | None:
    """从中文指令解析定时计划。"""
    q = text or ''

    action = 'daily_pipeline'
    title = '定时日更出片'
    if any(k in q for k in ('同步发布', '同步数据', '平台数据', '同步视频号', '同步抖音')):
        action = 'publish_overview'
        title = '定时查看发布数据'
    elif any(k in q for k in ('股票简报', '财经新闻', '早间简报')):
        action = 'stock_briefing'
        title = '定时股票情报'
    elif any(k in q for k in ('日更', '出片', '采热点', '写文案')):
        action = 'daily_pipeline'
        title = '定时日更出片'
    else:
        # 仅「每天X点」且无明确动作时，默认日更
        if not re.search(r'每天|每\s*\d+\s*小时|每小时', q):
            return None

    # 每 N 小时
    m_iv = re.search(r'每\s*(\d+)\s*小时', q) or re.search(r'每隔\s*(\d+)\s*小时', q)
    if m_iv or '每小时' in q or '每两小时' in q or '每2小时' in q:
        if '每两小时' in q or '每2小时' in q:
            iv = 2
        elif '每小时' in q and not m_iv:
            iv = 1
        else:
            iv = int(m_iv.group(1))
        iv = max(1, min(24, iv))
        return {
            'action': action,
            'title': title,
            'interval_hours': iv,
            'hour': None,
            'minute': 0,
            'params': {},
        }

    # 每天 HH 点
    hour = None
    minute = 0
    m = re.search(r'(\d{1,2})\s*点\s*(\d{1,2})?\s*分?', q)
    if m:
        hour = int(m.group(1))
        if m.group(2):
            minute = int(m.group(2))
    if '晚上' in q or '今晚' in q:
        if hour is None:
            hour = 21
        elif hour < 12:
            hour += 12
    elif '中午' in q and hour is None:
        hour = 12
    elif '下午' in q:
        if hour is None:
            hour = 14
        elif hour < 12:
            hour += 12
    elif ('早上' in q or '上午' in q) and hour is None:
        hour = 8
    if hour is None and '每天' not in q:
        return None
    if hour is None:
        hour = 8
    hour = max(0, min(23, hour))
    minute = max(0, min(59, minute))

    return {
        'action': action,
        'title': f'{title}（每天{hour:02d}:{minute:02d}）',
        'hour': hour,
        'minute': minute,
        'interval_hours': None,
        'params': {},
    }


def _mark_run(job_id: int, result: str) -> None:
    conn = get_db()
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        conn.execute(
            '''UPDATE pet_job SET last_run_at=CURRENT_TIMESTAMP, last_run_date=%s,
               last_result=%s, updated_at=CURRENT_TIMESTAMP WHERE id=%s''',
            (today, (result or '')[:500], job_id),
        )
        conn.commit()
    finally:
        conn.close()


def _should_run(job: dict, now: datetime) -> bool:
    if not job.get('enabled'):
        return False
    iv = job.get('interval_hours')
    if iv:
        last = job.get('last_run_at') or ''
        if not last:
            return True
        try:
            # last may be '2026-08-13 10:00:00'
            last_dt = datetime.strptime(str(last)[:19], '%Y-%m-%d %H:%M:%S')
        except Exception:
            return True
        return (now - last_dt).total_seconds() >= int(iv) * 3600 - 30

    hour = job.get('hour')
    if hour is None:
        return False
    minute = int(job.get('minute') or 0)
    if now.hour != int(hour):
        return False
    # 整点窗口 10 分钟内
    if now.minute < minute or now.minute > minute + 10:
        return False
    today = now.strftime('%Y-%m-%d')
    return (job.get('last_run_date') or '') != today


def _execute_action(action: str, params: dict | None = None) -> str:
    params = params or {}
    if action == 'daily_pipeline':
        from modules.content_ops.daily_runner import run_daily_pipeline
        r = run_daily_pipeline(
            refresh=True,
            include_platforms=False,
            produce_video=params.get('produce_video', True),
        )
        return r.get('message') or '日更完成'
    if action == 'stock_briefing':
        from modules.stocks.news import run_stock_briefing_job
        r = run_stock_briefing_job()
        return str(r.get('message') or r)[:300]
    if action == 'publish_overview':
        from modules.pet.tools_ops import tool_list_publish_overview
        _c, text = tool_list_publish_overview(5)
        return text[:400]
    return f'未知动作: {action}'


def run_due_jobs() -> list[dict]:
    ensure_pet_job_table()
    now = datetime.now()
    jobs = list_jobs(include_paused=False)
    ran = []
    for job in jobs:
        if not _should_run(job, now):
            continue
        with _lock:
            # re-check
            fresh = [j for j in list_jobs(include_paused=False) if j['id'] == job['id']]
            if not fresh or not _should_run(fresh[0], datetime.now()):
                continue
            try:
                result = _execute_action(job['action'], job.get('params'))
                _mark_run(job['id'], result)
                ran.append({'id': job['id'], 'ok': True, 'result': result})
                print(f'[PetJob] #{job["id"]} {job["action"]} ok: {result[:120]}')
            except Exception as e:
                _mark_run(job['id'], f'失败: {e}')
                ran.append({'id': job['id'], 'ok': False, 'result': str(e)})
                print(f'[PetJob] #{job["id"]} failed: {e}')
    return ran


def _loop():
    time.sleep(20)
    while True:
        try:
            run_due_jobs()
        except Exception as e:
            print(f'[PetJob] tick error: {e}')
        time.sleep(60)


def start_pet_job_scheduler():
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True
    try:
        ensure_pet_job_table()
    except Exception as e:
        print(f'[PetJob] table init: {e}')
    t = threading.Thread(target=_loop, name='pet-job-scheduler', daemon=True)
    t.start()
    print('[PetJob] scheduler started')
