"""运营管理助手：采热点 → 写文案 → 做视频（可执行工作流）。"""

from __future__ import annotations

import json
import re

from config import get_db as _db

from .base import BaseAssistant
from .prompts import DEFAULT_SYSTEM_PROMPTS
from .registry import register


class OperationsAssistant(BaseAssistant):
    key = 'operations'
    label = '运营管理助手'
    description = '采热点、写文案、做视频等日常运营重复操作'
    events = ('content.refresh', 'script.generate', 'video.create', 'manual')
    default_enabled = True
    has_board = True

    def run(self, **context) -> dict:
        task = (context.get('task') or '').strip()
        system_prompt = context.get('system_prompt') or ''
        if task == 'refresh_hotspots':
            return _task_refresh_hotspots()
        if task == 'generate_scripts':
            return _task_generate_scripts()
        if task == 'create_videos':
            return _task_create_videos()
        if task == 'daily_pipeline':
            return _task_daily_pipeline()
        # 默认：根据系统提示词给出下一步，并附带可执行任务说明
        return run_operations_assistant(
            trigger=context.get('trigger') or 'manual',
            system_prompt=system_prompt,
        )

    def board(self, **params) -> dict:
        return self.tasks()

    def tasks(self, **params) -> dict:
        return {
            'assistant': 'operations',
            'intro': '把「采热点 → 写文案 → 做视频」教给助手执行，减少手工重复操作。',
            'tasks': [
                {
                    'id': 'refresh_hotspots',
                    'title': '① 刷新内容情报',
                    'desc': '采集热点选题，找出可改编的口播素材',
                    'task': 'refresh_hotspots',
                    'runnable': True,
                    'secondary': {'label': '打开内容情报', 'path': '/hot-topics'},
                },
                {
                    'id': 'generate_scripts',
                    'title': '② 生成今日文案',
                    'desc': '按日更计划生成口播文案（可到文案中心修改）',
                    'task': 'generate_scripts',
                    'runnable': True,
                    'secondary': {'label': '打开文案中心', 'path': '/scripts'},
                },
                {
                    'id': 'create_videos',
                    'title': '③ 为文案创建视频',
                    'desc': '给已定稿/待制作的文案建视频任务并推进',
                    'task': 'create_videos',
                    'runnable': True,
                    'secondary': {'label': '打开视频中心', 'path': '/videos'},
                },
                {
                    'id': 'daily_pipeline',
                    'title': '一键日更（采写拍）',
                    'desc': '按系统日更配置串行执行：热点→文案→视频',
                    'task': 'daily_pipeline',
                    'runnable': True,
                },
            ],
        }


def _task_refresh_hotspots() -> dict:
    try:
        from modules.content_ops.daily_runner import refresh_intelligence
        res = refresh_intelligence(include_platforms=False)
        return {
            'assistant': 'operations',
            'task': 'refresh_hotspots',
            'summary': res.get('message') or '内容情报已刷新',
            'next_actions': ['去内容情报挑选可改编热点', '或继续执行「生成今日文案」'],
            'message': res.get('message') or '已刷新热点',
            'data': res,
        }
    except Exception as e:
        return {'assistant': 'operations', 'error': f'刷新热点失败: {e}'}


def _task_generate_scripts() -> dict:
    try:
        from modules.content_ops.daily_runner import generate_daily_scripts
        res = generate_daily_scripts()
        created = res.get('created') or []
        return {
            'assistant': 'operations',
            'task': 'generate_scripts',
            'summary': res.get('message') or f"已生成 {len(created)} 条文案",
            'next_actions': ['到文案中心检查润色', '满意后执行「为文案创建视频」'],
            'message': res.get('message') or f'文案完成 {len(created)} 条',
            'data': {'created': len(created), 'errors': res.get('errors')},
        }
    except Exception as e:
        return {'assistant': 'operations', 'error': f'生成文案失败: {e}'}


def _task_create_videos() -> dict:
    try:
        from modules.content_ops.daily_runner import enqueue_videos_for_scripts
        conn = _db()
        scripts = conn.execute(
            '''SELECT s.id FROM script s
               WHERE NOT EXISTS (SELECT 1 FROM video_task v WHERE v.script_id = s.id)
               ORDER BY s.created_at DESC LIMIT 5'''
        ).fetchall()
        conn.close()
        ids = [r['id'] for r in scripts]
        if not ids:
            return {
                'assistant': 'operations',
                'task': 'create_videos',
                'summary': '没有待建视频的文案',
                'next_actions': ['先执行「生成今日文案」', '或到文案中心确认状态'],
                'message': '暂无可建视频的文案',
            }
        res = enqueue_videos_for_scripts(ids, start_produce=True)
        if not isinstance(res, dict):
            res = {'message': str(res)}
        return {
            'assistant': 'operations',
            'task': 'create_videos',
            'summary': res.get('message') or f'已为 {len(ids)} 条文案创建视频任务',
            'next_actions': ['到视频中心查看进度', '完成后用发布管理助手发布'],
            'message': res.get('message') or f'视频任务 {len(ids)} 个',
            'data': res,
        }
    except Exception as e:
        return {'assistant': 'operations', 'error': f'创建视频失败: {e}'}


def _task_daily_pipeline() -> dict:
    try:
        from modules.content_ops.daily_runner import run_daily_pipeline
        res = run_daily_pipeline()
        if not isinstance(res, dict):
            res = {'message': str(res)}
        return {
            'assistant': 'operations',
            'task': 'daily_pipeline',
            'summary': res.get('message') or '日更流水线已执行',
            'next_actions': ['检查文案与视频结果', '完成后用发布管理助手发布'],
            'message': res.get('message') or '日更完成',
            'data': res,
        }
    except Exception as e:
        return {'assistant': 'operations', 'error': f'日更失败: {e}'}


def run_operations_assistant(trigger: str = 'manual', system_prompt: str = '', extra: dict | None = None) -> dict:
    tasks = OperationsAssistant().tasks()
    fallback = {
        'assistant': 'operations',
        'trigger': trigger,
        'summary': '按顺序执行：刷新情报 → 生成文案 → 创建视频',
        'next_actions': [t['title'] for t in (tasks.get('tasks') or [])[:3]],
        'talk_tips': '先选题再写稿，定稿后再开视频',
        'message': '请在 AI助手页点对应步骤的「执行」',
    }
    prompt = f"""根据你的职责，用简洁中文给出今天运营应优先做的 1～3 步。
可执行步骤：{json.dumps([t['title']+':'+t['desc'] for t in tasks.get('tasks') or []], ensure_ascii=False)}

只输出 JSON：
{{"summary":"一句话","next_actions":["动作1","动作2"],"talk_tips":"要点"}}"""
    try:
        from modules.ai.writer import call_llm
        sys_p = (system_prompt or '').strip() or DEFAULT_SYSTEM_PROMPTS['operations']
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
            'talk_tips': (data.get('talk_tips') or fallback['talk_tips']).strip(),
        }
    except Exception as e:
        return {**fallback, 'warning': str(e)}


register(OperationsAssistant())
