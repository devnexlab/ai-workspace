"""
个人消息推送：企业微信 / PushPlus / Server酱。

配置按渠道分 category（与采集平台卡片一致）：
  notify_wecom / notify_pushplus / notify_serverchan / notify(规则)
"""

from __future__ import annotations

from typing import Any

import requests

NOTIFY_CHANNELS = [
    {
        'key': 'wecom',
        'label': '企业微信',
        'desc': '免费群机器人，推荐自己用',
        'category': 'notify_wecom',
        'color': 'green',
        'builtin': True,
        'recommended': True,
    },
    {
        'key': 'pushplus',
        'label': 'PushPlus',
        'desc': '微信服务通知；实名可能收费，备用',
        'category': 'notify_pushplus',
        'color': 'blue',
        'builtin': True,
    },
    {
        'key': 'serverchan',
        'label': 'Server酱',
        'desc': 'SCT 推送到微信，备用',
        'category': 'notify_serverchan',
        'color': 'orange',
        'builtin': True,
    },
]


def list_notify_channels():
    return [dict(c) for c in NOTIFY_CHANNELS]


def _truthy(v) -> bool:
    return str(v or '').lower() in ('1', 'true', 'yes', 'on')


def _cfg():
    """读取当前生效渠道；兼容旧版单 category=notify 配置。"""
    from config import get_setting

    on_stock = _truthy(get_setting('notify', 'on_stock_alert', 'true'))
    on_screen = _truthy(get_setting('notify', 'on_screening_done', 'false'))

    wecom_on = _truthy(get_setting('notify_wecom', 'enabled', 'false'))
    push_on = _truthy(get_setting('notify_pushplus', 'enabled', 'false'))
    sct_on = _truthy(get_setting('notify_serverchan', 'enabled', 'false'))

    wecom_hook = (get_setting('notify_wecom', 'webhook', '') or get_setting('notify', 'wecom_webhook', '') or '').strip()
    push_token = (get_setting('notify_pushplus', 'token', '') or get_setting('notify', 'pushplus_token', '') or '').strip()
    sct_key = (get_setting('notify_serverchan', 'sendkey', '') or get_setting('notify', 'serverchan_sendkey', '') or '').strip()

    provider = ''
    if wecom_on:
        provider = 'wecom'
    elif push_on:
        provider = 'pushplus'
    elif sct_on:
        provider = 'serverchan'
    else:
        # 旧配置：notify.enabled + notify.provider
        legacy_on = _truthy(get_setting('notify', 'enabled', 'false'))
        legacy_provider = (get_setting('notify', 'provider', 'wecom') or 'wecom').strip().lower()
        if legacy_on:
            provider = legacy_provider

    return {
        'enabled': bool(provider),
        'provider': provider or 'wecom',
        'pushplus_token': push_token,
        'serverchan_sendkey': sct_key,
        'wecom_webhook': wecom_hook,
        'on_stock_alert': on_stock,
        'on_screening_done': on_screen,
        'channels': {
            'wecom': {'enabled': wecom_on, 'ready': bool(wecom_hook)},
            'pushplus': {'enabled': push_on, 'ready': bool(push_token)},
            'serverchan': {'enabled': sct_on, 'ready': bool(sct_key)},
        },
    }


def channel_status(key: str) -> dict:
    cfg = _cfg()
    ch = (cfg.get('channels') or {}).get(key) or {}
    enabled = bool(ch.get('enabled'))
    ready_cred = bool(ch.get('ready'))
    active = cfg.get('enabled') and cfg.get('provider') == key
    if key == 'wecom':
        msg = 'Webhook 已填' if ready_cred else '未填 Webhook'
    elif key == 'pushplus':
        msg = 'Token 已填' if ready_cred else '未填 Token'
    else:
        msg = 'SendKey 已填' if ready_cred else '未填 SendKey'
    if enabled and ready_cred:
        status = 'ready'
        message = f'已启用 · {msg}'
    elif enabled:
        status = 'need_config'
        message = f'已启用但{msg}'
    else:
        status = 'off'
        message = f'未启用 · {msg}'
    return {
        'key': key,
        'enabled': enabled,
        'ready': enabled and ready_cred,
        'active': active,
        'status': status,
        'message': message,
        'path': '/settings/notify',
    }


def is_ready(cfg: dict | None = None) -> tuple[bool, str]:
    cfg = cfg or _cfg()
    if not cfg['enabled']:
        return False, '推送未开启'
    provider = cfg['provider']
    if provider == 'pushplus':
        if not cfg['pushplus_token']:
            return False, '未填写 PushPlus Token'
        return True, 'PushPlus 已配置'
    if provider in ('serverchan', 'server酱', 'sct'):
        if not cfg['serverchan_sendkey']:
            return False, '未填写 Server酱 SendKey'
        return True, 'Server酱 已配置'
    if provider in ('wecom', '企业微信', 'qiye'):
        if not cfg['wecom_webhook']:
            return False, '未填写企业微信 Webhook'
        return True, '企业微信机器人已配置'
    return False, f'未知推送渠道: {provider}'


