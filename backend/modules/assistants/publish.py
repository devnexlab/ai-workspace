"""发布管理助手：待发布 / 失败重试 / 为成片建发布任务。"""

from __future__ import annotations

import json
import re

from config import get_db as _db

from .base import BaseAssistant
from .prompts import DEFAULT_SYSTEM_PROMPTS
from .registry import register


class PublishAssistant(BaseAssistant):
    key = 'publish'
    label = '发布管理助手'
    description = '创建发布、失败重试、多平台发布等重复操作'
    events = ('publish.create', 'publish.fail', 'publish.success', 'manual')
    default_enabled = True
    has_board = True

    def run(self, **context) -> dict:
        task = (context.get('task') or '').strip()
        system_prompt = context.get('system_prompt') or ''
        if task == 'create_from_ready':
            return _task_create_from_ready()
        if task.startswith('retry:'):
            try:
                tid = int(task.split(':', 1)[1])
            except Exception:
                return {'error': 'invalid retry task id'}
            return _task_retry_publish(tid)
        if task.startswith('publish:'):
            try:
                tid = int(task.split(':', 1)[1])
            except Exception:
                return {'error': 'invalid publish task id'}
            return _task_do_publish(tid)
        return run_publish_assistant(trigger=context.get('trigger') or 'manual', system_prompt=system_prompt)

    def board(self, **params) -> dict:
        return self.tasks()

    def tasks(self, **params) -> dict:
        conn = _db()
        tasks = []
        try:
            ready = conn.execute(
                '''SELECT v.id, v.title FROM video_task v
                   WHERE v.export_status='done'
                     AND NOT EXISTS (SELECT 1 FROM publish_task p WHERE p.video_task_id=v.id)
                   ORDER BY v.created_at DESC LIMIT 8'''
            ).fetchall()
            failed = conn.execute(
                '''SELECT id, title, platform, error_msg, status FROM publish_task
                   WHERE status IN ('failed','error')
                   ORDER BY created_at DESC LIMIT 8'''
            ).fetchall()
            pending = conn.execute(
                '''SELECT id, title, platform, status FROM publish_task
                   WHERE status IN ('pending','scheduled','queued')
                   ORDER BY created_at DESC LIMIT 8'''
            ).fetchall()
        finally:
            conn.close()

        tasks.append({
            'id': 'create_from_ready',
            'title': '为已完成视频创建发布任务',
            'desc': f'当前有 {len(ready)} 个成片尚未建发布任务' if ready else '暂无待建发布的成片',
            'task': 'create_from_ready',
            'runnable': bool(ready),
            'secondary': {'label': '打开发布中心', 'path': '/publish'},
        })
        for r in failed:
            d = dict(r)
            title = d.get('title') or f"任务#{d['id']}"
            tasks.append({
                'id': f"retry:{d['id']}",
                'title': f"重试失败发布：{title}",
                'desc': f"{d.get('platform') or ''} · {d.get('error_msg') or '发布失败'}",
                'task': f"retry:{d['id']}",
                'runnable': True,
                'secondary': {'label': '打开发布中心', 'path': '/publish'},
            })
        for r in pending:
            d = dict(r)
            title = d.get('title') or f"任务#{d['id']}"
            tasks.append({
                'id': f"publish:{d['id']}",
                'title': f"执行发布：{title}",
                'desc': f"{d.get('platform') or '未选平台'} · 状态 {d.get('status')}",
                'task': f"publish:{d['id']}",
                'runnable': True,
                'secondary': {'label': '打开发布中心', 'path': '/publish'},
            })

        return {
            'assistant': 'publish',
            'intro': '把建发布任务、失败重试、点开发布等重复操作交给助手。',
            'tasks': tasks,
        }


def _task_create_from_ready() -> dict:
    conn = _db()
    ready = conn.execute(
        '''SELECT v.id, v.title FROM video_task v
           WHERE v.export_status='done'
             AND NOT EXISTS (SELECT 1 FROM publish_task p WHERE p.video_task_id=v.id)
           ORDER BY v.created_at DESC LIMIT 5'''
    ).fetchall()
    created = []
    for v in ready:
        cur = conn.execute(
            '''INSERT INTO publish_task (video_task_id, title, platform, status)
               VALUES (%s, %s, '', 'pending')''',
            (v['id'], v['title'] or f"发布-{v['id']}"),
        )
        created.append(cur.lastrowid)
    conn.commit()
    conn.close()
    return {
        'assistant': 'publish',
        'task': 'create_from_ready',
        'summary': f'已创建 {len(created)} 个发布任务（请到发布中心补全平台后发布）',
        'next_actions': ['在发布中心选择平台', '再点对应任务的「执行发布」'],
        'message': f'新建发布任务 {len(created)} 个',
        'data': {'ids': created},
    }


def _task_retry_publish(task_id: int) -> dict:
    conn = _db()
    conn.execute(
        "UPDATE publish_task SET status='pending', error_msg='' WHERE id=%s",
        (task_id,),
    )
    conn.commit()
    conn.close()
    return _task_do_publish(task_id)


