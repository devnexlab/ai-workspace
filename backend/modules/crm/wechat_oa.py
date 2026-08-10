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
    """服务号 H5 留资 → 写入线索池，并尽量通知运营。"""
    from modules.crm.leads import create_lead_row

    payload = {
        'nickname': data.get('nickname') or data.get('name'),
        'phone': data.get('phone'),
        'wechat': data.get('wechat'),
        'remark': data.get('remark'),
        'preferred_time': data.get('preferred_time'),
        'source': 'wechat_oa',
        'status': 'pending_contact',
    }
    return create_lead_row(payload, notify=True)