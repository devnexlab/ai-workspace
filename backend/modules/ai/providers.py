"""
AI 大模型多厂商配置（卡片启用）。

内置厂商 + 数据库自定义厂商；统一使用 API Key（Bearer）。
"""

from __future__ import annotations

import re

AI_LLM_PROVIDERS = [
    {
        'key': 'zhipu',
        'label': '智谱 GLM',
        'desc': 'glm-4-flash 等，性价比高',
        'category': 'ai_zhipu',
        'color': 'blue',
        'builtin': True,
        'recommended': True,
        'default_base_url': 'https://open.bigmodel.cn/api/paas/v4',
        'default_model': 'glm-4-flash',
        'model_hint': '如 glm-4-flash、glm-4',
        'key_hint': '开放平台 API Key',
    },
    {
        'key': 'volcano',
        'label': '火山引擎',
        'desc': '方舟豆包，模型名填接入点 ep-xxx',
        'category': 'ai_volcano',
        'color': 'orange',
        'builtin': True,
        'default_base_url': 'https://ark.cn-beijing.volces.com/api/v3',
        'default_model': '',
        'model_hint': '推理接入点 ID，形如 ep-xxxxxxxx',
        'key_hint': '方舟 ARK_API_KEY',
    },
    {
        'key': 'qwen',
        'label': '通义千问',
        'desc': '阿里云 DashScope',
        'category': 'ai_qwen',
        'color': 'purple',
        'builtin': True,
        'default_base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
        'default_model': 'qwen-plus',
        'model_hint': '如 qwen-plus、qwen-turbo',
        'key_hint': 'DashScope API Key',
    },
    {
        'key': 'deepseek',
        'label': 'DeepSeek',
        'desc': '深度求索',
        'category': 'ai_deepseek',
        'color': 'cyan',
        'builtin': True,
        'default_base_url': 'https://api.deepseek.com/v1',
        'default_model': 'deepseek-chat',
        'model_hint': '如 deepseek-chat',
        'key_hint': 'DeepSeek API Key',
    },
    {
        'key': 'moonshot',
        'label': 'Moonshot',
        'desc': '月之暗面 Kimi',
        'category': 'ai_moonshot',
        'color': 'geekblue',
        'builtin': True,
        'default_base_url': 'https://api.moonshot.cn/v1',
        'default_model': 'moonshot-v1-8k',
        'model_hint': '如 moonshot-v1-8k',
        'key_hint': 'Moonshot API Key',
    },
    {
        'key': 'openai',
        'label': 'OpenAI / ChatGPT',
        'desc': '官方 GPT：填 platform.openai.com 的 sk- API Key',
        'category': 'ai_openai',
        'color': 'green',
        'builtin': True,
        'default_base_url': 'https://api.openai.com/v1',
        'default_model': 'gpt-4o-mini',
        'model_hint': '如 gpt-4o-mini、gpt-4o',
        'key_hint': 'OpenAI API Key（sk- 开头）',
    },
]

_RESERVED_KEYS = {p['key'] for p in AI_LLM_PROVIDERS} | {'common', 'rules', 'ai', 'codex'}


def _truthy(v) -> bool:
    return str(v or '').lower() in ('1', 'true', 'yes', 'on')


def _row_to_provider(row) -> dict:
    r = dict(row)
    key = r['key']
    return {
        'key': key,
        'label': r.get('label') or key,
        'desc': r.get('description') or '',
        'category': f'ai_{key}',
        'color': r.get('color') or 'blue',
        'builtin': False,
        'default_base_url': r.get('default_base_url') or '',
        'default_model': r.get('default_model') or '',
        'model_hint': r.get('model_hint') or '模型名称',
        'key_hint': 'API Key',
    }


def _load_custom_providers() -> list[dict]:
    try:
        from config import get_db
        conn = get_db()
        rows = conn.execute(
            'SELECT * FROM ai_llm_provider ORDER BY id'
        ).fetchall()
        conn.close()
        return [_row_to_provider(r) for r in rows]
    except Exception:
        return []


def list_ai_providers():
    customs = _load_custom_providers()
    custom_keys = {c['key'] for c in customs}
    builtins = [dict(p) for p in AI_LLM_PROVIDERS if p['key'] not in custom_keys]
    return builtins + customs


