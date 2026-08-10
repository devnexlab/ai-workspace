"""桌宠数据问答 API：向量检索 + Agent。"""

from flask import Blueprint, request, jsonify

from modules.pet.agent import (
    append_message,
    create_session,
    load_history,
    run_pet_agent,
)
from modules.pet.rag import ensure_index, index_status, reindex_all

bp = Blueprint('pet_chat', __name__)


@bp.route('/api/pet-chat/status')
def pet_chat_status():
    status = index_status()
    return jsonify({'ok': True, **status})


@bp.route('/api/pet-chat/reindex', methods=['POST'])
def pet_chat_reindex():
    try:
        stats = reindex_all()
        return jsonify({'ok': True, 'stats': stats, **index_status()})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@bp.route('/api/pet-chat', methods=['POST'])
def pet_chat():
    data = request.get_json(silent=True) or {}
    message = (data.get('message') or data.get('question') or '').strip()
    mode = (data.get('mode') or 'auto').strip().lower()
    session_id = data.get('session_id')

    if not message:
        return jsonify({'error': '请输入问题'}), 400

    try:
        ensure_index()
    except Exception:
        pass

    try:
        if session_id:
            session_id = int(session_id)
            history = load_history(session_id)
        else:
            session_id = create_session(message[:40])
            history = []
    except Exception as e:
        return jsonify({'error': f'会话创建失败: {e}'}), 500

    append_message(session_id, 'user', message)

    try:
        result = run_pet_agent(message, mode=mode, history=history)
    except Exception as e:
        append_message(session_id, 'assistant', f'出错了：{e}', {'error': True})
        return jsonify({
            'ok': False,
            'session_id': session_id,
            'answer': f'问答失败：{e}',
            'steps': [{'text': f'失败：{e}', 'state': 'ok'}],
            'cites': [],
            'mode': mode,
        }), 500

    append_message(
        session_id,
        'assistant',
        result.get('answer') or '',
        {
            'steps': result.get('steps') or [],
            'cites': result.get('cites') or [],
            'mode': result.get('mode') or mode,
        },
    )

    return jsonify({
        'ok': True,
        'session_id': session_id,
        'answer': result.get('answer') or '',
        'steps': result.get('steps') or [],
        'cites': result.get('cites') or [],
        'mode': result.get('mode') or mode,
    })
