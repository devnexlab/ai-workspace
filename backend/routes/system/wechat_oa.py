"""微信服务号公开接口（客户 H5，无需登录）。"""

from flask import Blueprint, request, jsonify

from modules.wechat_oa import get_oa_profile, create_lead

bp = Blueprint('wechat_oa', __name__)


@bp.route('/api/public/wechat-oa/profile', methods=['GET'])
def public_profile():
    profile = get_oa_profile()
    # 对外不暴露 app_id / secret
    return jsonify({
        'enabled': profile['enabled'],
        'brand_name': profile['brand_name'],
        'intro_title': profile['intro_title'],
        'intro_text': profile['intro_text'],
        'contact_wechat': profile['contact_wechat'],
        'contact_phone': profile['contact_phone'],
        'booking_hint': profile['booking_hint'],
    })


@bp.route('/api/public/wechat-oa/leads', methods=['POST'])
def public_leads():
    data = request.get_json(silent=True) or {}
    try:
        result = create_lead(data)
        return jsonify(result), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'提交失败: {e}'}), 500


@bp.route('/api/settings/wechat-oa/menu-links', methods=['GET'])
def menu_links():
    """后台设置页用：生成可复制的菜单链接。"""
    profile = get_oa_profile()
    return jsonify({
        'public_base_url': profile['public_base_url'],
        'about_url': profile['about_url'],
        'book_url': profile['book_url'],
        'about_path': profile['about_path'],
        'book_path': profile['book_path'],
        'hint': (
            '请把「对外访问地址」填成客户手机能打开的域名或 IP（含 http/https），'
            '再复制链接到微信公众平台 → 自定义菜单。'
            if not profile['public_base_url']
            else '将下列链接配置到服务号自定义菜单即可。'
        ),
    })