_provider_list_cache = None
_provider_list_ts = 0.0


def list_ai_providers_cached(ttl: float = 2.0):
    global _provider_list_cache, _provider_list_ts
    import time
    now = time.time()
    if _provider_list_cache is not None and (now - _provider_list_ts) < ttl:
        return _provider_list_cache
    _provider_list_cache = list_ai_providers()
    _provider_list_ts = now
    return _provider_list_cache


def provider_meta(key: str) -> dict | None:
    key = (key or '').strip().lower()
    aliases = {
        'volcengine': 'volcano', 'doubao': 'volcano', 'ark': 'volcano', 'huoshan': 'volcano',
        'chatgpt': 'openai', 'gpt': 'openai',
    }
    key = aliases.get(key, key)
    for p in list_ai_providers_cached():
        if p['key'] == key:
            return p
    return None


def _seed_provider_settings(conn, meta: dict):
    """为厂商 category 写入默认 system_setting（已存在则跳过）。"""
    cat = meta['category']
    rows = [
        (cat, 'enabled', 'false', f"启用{meta['label']}", '开启后作为当前大模型', 'select', '["true","false"]', 1),
        (cat, 'api_key', '', 'API Key', meta.get('key_hint') or 'API Key', 'password', None, 2),
        (cat, 'base_url', meta.get('default_base_url') or '', 'API Base URL',
         'OpenAI 兼容接口根地址，一般以 /v1 或 /api/v3 结尾', 'text', None, 3),
        (cat, 'model', meta.get('default_model') or '', '模型名称',
         meta.get('model_hint') or '模型名或接入点 ID', 'text', None, 4),
    ]
    for item in rows:
        conn.execute(
            '''INSERT INTO system_setting
               (category, key, value, label, description, field_type, options, sort_order)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (category, key) DO NOTHING''',
            item,
        )


def ensure_builtin_settings():
    """启动时确保内置厂商配置项存在，并清理已废弃的 Codex 配置。"""
    from config import get_db
    conn = get_db()
    try:
        for p in AI_LLM_PROVIDERS:
            _seed_provider_settings(conn, p)
        for p in _load_custom_providers():
            _seed_provider_settings(conn, p)

        # 移除已废弃的「中转账号密码 / Codex」
        conn.execute('DELETE FROM system_setting WHERE category=?', ('ai_codex',))
        try:
            conn.execute('DELETE FROM ai_llm_provider WHERE key=?', ('codex',))
        except Exception:
            pass

        conn.execute(
            '''UPDATE system_setting SET label=%s, description=%s
               WHERE category=%s AND key=%s''',
            (
                '启用 OpenAI / ChatGPT',
                '官方 GPT：使用 platform.openai.com 的 API Key（sk-）',
                'ai_openai', 'enabled',
            ),
        )
        conn.execute(
            '''UPDATE system_setting SET description=%s
               WHERE category=%s AND key=%s''',
            (
                'sk- 开头的 API Key',
                'ai_openai', 'api_key',
            ),
        )
        # 隐藏旧的账号密码字段（若仍存在）
        for cat_prefix in ('ai_',):
            conn.execute(
                '''DELETE FROM system_setting
                   WHERE category LIKE %s AND key IN ('username', 'password', 'auth_type')''',
                (f'{cat_prefix}%',),
            )
        conn.commit()
    finally:
        conn.close()


def create_provider(data: dict) -> dict:
    key = (data.get('key') or '').strip().lower()
    if not re.match(r'^[a-z][a-z0-9_]{1,31}$', key):
        raise ValueError('标识须小写字母开头，仅 a-z/0-9/_，2-32 位')
    if key in _RESERVED_KEYS or key.startswith('ai_'):
        raise ValueError('该标识为系统保留，请换一个')
    label = (data.get('label') or '').strip()
    if not label:
        raise ValueError('请填写显示名称')
    base_url = (data.get('default_base_url') or data.get('base_url') or '').strip()
    model = (data.get('default_model') or data.get('model') or '').strip()

    from config import get_db
    conn = get_db()
    try:
        exists = conn.execute('SELECT id FROM ai_llm_provider WHERE key=?', (key,)).fetchone()
        if exists:
            raise ValueError('该标识已存在')
        if any(p['key'] == key for p in AI_LLM_PROVIDERS):
            raise ValueError('与内置厂商重名')
        conn.execute(
            '''INSERT INTO ai_llm_provider
               (key, label, description, color, auth_type, default_base_url, default_model, model_hint)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)''',
            (
                key,
                label,
                (data.get('desc') or data.get('description') or '').strip(),
                data.get('color') or 'blue',
                'api_key',
                base_url,
                model,
                (data.get('model_hint') or '').strip(),
            ),
        )
        meta = {
            'key': key,
            'label': label,
            'category': f'ai_{key}',
            'default_base_url': base_url,
            'default_model': model,
            'model_hint': data.get('model_hint') or '',
            'key_hint': 'API Key',
        }
        _seed_provider_settings(conn, meta)
        conn.commit()
        return provider_meta(key)
    finally:
        conn.close()


