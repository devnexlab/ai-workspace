"""
微信服务号（阶段①）：对外展示配置 + 客户留资。

阶段①不接模板消息/openid；只提供可挂菜单的 H5 与后台配置。
"""

from __future__ import annotations


def get_oa_profile() -> dict:
    from config import get_settings_by_category

    cfg = get_settings_by_category('wechat_oa') or {}
    enabled = str(cfg.get('enabled', 'false')).lower() in ('1', 'true', 'yes', 'on')
    brand = (cfg.get('brand_name') or '祁实说实话').strip()
    public_base = (cfg.get('public_base_url') or '').strip().rstrip('/')
    return {
        'enabled': enabled,
        'brand_name': brand,
        'intro_title': (cfg.get('intro_title') or f'你好，我是{brand}').strip(),
        'intro_text': (cfg.get('intro_text') or '').strip(),
        'contact_wechat': (cfg.get('contact_wechat') or '').strip(),
        'contact_phone': (cfg.get('contact_phone') or '').strip(),
        'booking_hint': (cfg.get('booking_hint') or '留下联系方式，我会尽快与你联系。').strip(),
        'public_base_url': public_base,
        'about_path': '/m/about',
        'book_path': '/m/book',
        'about_url': f'{public_base}/m/about' if public_base else '',
        'book_url': f'{public_base}/m/book' if public_base else '',
        'app_id': (cfg.get('app_id') or '').strip(),
    }


def create_lead(data: dict) -> dict:
    """服务号 H5 留资 → 写入 customer，并尽量通知运营。"""
    nickname = (data.get('nickname') or data.get('name') or '').strip()
    phone = (data.get('phone') or '').strip()
    wechat = (data.get('wechat') or '').strip()
    remark = (data.get('remark') or '').strip()
    preferred = (data.get('preferred_time') or '').strip()

    if not nickname:
        raise ValueError('请填写称呼')
    if not phone and not wechat:
        raise ValueError('请至少填写手机或微信号之一')

    note_parts = ['【微信服务号留资】']
    if preferred:
        note_parts.append(f'期望联系时间：{preferred}')
    if remark:
        note_parts.append(remark)
    full_remark = '\n'.join(note_parts)

    from config import get_db

    conn = get_db()
    try:
        cur = conn.execute(
            '''INSERT INTO customer
               (nickname, phone, wechat, source_channel, tags, intention,
                lifecycle_stage, remark)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (
                nickname,
                phone,
                wechat,
                '微信服务号',
                '服务号留资',
                'medium',
                'appointment',
                full_remark,
            ),
        )
        lead_id = cur.lastrowid
        conn.commit()
    finally:
        conn.close()

    # 通知运营（已有推送通道）
    try:
        from modules.wechat_notify import send_wechat
        title = f'新留资：{nickname}'
        content = (
            f'来源：微信服务号\n'
            f'称呼：{nickname}\n'
            f'手机：{phone or "-"}\n'
            f'微信：{wechat or "-"}\n'
            f'期望时间：{preferred or "-"}\n'
            f'备注：{remark or "-"}'
        )
        send_wechat(title, content, force=True)
    except Exception as e:
        print(f'[wechat_oa] notify failed: {e}')

    return {'id': lead_id, 'nickname': nickname, 'message': '已提交，我们会尽快联系你'}
