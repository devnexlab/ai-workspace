"""桌宠数据问答 API：向量检索 + Agent。"""

from flask import Blueprint, request, jsonify

from modules.pet.agent import (
    append_message,
    create_session,
    list_sessions,
    load_history,
    load_session_messages,
    run_pet_agent,
    session_exists,
)
from modules.pet.rag import ensure_index, index_status, reindex_all

bp = Blueprint('pet_chat', __name__)


@bp.route('/api/pet-chat/status')
def pet_chat_status():
    status = index_status()
    return jsonify({'ok': True, **status})


@bp.route('/api/pet-chat/sessions')
def pet_chat_sessions():
    try:
        sessions = list_sessions(limit=40)
        return jsonify({'ok': True, 'sessions': sessions})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@bp.route('/api/pet-chat/sessions/<int:session_id>')
def pet_chat_session_detail(session_id):
    try:
        if not session_exists(session_id):
            return jsonify({'ok': False, 'error': '会话不存在'}), 404
        messages = load_session_messages(session_id)
        return jsonify({'ok': True, 'session_id': session_id, 'messages': messages})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@bp.route('/api/pet-chat/reindex', methods=['POST'])
def pet_chat_reindex():
    try:
        stats = reindex_all()
        return jsonify({'ok': True, 'stats': stats, **index_status()})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@bp.route('/api/pet-chat/jobs')
def pet_chat_jobs():
    """列出智仔定时任务。"""
    try:
        from modules.pet.jobs import list_jobs
        jobs = list_jobs(include_paused=True)
        return jsonify({'ok': True, 'jobs': jobs})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@bp.route('/api/pet-chat/jobs/<int:job_id>/pause', methods=['POST'])
def pet_chat_job_pause(job_id):
    from modules.pet.jobs import ensure_pet_job_table
    from config import get_db
    ensure_pet_job_table()
    conn = get_db()
    try:
        conn.execute(
            'UPDATE pet_job SET enabled=FALSE, updated_at=CURRENT_TIMESTAMP WHERE id=%s',
            (job_id,),
        )
        conn.commit()
    finally:
        conn.close()
    return jsonify({'ok': True, 'id': job_id, 'enabled': False})


@bp.route('/api/pet-chat', methods=['POST'])
def pet_chat():
    data = request.get_json(silent=True) or {}
    message = (data.get('message') or data.get('question') or '').strip()
    mode = (data.get('mode') or 'auto').strip().lower()
    source = (data.get('source') or '').strip().lower()
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
            if not session_exists(session_id):
                session_id = create_session(message[:40])
                history = []
            else:
                history = load_history(session_id, limit=20)
        else:
            session_id = create_session(message[:40])
            history = []
    except Exception as e:
        return jsonify({'error': f'会话创建失败: {e}'}), 500

    append_message(session_id, 'user', message)

    try:
        result = run_pet_agent(message, mode=mode, history=history, source=source)
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
            'choices': result.get('choices') or [],
            'mode': result.get('mode') or mode,
        },
    )

    return jsonify({
        'ok': True,
        'session_id': session_id,
        'answer': result.get('answer') or '',
        'steps': result.get('steps') or [],
        'cites': result.get('cites') or [],
        'choices': result.get('choices') or [],
        'mode': result.get('mode') or mode,
    })
