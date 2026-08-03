"""助手注册表与统一调度。"""

from __future__ import annotations

import json
from typing import Dict, Optional

from config import get_db as _db

from .base import BaseAssistant

_REGISTRY: Dict[str, BaseAssistant] = {}


def register(assistant: BaseAssistant) -> BaseAssistant:
    if not assistant.key:
        raise ValueError('assistant.key required')
    _REGISTRY[assistant.key] = assistant
    return assistant


def get_assistant(key: str) -> Optional[BaseAssistant]:
    return _REGISTRY.get(key)


def list_assistants() -> list:
    items = []
    for key, a in _REGISTRY.items():
        items.append({
            'key': a.key,
            'label': a.label,
            'description': a.description,
            'events': list(a.events),
            'default_enabled': a.default_enabled,
            'enabled': is_assistant_enabled(key),
            'has_board': bool(getattr(a, 'has_board', False)),
        })
    return items


def is_assistant_enabled(key: str) -> bool:
    """未配置对应 Agent 时：用助手 default_enabled；
    有配置时：config.enabled 优先，否则 status 非 disabled/off 即启用。
    """
    assistant = _REGISTRY.get(key)
    default = assistant.default_enabled if assistant else True
    try:
        conn = _db()
        row = conn.execute(
            'SELECT status, config_json FROM ai_agent WHERE agent_type=%s ORDER BY id DESC LIMIT 1',
            (key,),
        ).fetchone()
        conn.close()
        if not row:
            return default
        cfg = {}
        try:
            cfg = json.loads(row['config_json'] or '{}')
        except Exception:
            pass
        if 'enabled' in cfg:
            return bool(cfg['enabled'])
        return (row['status'] or '') not in ('disabled', 'off')
    except Exception:
        return default


def run_assistant(key: str, **context) -> dict:
    assistant = _REGISTRY.get(key)
    if not assistant:
        return {'error': f'unknown assistant: {key}'}
    if not is_assistant_enabled(key):
        return {'skipped': True, 'reason': f'{key} assistant disabled', 'assistant': key}
    result = assistant.run(**context) or {}
    if isinstance(result, dict) and 'assistant' not in result:
        result = {**result, 'assistant': key}
    return result