def send_wechat(title: str, content: str, *, force: bool = False, provider: str | None = None) -> dict[str, Any]:
    """发送一条推送。force=True 时忽略 enabled（用于测试）。"""
    cfg = _cfg()
    use_provider = (provider or cfg['provider'] or 'wecom').strip().lower()

    if not force and not cfg['enabled']:
        return {'ok': False, 'skipped': True, 'message': '推送未开启'}

    # 测试指定渠道时，用该渠道凭证校验
    check = dict(cfg)
    check['enabled'] = True
    check['provider'] = use_provider
    ready, msg = is_ready(check)
    if not ready:
        return {'ok': False, 'message': msg}

    title = (title or '通知').strip()[:100]
    content = (content or '').strip() or title

    try:
        if use_provider == 'pushplus':
            return _send_pushplus(cfg['pushplus_token'], title, content)
        if use_provider in ('serverchan', 'server酱', 'sct'):
            return _send_serverchan(cfg['serverchan_sendkey'], title, content)
        if use_provider in ('wecom', '企业微信', 'qiye'):
            return _send_wecom(cfg['wecom_webhook'], title, content)
        return {'ok': False, 'message': f'未知推送渠道: {use_provider}'}
    except Exception as e:
        return {'ok': False, 'message': str(e)}


def notify_stock_alerts(alerts: list[dict]) -> dict[str, Any]:
    cfg = _cfg()
    if not cfg['enabled'] or not cfg['on_stock_alert']:
        return {'ok': False, 'skipped': True, 'message': '股价预警推送未开启'}
    if not alerts:
        return {'ok': False, 'skipped': True, 'message': '无预警'}

    if len(alerts) == 1:
        a = alerts[0]
        return send_wechat(a.get('title') or '股价预警', a.get('content') or '')

    lines = [
        f"{i}. {a.get('title') or ''}\n{(a.get('content') or '').strip()}"
        for i, a in enumerate(alerts, 1)
    ]
    return send_wechat(f'股价预警 {len(alerts)} 条', '\n\n'.join(lines))


def notify_screening_done(name: str, matched: int, message: str = '') -> dict[str, Any]:
    cfg = _cfg()
    if not cfg['enabled'] or not cfg['on_screening_done']:
        return {'ok': False, 'skipped': True, 'message': '筛选完成推送未开启'}
    title = f'筛选完成：{name or "技术面筛选"}'
    body = message or f'命中 {matched} 只股票'
    return send_wechat(title, body)


def _send_pushplus(token: str, title: str, content: str) -> dict[str, Any]:
    resp = requests.post(
        'https://www.pushplus.plus/send',
        json={
            'token': token,
            'title': title,
            'content': content,
            'template': 'txt',
        },
        timeout=15,
    )
    data = {}
    try:
        data = resp.json()
    except Exception:
        data = {'raw': (resp.text or '')[:300]}
    code = data.get('code')
    ok = resp.ok and code in (0, 200, '0', '200')
    return {
        'ok': bool(ok),
        'provider': 'pushplus',
        'message': data.get('msg') or data.get('message') or ('发送成功' if ok else '发送失败'),
        'detail': data,
    }


def _send_serverchan(sendkey: str, title: str, content: str) -> dict[str, Any]:
    url = f'https://sctapi.ftqq.com/{sendkey}.send'
    resp = requests.post(url, data={'title': title, 'desp': content}, timeout=15)
    data = {}
    try:
        data = resp.json()
    except Exception:
        data = {'raw': (resp.text or '')[:300]}
    ok = resp.ok and data.get('code') == 0
    return {
        'ok': bool(ok),
        'provider': 'serverchan',
        'message': data.get('message') or data.get('msg') or ('发送成功' if ok else '发送失败'),
        'detail': data,
    }


def _send_wecom(webhook: str, title: str, content: str) -> dict[str, Any]:
    text = f'【{title}】\n{content}'
    resp = requests.post(
        webhook,
        json={'msgtype': 'text', 'text': {'content': text}},
        timeout=15,
    )
    data = {}
    try:
        data = resp.json()
    except Exception:
        data = {'raw': (resp.text or '')[:300]}
    ok = resp.ok and data.get('errcode', 0) == 0
    return {
        'ok': bool(ok),
        'provider': 'wecom',
        'message': data.get('errmsg') or ('发送成功' if ok else '发送失败'),
        'detail': data,
    }
