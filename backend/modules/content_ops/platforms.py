"""
内容运营 - 可插拔采集/发布平台注册表。

内置平台 + 数据库 ops_platform 自定义平台合并。
前端可添加平台：写入 DB 并自动种子 collector_/publish_ 设置项。
"""

import re

# 内置平台（有专用 Playwright 采集/发布实现）
BUILTIN_PLATFORMS = [
    {
        'key': 'shipinhao',
        'label': '视频号',
        'color': 'green',
        'priority': 1,
        'desc': '主阵地，微信生态口播与熟人转发（仅发布：选题走全网热榜，勿用自动化登录采集）',
        'cookie_domain': '.qq.com',
        'creator_url': 'https://channels.weixin.qq.com/platform/post/create',
        'search_url_template': '',
        # 微信未开放视频号内容搜索，channels.weixin.qq.com 只有创作者后台
        'enable_collector': False,
        'enable_publish': True,
        'builtin': True,
        'enabled_default': False,
        'creator_url': 'https://channels.weixin.qq.com/platform/post/create',
        'cookie_domain': '.weixin.qq.com',
    },
    {
        'key': 'douyin',
        'label': '抖音',
        'color': 'black',
        'priority': 2,
        'desc': '泛流量大；采集/自动发有封号风险，默认关闭采集，发布请用人工确认模式',
        'cookie_domain': '.douyin.com',
        'creator_url': 'https://creator.douyin.com/creator-micro/content/upload',
        'search_url_template': '',
        'enable_collector': True,
        'enable_publish': True,
        'builtin': True,
        'enabled_default': False,
    },
    {
        'key': 'xiaohongshu',
        'label': '小红书',
        'color': 'red',
        'priority': 3,
        'desc': '种草向；采集/自动发有封号风险，默认关闭采集，发布请用人工确认模式',
        'cookie_domain': '.xiaohongshu.com',
        'creator_url': 'https://creator.xiaohongshu.com/publish/publish',
        'search_url_template': '',
        'enable_collector': True,
        'enable_publish': True,
        'builtin': True,
        'enabled_default': False,
    },
]

_KEY_RE = re.compile(r'^[a-z][a-z0-9_]{1,31}$')


def _guess_cookie_domain(url):
    """从 URL 猜测 Cookie 域名，如 https://www.kuaishou.com/x → .kuaishou.com"""
    if not url:
        return ''
    m = re.search(r'https?://([^/]+)', url)
    if not m:
        return ''
    host = m.group(1).split(':')[0].lower()
    parts = host.split('.')
    if len(parts) >= 2:
        return '.' + '.'.join(parts[-2:])
    return '.' + host


def _normalize_row(row):
    """Convert DB row / dict into unified platform shape."""
    if hasattr(row, 'keys'):
        d = dict(row)
    else:
        d = dict(row)
    return {
        'id': d.get('id'),
        'key': d['key'],
        'label': d.get('label') or d['key'],
        'color': d.get('color') or 'blue',
        'priority': int(d.get('priority') or 100),
        'desc': d.get('description') or d.get('desc') or '',
        'cookie_domain': d.get('cookie_domain') or '',
        'creator_url': d.get('creator_url') or '',
        'search_url_template': d.get('search_url_template') or '',
        'enable_collector': bool(d.get('enable_collector', True)),
        'enable_publish': bool(d.get('enable_publish', True)),
        'builtin': bool(d.get('builtin', False)),
        'setting_category': f"collector_{d['key']}",
        'enabled_default': bool(d.get('enabled_default', False)),
    }


def _load_custom_platforms():
    try:
        from config import get_db
        conn = get_db()
        rows = conn.execute(
            'SELECT * FROM ops_platform ORDER BY priority, id'
        ).fetchall()
        conn.close()
        return [_normalize_row(r) for r in rows]
    except Exception:
        return []


def list_platforms():
    """内置 + 自定义，按 priority 排序；同 key 以自定义覆盖（一般不会冲突）。"""
    by_key = {p['key']: dict(p) for p in BUILTIN_PLATFORMS}
    for p in BUILTIN_PLATFORMS:
        by_key[p['key']] = _normalize_row(p)
    for p in _load_custom_platforms():
        # 不允许用自定义覆盖内置 key；自定义同名被跳过
        if p['key'] in by_key and by_key[p['key']].get('builtin'):
            continue
        by_key[p['key']] = p
    return sorted(by_key.values(), key=lambda x: (x.get('priority', 100), x['key']))


def platform_map():
    return {p['key']: p for p in list_platforms()}


# 兼容旧引用：模块加载时的静态快照；运行时请用 platform_map() / list_platforms()
PLATFORM_MAP = {p['key']: p for p in BUILTIN_PLATFORMS}
PLATFORMS = list(BUILTIN_PLATFORMS)


def get_platform(key):
    return PLATFORM_MAP.get(key)


def platform_keys():
    return [p['key'] for p in list_platforms()]


def get_platform(key):
    return platform_map().get(key)


def validate_platform_key(key):
    if not key or not _KEY_RE.match(key):
        return False, '平台标识须为小写字母开头，仅含 a-z / 0-9 / _，长度 2-32'
    builtin_keys = {p['key'] for p in BUILTIN_PLATFORMS}
    if key in builtin_keys:
        return False, f'「{key}」为内置平台，无需重复添加'
    existing = {p['key'] for p in _load_custom_platforms()}
    if key in existing:
        return False, f'平台「{key}」已存在'
    return True, ''


