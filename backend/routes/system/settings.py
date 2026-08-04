"""Settings routes - 按功能模块分组的系统配置。"""

import json
from flask import Blueprint, request, jsonify
from config import update_settings_batch, get_db as _db
from modules.content_ops.platforms import list_platforms

bp = Blueprint('settings', __name__)

SETTINGS_MODULES = [
    {
        'key': 'ai',
        'path': 'ai',
        'label': 'AI 大模型',
        'desc': '文案生成、热点分析、客户分析所用的大模型',
        'icon': 'robot',
        'categories': ['ai'],
    },
    {
        'key': 'collectors',
        'path': 'collectors',
        'label': '采集平台',
        'desc': '视频号 / 抖音 / 小红书等口播素材采集（可扩展）',
        'icon': 'cloud-download',
        'type': 'collector_platforms',
        'categories': [],
    },
    {
        'key': 'publish',
        'path': 'publish',
        'label': '发布平台',
        'desc': '各平台发布账号 Cookies',
        'icon': 'rocket',
        'type': 'publish_platforms',
        'categories': [],
    },
    {
        'key': 'media',
        'path': 'media',
        'label': '配音与视频',
        'desc': 'TTS 配音、视频合成参数',
        'icon': 'video-camera',
        'categories': ['tts', 'video'],
    },
    {
        'key': 'content',
        'path': 'content',
        'label': '内容运营',
        'desc': '每日 2+1 计划、品牌收口、采集间隔',
        'icon': 'file-text',
        'categories': ['system'],
    },
    {
        'key': 'stock',
        'path': 'stock',
        'label': '股票筛选',
        'desc': '技术面初筛上限、匹配模式、自定义形态规则',
        'icon': 'line-chart',
        'categories': ['stock'],
    },
]


def _load_all_settings_rows():
    conn = _db()
    rows = conn.execute(
        'SELECT * FROM system_setting ORDER BY category, sort_order'
    ).fetchall()
    conn.close()
    result = {}
    for row in rows:
        cat = row['category']
        if cat not in result:
            result[cat] = []
        item = dict(row)
        if item.get('options'):
            try:
                item['options'] = json.loads(item['options'])
            except (json.JSONDecodeError, TypeError):
                pass
        result[cat].append(item)
    return result


@bp.route('/api/settings/modules')
def list_modules():
    platforms = list_platforms()
    modules = []
    for m in SETTINGS_MODULES:
        mod = dict(m)
        if m.get('type') == 'collector_platforms':
            collectors = [p for p in platforms if p.get('enable_collector', True)]
            mod['platforms'] = [
                {**p, 'category': f"collector_{p['key']}"}
                for p in collectors
            ]
            mod['categories'] = [f"collector_{p['key']}" for p in collectors]
        elif m.get('type') == 'publish_platforms':
            pubs = [p for p in platforms if p.get('enable_publish', True)]
            mod['platforms'] = [
                {**p, 'category': f"publish_{p['key']}"}
                for p in pubs
            ]
            mod['categories'] = [f"publish_{p['key']}" for p in pubs]
        modules.append(mod)
    return jsonify({'modules': modules})


