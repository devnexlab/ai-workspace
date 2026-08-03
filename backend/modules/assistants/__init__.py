"""多助手框架：统一注册、开关与调度。

现阶段三类：客户管理 / 运营管理 / 发布管理。
Agent 中心创建对应类型后，会在「AI助手」页展示。
"""

from __future__ import annotations

from .base import BaseAssistant
from .registry import (
    get_assistant,
    is_assistant_enabled,
    list_assistants,
    register,
    run_assistant,
)

from . import customer as _customer  # noqa: F401
from . import operations as _operations  # noqa: F401
from . import publish as _publish  # noqa: F401

CORE_ASSISTANT_TYPES = ('customer', 'operations', 'publish')

__all__ = [
    'BaseAssistant',
    'CORE_ASSISTANT_TYPES',
    'get_assistant',
    'is_assistant_enabled',
    'list_assistants',
    'register',
    'run_assistant',
    'ensure_default_agents',
    'list_ai_assistants',
]


def ensure_default_agents():
    """确保三个核心 Agent 各有一条记录（幂等）。"""
    from config import get_db as _db
    from .registry import get_assistant as _get
    from .prompts import DEFAULT_SYSTEM_PROMPTS

    defaults = [
        ('customer', '客户管理助手'),
        ('operations', '运营管理助手'),
        ('publish', '发布管理助手'),
    ]
    conn = _db()
    try:
        for key, name in defaults:
            exist = conn.execute(
                'SELECT id, system_prompt FROM ai_agent WHERE agent_type=%s LIMIT 1', (key,)
            ).fetchone()
            if exist:
                old = (exist.get('system_prompt') or '').strip()
                new_prompt = DEFAULT_SYSTEM_PROMPTS.get(key, '')
                # 空提示词，或仍是旧版短提示（不含每日节奏），自动升级为专业默认
                if (not old) or ('每日' not in old and len(old) < 180):
                    conn.execute(
                        'UPDATE ai_agent SET system_prompt=%s WHERE id=%s',
                        (new_prompt, exist['id']),
                    )
                continue
            meta = _get(key)
            desc = meta.description if meta else ''
            conn.execute(
                '''INSERT INTO ai_agent (name, agent_type, description, config_json, system_prompt, status)
                   VALUES (%s, %s, %s, %s, %s, 'idle')''',
                (name, key, desc, '{}', DEFAULT_SYSTEM_PROMPTS.get(key, '')),
            )
        content_row = conn.execute(
            "SELECT id FROM ai_agent WHERE agent_type='content' LIMIT 1"
        ).fetchone()
        ops_row = conn.execute(
            "SELECT id FROM ai_agent WHERE agent_type='operations' LIMIT 1"
        ).fetchone()
        if content_row and not ops_row:
            conn.execute(
                '''UPDATE ai_agent
                   SET agent_type='operations', name=%s, description=%s, system_prompt=%s
                   WHERE id=%s''',
                (
                    '运营管理助手',
                    (_get('operations').description if _get('operations') else ''),
                    DEFAULT_SYSTEM_PROMPTS.get('operations', ''),
                    content_row['id'],
                ),
            )
        conn.commit()
    finally:
        conn.close()


def list_ai_assistants():
    """AI助手页数据源：Agent 中心已创建的助手（按核心类型）。"""
    from config import get_db as _db
    from .prompts import extract_system_prompt

    ensure_default_agents()
    conn = _db()
    rows = conn.execute(
        '''SELECT * FROM ai_agent
           WHERE agent_type IN ('customer', 'operations', 'publish')
           ORDER BY
             CASE agent_type
               WHEN 'customer' THEN 1
               WHEN 'operations' THEN 2
               WHEN 'publish' THEN 3
               ELSE 9
             END,
             id ASC'''
    ).fetchall()
    conn.close()

    result = []
    for row in rows:
        agent = dict(row)
        key = agent.get('agent_type') or ''
        meta = get_assistant(key)
        result.append({
            'id': agent['id'],
            'name': agent.get('name') or (meta.label if meta else key),
            'agent_type': key,
            'label': (meta.label if meta else agent.get('name') or key),
            'description': agent.get('description') or (meta.description if meta else ''),
            'system_prompt': extract_system_prompt(agent, key),
            'status': agent.get('status') or 'idle',
            'last_run': str(agent.get('last_run') or ''),
            'last_result': agent.get('last_result') or '',
            'created_at': str(agent.get('created_at') or ''),
            'enabled': is_assistant_enabled(key) and (agent.get('status') or '') not in ('disabled', 'off'),
            'has_board': bool(meta and meta.has_board),
            'registered': meta is not None,
        })
    return result
