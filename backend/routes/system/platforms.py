"""Platform CRUD routes - 自定义采集/发布平台。"""

from flask import Blueprint, request, jsonify
from modules.content_ops.platforms import (
    list_platforms, get_platform, create_platform, update_platform, delete_platform,
)

bp = Blueprint('platforms', __name__)


@bp.route('/api/platforms')
def api_list_platforms():
    return jsonify({'list': list_platforms()})


@bp.route('/api/platforms', methods=['POST'])
def api_create_platform():
    data = request.get_json(silent=True) or {}
    try:
        plat = create_platform(data)
        return jsonify({'platform': plat, 'message': f"平台「{plat['label']}」已添加，可直接配置 Cookies 使用"}), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'创建失败: {e}'}), 500


@bp.route('/api/platforms/<key>', methods=['PUT'])
def api_update_platform(key):
    data = request.get_json(silent=True) or {}
    try:
        plat = update_platform(key, data)
        return jsonify({'platform': plat, 'message': '已更新'})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'更新失败: {e}'}), 500


@bp.route('/api/platforms/<key>', methods=['DELETE'])
def api_delete_platform(key):
    try:
        delete_platform(key)
        return jsonify({'message': '已删除'})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'删除失败: {e}'}), 500


@bp.route('/api/platforms/<key>')
def api_get_platform(key):
    plat = get_platform(key)
    if not plat:
        return jsonify({'error': '平台不存在'}), 404
    return jsonify(plat)