def delete_provider(key: str):
    key = (key or '').strip().lower()
    if key in _RESERVED_KEYS or any(p['key'] == key for p in AI_LLM_PROVIDERS):
        raise ValueError('内置厂商不能删除')
    from config import get_db
    conn = get_db()
    try:
        row = conn.execute('SELECT id FROM ai_llm_provider WHERE key=?', (key,)).fetchone()
        if not row:
            raise ValueError('未找到该厂商')
        conn.execute('DELETE FROM ai_llm_provider WHERE key=?', (key,))
        conn.execute('DELETE FROM system_setting WHERE category=?', (f'ai_{key}',))
        conn.commit()
    finally:
        conn.close()


def channel_status(key: str) -> dict:
    from config import get_setting

    meta = provider_meta(key)
    if not meta:
        return {'key': key, 'enabled': False, 'ready': False, 'message': '未知服务商', 'path': '/settings/ai'}
    cat = meta['category']
    enabled = _truthy(get_setting(cat, 'enabled', 'false'))
    api_key = (get_setting(cat, 'api_key', '') or '').strip()
    model = (get_setting(cat, 'model', '') or '').strip() or (meta.get('default_model') or '')

    if key == 'volcano':
        ready_cred = bool(api_key and model)
        miss = '待配 Key/模型'
    else:
        ready_cred = bool(api_key)
        miss = '待配 API Key'
    has_cred = bool(api_key)

    if enabled and ready_cred:
        message = f'已启用 · {meta["label"]}'
    elif enabled:
        message = f'已启用但{miss}'
    elif has_cred:
        message = '已填凭证，未启用'
    else:
        message = '未配置'
    return {
        'key': key,
        'enabled': enabled,
        'ready': enabled and ready_cred,
        'message': message,
        'label': meta['label'],
        'path': '/settings/ai',
    }


def resolve_ai_config() -> dict:
    """返回当前启用厂商的配置（供 call_llm 使用）。"""
    from config import get_setting, get_settings_by_category

    shared = get_settings_by_category('ai') or {}
    providers = list_ai_providers()

    active = None
    for p in providers:
        if _truthy(get_setting(p['category'], 'enabled', 'false')):
            active = p
            break

    if active:
        cat = active['category']
        return {
            'provider': active['key'],
            'api_key': (get_setting(cat, 'api_key', '') or '').strip(),
            'base_url': (get_setting(cat, 'base_url', '') or '').strip() or (active.get('default_base_url') or ''),
            'model': (get_setting(cat, 'model', '') or '').strip() or (active.get('default_model') or ''),
            'temperature': shared.get('temperature', '0.7'),
            'max_tokens': shared.get('max_tokens', '2000'),
            'default_audience': shared.get('default_audience', ''),
            'default_tone': shared.get('default_tone', 'casual'),
        }

    legacy_provider = (shared.get('provider') or 'zhipu').strip().lower()
    meta = provider_meta(legacy_provider) or AI_LLM_PROVIDERS[0]
    return {
        'provider': meta['key'],
        'api_key': (shared.get('api_key') or '').strip(),
        'base_url': (shared.get('base_url') or '').strip() or meta['default_base_url'],
        'model': (shared.get('model') or '').strip() or (meta.get('default_model') or ''),
        'temperature': shared.get('temperature', '0.7'),
        'max_tokens': shared.get('max_tokens', '2000'),
        'default_audience': shared.get('default_audience', ''),
        'default_tone': shared.get('default_tone', 'casual'),
    }