def _seed_settings(conn, key, label, enable_collector=True, enable_publish=True,
                   cookie_domain='', creator_url=''):
    """为新平台写入 system_setting 默认项。"""
    items = []
    if enable_collector:
        cookie_hint = (
            '【高风险·不推荐】登录态/自动化采集可能封号。'
            f'浏览器打开对应网站 → F12 → Network → 复制 Cookie'
            + (f'（域名建议 {cookie_domain}）' if cookie_domain else '')
            + '。日常选题请用全网热榜。'
        )
        default_on = 'false'
        items.extend([
            (f'collector_{key}', 'enabled', default_on, f'启用{label}采集',
             '高风险：易触发平台风控。默认关闭，仅实验时开启。', 'select',
             '["true","false"]', 1),
            (f'collector_{key}', 'cookies', '', f'{label} Cookies', cookie_hint, 'textarea',
             None, 2),
            (f'collector_{key}', 'keywords', '', '采集关键词', '逗号分隔', 'text', None, 3),
        ])
    if enable_publish:
        pub_hint = (
            '安全模式无需 Cookie：发布中心会复制文案并打开官方页，由你手动点发布。'
            + (f' 创作者页：{creator_url}' if creator_url else '')
            + '。Cookies 仅高级「浏览器自动填充」需要（有封号风险）。'
        )
        items.extend([
            (f'publish_{key}', 'enabled', 'true', f'启用{label}发布',
             '推荐人工确认发布，避免自动化封号', 'select', '["true","false"]', 1),
            (f'publish_{key}', 'cookies', '', f'{label}发布 Cookies（可选·高风险）', pub_hint, 'textarea',
             None, 2),
        ])

    for item in items:
        conn.execute(
            '''INSERT INTO system_setting
               (category, key, value, label, description, field_type, options, sort_order)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (category, key) DO NOTHING''',
            item,
        )


def create_platform(data):
    """
    创建自定义平台并种子配置。
    data: key, label, color, desc, cookie_domain, creator_url,
          search_url_template, enable_collector, enable_publish, priority
    """
    key = (data.get('key') or '').strip().lower()
    label = (data.get('label') or '').strip()
    ok, err = validate_platform_key(key)
    if not ok:
        raise ValueError(err)
    if not label:
        raise ValueError('平台名称不能为空')

    color = (data.get('color') or 'blue').strip()
    desc = (data.get('desc') or data.get('description') or '').strip()
    cookie_domain = (data.get('cookie_domain') or '').strip()
    creator_url = (data.get('creator_url') or '').strip()
    search_url_template = (data.get('search_url_template') or '').strip()
    enable_collector = bool(data.get('enable_collector', True))
    enable_publish = bool(data.get('enable_publish', True))
    priority = int(data.get('priority') or 100)

    if not enable_collector and not enable_publish:
        raise ValueError('至少启用采集或发布之一')
    if enable_publish and not creator_url:
        raise ValueError('启用发布时须填写创作者后台地址 creator_url')
    if enable_collector and not search_url_template:
        raise ValueError('启用采集时须填写搜索页模板 search_url_template（含 {keyword}）')
    if search_url_template and '{keyword}' not in search_url_template:
        raise ValueError('search_url_template 须包含 {keyword} 占位符')
    if not cookie_domain:
        cookie_domain = _guess_cookie_domain(creator_url or search_url_template)

    from config import get_db
    conn = get_db()
    try:
        cur = conn.execute(
            '''INSERT INTO ops_platform
               (key, label, color, description, priority, cookie_domain,
                creator_url, search_url_template, enable_collector, enable_publish, builtin)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, FALSE)''',
            (key, label, color, desc, priority, cookie_domain,
             creator_url, search_url_template, enable_collector, enable_publish),
        )
        _seed_settings(
            conn, key, label,
            enable_collector=enable_collector,
            enable_publish=enable_publish,
            cookie_domain=cookie_domain,
            creator_url=creator_url,
        )
        conn.commit()
        new_id = cur.lastrowid
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return get_platform(key) or {
        'id': new_id, 'key': key, 'label': label, 'builtin': False,
    }


def update_platform(key, data):
    plat = get_platform(key)
    if not plat:
        raise ValueError('平台不存在')
    if plat.get('builtin'):
        raise ValueError('内置平台不可修改元数据，请直接改设置项')

    fields = {}
    for col in ('label', 'color', 'cookie_domain', 'creator_url',
                'search_url_template'):
        if col in data and data[col] is not None:
            fields[col] = str(data[col]).strip()
    if 'desc' in data or 'description' in data:
        fields['description'] = str(data.get('desc') or data.get('description') or '').strip()
    if 'priority' in data and data['priority'] is not None:
        fields['priority'] = int(data['priority'])
    if 'enable_collector' in data:
        fields['enable_collector'] = bool(data['enable_collector'])
    if 'enable_publish' in data:
        fields['enable_publish'] = bool(data['enable_publish'])

    if 'search_url_template' in fields and fields['search_url_template']:
        if '{keyword}' not in fields['search_url_template']:
            raise ValueError('search_url_template 须包含 {keyword} 占位符')

    if not fields:
        return plat

    from config import get_db
    conn = get_db()
    sets = ', '.join(f'{k}=?' for k in fields)
    conn.execute(
        f'UPDATE ops_platform SET {sets} WHERE key=?',
        list(fields.values()) + [key],
    )
    conn.commit()
    conn.close()
    return get_platform(key)


def delete_platform(key):
    plat = get_platform(key)
    if not plat:
        raise ValueError('平台不存在')
    if plat.get('builtin'):
        raise ValueError('内置平台不可删除')

    from config import get_db
    conn = get_db()
    conn.execute('DELETE FROM ops_platform WHERE key=?', (key,))
    # 清理对应设置分类
    conn.execute('DELETE FROM system_setting WHERE category=?', (f'collector_{key}',))
    conn.execute('DELETE FROM system_setting WHERE category=?', (f'publish_{key}',))
    conn.commit()
    conn.close()
    return True