@bp.route('/api/settings/check', methods=['GET'])
def check_readiness():
    conn = _db()
    rows = conn.execute('SELECT category, key, value FROM system_setting').fetchall()
    conn.close()

    settings = {}
    for row in rows:
        cat = row['category']
        if cat not in settings:
            settings[cat] = {}
        settings[cat][row['key']] = row['value']

    # Playwright / FFmpeg（运行环境）
    try:
        from modules.publisher import check_playwright
        pw_ok = bool(check_playwright())
    except Exception:
        pw_ok = False
    try:
        from modules.video_maker import check_ffmpeg
        ff_ok = bool(check_ffmpeg())
    except Exception:
        ff_ok = False

    readiness = {
        'ai': {
            'ready': bool(settings.get('ai', {}).get('api_key')),
            'message': 'AI API Key 已配置' if settings.get('ai', {}).get('api_key') else '未配置 AI API Key',
            'path': '/settings/ai',
        },
        'tts': {'ready': True, 'message': 'TTS 就绪 (Edge TTS 免费)', 'path': '/settings/media'},
        'video': {
            'ready': True,
            'message': '视频合成模块就绪（MoviePy 可用）',
            'path': '/settings/media',
        },
        'ffmpeg': {
            'ready': ff_ok,
            'message': '已检测到系统 FFmpeg' if ff_ok else '未检测到系统 FFmpeg（MoviePy 仍可用；测时长/FFmpeg 引擎建议安装）',
            'path': '/settings/media',
            'optional': True,
        },
        'playwright': {
            'ready': pw_ok,
            'message': 'Playwright 已安装' if pw_ok else '未安装 Playwright（自动发布需要）',
            'path': '/settings/publish',
        },
        'system': {'ready': True, 'message': '内容运营参数可改', 'path': '/settings/content'},
        'media': {'ready': True, 'message': '配音与视频可用', 'path': '/settings/media'},
        'content': {'ready': True, 'message': '内容运营参数可用', 'path': '/settings/content'},
    }

    for p in list_platforms():
        if p.get('enable_collector', True):
            ckey = f"collector_{p['key']}"
            readiness[ckey] = {
                'ready': bool(settings.get(ckey, {}).get('cookies')),
                'enabled': str(settings.get(ckey, {}).get('enabled', 'true')).lower() == 'true',
                'message': f"{p['label']}采集 Cookies 已配置" if settings.get(ckey, {}).get('cookies') else f"未配置{p['label']}采集 Cookies",
                'label': p['label'],
                'path': '/settings/collectors',
            }
        if p.get('enable_publish', True):
            pkey = f"publish_{p['key']}"
            readiness[pkey] = {
                'ready': bool(settings.get(pkey, {}).get('cookies')),
                'enabled': str(settings.get(pkey, {}).get('enabled', 'false')).lower() == 'true',
                'message': f"{p['label']}发布已配置" if settings.get(pkey, {}).get('cookies') else f"未配置{p['label']}发布",
                'label': p['label'],
                'path': '/settings/publish',
            }

    collector_ready = any(
        readiness.get(f"collector_{p['key']}", {}).get('ready')
        for p in list_platforms() if p.get('enable_collector', True)
    )
    readiness['collectors'] = {
        'ready': collector_ready,
        'message': '至少有一个采集平台已配置 Cookies' if collector_ready else '尚未配置任何采集平台 Cookies',
        'path': '/settings/collectors',
    }
    publish_ready = any(
        readiness.get(f"publish_{p['key']}", {}).get('ready')
        for p in list_platforms() if p.get('enable_publish', True)
    )
    readiness['publish'] = {
        'ready': publish_ready,
        'message': '至少有一个发布平台已配置' if publish_ready else '尚未配置发布平台',
        'path': '/settings/publish',
    }

    # 总览用的精简清单
    readiness['summary'] = [
        {'key': 'ai', **readiness['ai'], 'label': 'AI 模型'},
        {'key': 'collectors', **readiness['collectors'], 'label': '内容采集'},
        {'key': 'publish', **readiness['publish'], 'label': '发布平台'},
        {'key': 'playwright', **readiness['playwright'], 'label': 'Playwright'},
        {'key': 'ffmpeg', **readiness['ffmpeg'], 'label': 'FFmpeg'},
    ]

    return jsonify(readiness)


@bp.route('/api/settings')
def get_settings():
    return jsonify(_load_all_settings_rows())


@bp.route('/api/settings', methods=['PUT'])
def update_settings():
    data = request.get_json(silent=True) or {}
    update_settings_batch(data)
    return jsonify({'message': '设置已保存'})


@bp.route('/api/settings/<category>', methods=['GET'])
def get_category_settings(category):
    conn = _db()
    rows = conn.execute(
        'SELECT * FROM system_setting WHERE category=? ORDER BY sort_order', (category,)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])
