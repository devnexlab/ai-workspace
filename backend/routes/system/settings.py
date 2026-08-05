"""Settings routes - 按功能模块分组的系统配置。"""

import json
from flask import Blueprint, request, jsonify
from config import update_settings_batch, get_db as _db
from modules.content_ops.platforms import list_platforms
from modules.content_ops.commercial_data import list_commercial_providers
from modules.wechat_notify import list_notify_channels, channel_status as notify_channel_status

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
        'desc': '平台登录态采集默认关闭（易封号）。日常选题请用内容情报「全网热榜」',
        'icon': 'cloud-download',
        'type': 'collector_platforms',
        'categories': [],
    },
    {
        'key': 'commercial',
        'path': 'commercial',
        'label': '官方数据台',
        'desc': '巨量算数 / 蝉妈妈 / 新榜等：只配官方或合规 API，拉取榜单入内容情报',
        'icon': 'bar-chart',
        'type': 'commercial_providers',
        'categories': [],
    },
    {
        'key': 'publish',
        'path': 'publish',
        'label': '发布平台',
        'desc': '推荐复制文案 + 打开官方创作者页，由你手动点发布',
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
        'key': 'notify',
        'path': 'notify',
        'label': '消息推送',
        'desc': '股价预警推到企业微信（免费）；也可选 PushPlus / Server酱',
        'icon': 'bell',
        'type': 'notify_channels',
        'categories': [],
    },
    {
        'key': 'content',
        'path': 'content',
        'label': '内容运营',
        'desc': '每日 2+1 计划、品牌收口、采集间隔',
        'icon': 'file-text',
        'categories': ['system'],
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
        elif m.get('type') == 'commercial_providers':
            providers = list_commercial_providers()
            mod['platforms'] = providers
            mod['categories'] = [p['category'] for p in providers]
        elif m.get('type') == 'notify_channels':
            channels = list_notify_channels()
            rules = {
                'key': 'rules',
                'label': '推送规则',
                'desc': '哪些事件要推送',
                'category': 'notify',
                'color': 'purple',
                'builtin': True,
            }
            mod['platforms'] = channels + [rules]
            mod['categories'] = [c['category'] for c in channels] + ['notify']
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
            'message': 'Playwright 已安装（仅高级自动填充可选）' if pw_ok else '未安装 Playwright（安全发布模式不需要）',
            'path': '/settings/publish',
            'optional': True,
        },
        'system': {'ready': True, 'message': '内容运营参数可改', 'path': '/settings/content'},
        'media': {'ready': True, 'message': '配音与视频可用', 'path': '/settings/media'},
        'content': {'ready': True, 'message': '内容运营参数可用', 'path': '/settings/content'},
    }

    try:
        from modules.wechat_notify import is_ready as notify_ready, _cfg as notify_cfg
        ncfg = notify_cfg()
        n_ok, n_msg = notify_ready(ncfg)
        if not ncfg['enabled']:
            readiness['notify'] = {
                'ready': True,
                'optional': True,
                'message': '消息推送未开启（可选）；推荐启用企业微信',
                'path': '/settings/notify',
            }
        else:
            readiness['notify'] = {
                'ready': n_ok,
                'optional': True,
                'message': n_msg if n_ok else f'已开启但未配齐：{n_msg}',
                'path': '/settings/notify',
            }
        for ch in list_notify_channels():
            st = notify_channel_status(ch['key'])
            readiness[ch['category']] = {
                'ready': st['ready'],
                'enabled': st['enabled'],
                'message': st['message'],
                'label': ch['label'],
                'path': '/settings/notify',
            }
        readiness['notify'] = {
            **readiness['notify'],
            'ready': readiness['notify']['ready'],
        }
    except Exception:
        readiness['notify'] = {
            'ready': True,
            'optional': True,
            'message': '消息推送可选',
            'path': '/settings/notify',
        }

    for p in list_platforms():
        if p.get('enable_collector', True):
            ckey = f"collector_{p['key']}"
            enabled = str(settings.get(ckey, {}).get('enabled', 'false')).lower() == 'true'
            has_cookie = bool(settings.get(ckey, {}).get('cookies'))
            readiness[ckey] = {
                'ready': (not enabled) or has_cookie,
                'enabled': enabled,
                'message': (
                    f"{p['label']}采集已关闭（推荐）" if not enabled
                    else (f"{p['label']}采集 Cookies 已配置" if has_cookie else f"{p['label']}采集已开但未配 Cookies")
                ),
                'label': p['label'],
                'path': '/settings/collectors',
            }
        if p.get('enable_publish', True):
            pkey = f"publish_{p['key']}"
            enabled = str(settings.get(pkey, {}).get('enabled', 'true')).lower() == 'true'
            # 安全发布不依赖 Cookie
            readiness[pkey] = {
                'ready': enabled,
                'enabled': enabled,
                'message': (
                    f"{p['label']}发布已启用（复制文案+打开官方页）" if enabled
                    else f"{p['label']}发布未启用"
                ),
                'label': p['label'],
                'path': '/settings/publish',
            }

    # 内容采集：全网热榜即可，不强制平台 Cookie
    any_platform_collect_on = any(
        readiness.get(f"collector_{p['key']}", {}).get('enabled')
        for p in list_platforms() if p.get('enable_collector', True)
    )
    readiness['collectors'] = {
        'ready': True,
        'message': (
            '可用全网热榜选题；平台登录态采集已关闭（更安全）'
            if not any_platform_collect_on
            else '平台登录态采集已开启（有封号风险），请确认确有必要'
        ),
        'path': '/settings/collectors',
        'optional': True,
    }

    commercial_list = list_commercial_providers()
    commercial_on = [p for p in commercial_list if p.get('enabled')]
    commercial_bad = [p for p in commercial_on if not p.get('ready')]
    for p in commercial_list:
        readiness[p['category']] = {
            'ready': p['ready'],
            'enabled': p['enabled'],
            'message': p['message'],
            'label': p['label'],
            'path': '/settings/commercial',
        }
    readiness['commercial'] = {
        'ready': len(commercial_bad) == 0,
        'message': (
            '未启用商业数据台（可选）；启用后请配齐 Base URL / API Key'
            if not commercial_on
            else (
                f'已启用 {len(commercial_on)} 个数据源'
                if not commercial_bad
                else f'{len(commercial_bad)} 个已启用源未配齐 API'
            )
        ),
        'path': '/settings/commercial',
        'optional': True,
        'providers': commercial_list,
    }
    publish_ready = any(
        readiness.get(f"publish_{p['key']}", {}).get('ready')
        for p in list_platforms() if p.get('enable_publish', True)
    )
    readiness['publish'] = {
        'ready': publish_ready,
        'message': '至少有一个发布平台已启用' if publish_ready else '尚未启用发布平台',
        'path': '/settings/publish',
    }

    # 总览用的精简清单
    readiness['summary'] = [
        {'key': 'ai', **readiness['ai'], 'label': 'AI 模型'},
        {'key': 'collectors', **readiness['collectors'], 'label': '内容选题'},
        {'key': 'commercial', **readiness['commercial'], 'label': '官方数据台'},
        {'key': 'publish', **readiness['publish'], 'label': '发布平台'},
        {'key': 'notify', **readiness['notify'], 'label': '微信推送'},
        {'key': 'playwright', **readiness['playwright'], 'label': 'Playwright（可选）'},
        {'key': 'ffmpeg', **readiness['ffmpeg'], 'label': 'FFmpeg'},
    ]

    return jsonify(readiness)


@bp.route('/api/settings/notify/test', methods=['POST'])
def test_notify():
    """发送一条测试推送。可指定 channel=wecom|pushplus|serverchan。"""
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '推送测试').strip()
    content = (data.get('content') or '这是一条来自运营平台的测试消息，配置正常即可收到股价预警。').strip()
    channel = (data.get('channel') or data.get('provider') or '').strip().lower() or None
    try:
        from modules.wechat_notify import send_wechat
        result = send_wechat(title, content, force=True, provider=channel)
        if result.get('ok'):
            return jsonify({'message': result.get('message') or '已发送', **result})
        return jsonify({'error': result.get('message') or '发送失败', **result}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


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