def _task_do_publish(task_id: int) -> dict:
    try:
        from config import get_setting
        from modules.content_ops.platforms import get_platform

        mode = (get_setting('publish', 'mode', 'manual') or 'manual').lower()
        conn = _db()
        task = conn.execute(
            '''SELECT p.*, v.output_path, v.title as video_title FROM publish_task p
               LEFT JOIN video_task v ON p.video_task_id=v.id WHERE p.id=%s''',
            (task_id,),
        ).fetchone()
        if not task:
            conn.close()
            return {'error': 'publish task not found'}
        t = dict(task)
        if not t.get('platform'):
            conn.close()
            return {
                'assistant': 'publish',
                'summary': '请先在发布中心为该任务选择平台',
                'next_actions': ['打开发布中心补全平台后再执行'],
                'message': '缺少发布平台',
            }
        if not t.get('output_path'):
            conn.close()
            return {'error': '视频成片路径为空，无法发布'}

        # 默认安全模式：不启动自动化浏览器
        if mode != 'autofill':
            meta = get_platform(t['platform']) or {}
            label = meta.get('label') or t['platform']
            creator_url = meta.get('creator_url') or ''
            conn.execute(
                "UPDATE publish_task SET status='reviewing', error_msg=%s WHERE id=%s",
                (
                    f'请到发布中心点「准备发布」：复制文案并打开{label}官方页，手动上传点发表后确认',
                    task_id,
                ),
            )
            conn.commit()
            conn.close()
            msg = f'已标记待确认。请打开发布中心对任务 #{task_id} 点「准备发布」（安全模式，避免封号）'
            return {
                'assistant': 'publish',
                'task': f'publish:{task_id}',
                'summary': msg,
                'next_actions': ['打开发布中心 → 准备发布', '在平台点发表后确认已发'],
                'message': msg,
                'data': {'creator_url': creator_url, 'mode': 'manual'},
            }

        from modules.publisher import publish_video
        result = publish_video(
            platform=t['platform'],
            video_path=t['output_path'],
            title=t.get('title') or '',
            description=t.get('description') or '',
            tags=t.get('tags') or '',
            cover_text=t.get('cover_text') or '',
            task_id=task_id,
        )
        status = (result or {}).get('status')
        sid = (result or {}).get('session_id') or ''
        if status == 'pending_review':
            conn.execute(
                "UPDATE publish_task SET status='reviewing', error_msg=%s, session_id=%s WHERE id=%s",
                ((result or {}).get('message') or '', sid, task_id),
            )
            msg = (result or {}).get('message') or '已打开发布页，请在浏览器中确认发布'
        elif status == 'error':
            conn.execute(
                "UPDATE publish_task SET status='failed', error_msg=%s WHERE id=%s",
                ((result or {}).get('message') or '发布失败', task_id),
            )
            msg = (result or {}).get('message') or '发布失败'
        else:
            conn.execute(
                "UPDATE publish_task SET status=%s, error_msg=%s WHERE id=%s",
                (status or 'pending', (result or {}).get('message') or '', task_id),
            )
            msg = (result or {}).get('message') or '发布流程已启动'
        conn.commit()
        conn.close()
        return {
            'assistant': 'publish',
            'task': f'publish:{task_id}',
            'summary': msg,
            'next_actions': ['在打开发布页中确认提交'] if status == 'pending_review' else ['查看发布中心状态'],
            'message': msg,
            'data': result if isinstance(result, dict) else {},
        }
    except Exception as e:
        return {'assistant': 'publish', 'error': f'发布失败: {e}'}


def run_publish_assistant(trigger: str = 'manual', system_prompt: str = '') -> dict:
    tasks = PublishAssistant().tasks()
    fallback = {
        'assistant': 'publish',
        'trigger': trigger,
        'summary': '优先处理失败发布，再为成片建任务并发布',
        'next_actions': [t['title'] for t in (tasks.get('tasks') or [])[:3]],
        'message': '请在 AI助手页点具体任务的「执行」',
    }
    prompt = f"""给出今天发布应优先做的 1～3 步。
当前任务：{json.dumps([t['title'] for t in (tasks.get('tasks') or [])[:10]], ensure_ascii=False)}
只输出 JSON：{{"summary":"...","next_actions":["..."],"talk_tips":"..."}}"""
    try:
        from modules.ai_writer import call_llm
        sys_p = (system_prompt or '').strip() or DEFAULT_SYSTEM_PROMPTS['publish']
        if 'JSON' not in sys_p and 'json' not in sys_p:
            sys_p = sys_p + ' 只输出合法 JSON。'
        resp, _tokens, _model = call_llm(prompt, system_prompt=sys_p, temperature=0.3, max_tokens=600)
        match = re.search(r'\{[\s\S]*\}', resp or '')
        if not match:
            return fallback
        data = json.loads(match.group())
        actions = data.get('next_actions') or fallback['next_actions']
        if isinstance(actions, str):
            actions = [actions]
        return {
            **fallback,
            'summary': (data.get('summary') or fallback['summary']).strip(),
            'next_actions': [str(a).strip() for a in actions if str(a).strip()][:3],
            'talk_tips': (data.get('talk_tips') or '').strip(),
        }
    except Exception as e:
        return {**fallback, 'warning': str(e)}


register(PublishAssistant())
