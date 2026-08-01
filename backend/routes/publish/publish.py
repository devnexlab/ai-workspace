"""Publish routes - real publishing via Playwright."""

from flask import Blueprint, request, jsonify
from config import get_db as _db
from modules.publisher import publish_video, get_publish_status, check_playwright

bp = Blueprint('publish', __name__)


@bp.route('/api/publish')
def list_publish():
    conn = _db()
    page = int(request.args.get('page', 1))
    pageSize = int(request.args.get('pageSize', 20))
    status = request.args.get('status', '')
    platform = request.args.get('platform', '')

    where = []
    params = []
    if status:
        where.append('p.status=?')
        params.append(status)
    if platform:
        where.append('p.platform=?')
        params.append(platform)

    where_clause = ('WHERE ' + ' AND '.join(where)) if where else ''
    offset = (page - 1) * pageSize

    total = conn.execute(
        f'SELECT COUNT(*) as c FROM publish_task p {where_clause}', params
    ).fetchone()['c']

    rows = conn.execute(
        f'''SELECT p.*, v.title as video_title, v.output_path
            FROM publish_task p LEFT JOIN video_task v ON p.video_task_id=v.id
            {where_clause} ORDER BY p.created_at DESC LIMIT ? OFFSET ?''',
        params + [pageSize, offset]
    ).fetchall()
    conn.close()

    return jsonify({
        'list': [dict(r) for r in rows],
        'page': page,
        'pageSize': pageSize,
        'total': total,
    })


@bp.route('/api/publish', methods=['POST'])
def create_publish():
    data = request.get_json(silent=True) or {}
    conn = _db()
    cur = conn.execute(
        '''INSERT INTO publish_task (video_task_id,title,description,cover_text,tags,platform,scheduled_time,status)
           VALUES (?,?,?,?,?,?,?,?)''',
        (data.get('video_task_id'), data.get('title', ''), data.get('description', ''),
         data.get('cover_text', ''), data.get('tags', ''), data.get('platform', ''),
         data.get('scheduled_time', ''), data.get('status', 'pending'))
    )
    conn.commit()
    conn.close()
    return jsonify({'id': cur.lastrowid, 'message': '发布任务已创建'})


@bp.route('/api/publish/<int:id>/publish', methods=['POST'])
def do_publish(id):
    """Execute publishing to the platform."""
    conn = _db()
    task = conn.execute(
        '''SELECT p.*, v.output_path FROM publish_task p
           LEFT JOIN video_task v ON p.video_task_id=v.id WHERE p.id=?''',
        (id,)
    ).fetchone()
    conn.close()

    if not task:
        return jsonify({'error': '发布任务不存在'}), 404

    task_dict = dict(task)
    video_path = task_dict.get('output_path', '')

    if not video_path:
        return jsonify({'error': '关联的视频文件不存在，请先完成视频制作'}), 400

    result = publish_video(
        platform=task_dict['platform'],
        video_path=video_path,
        title=task_dict.get('title', ''),
        description=task_dict.get('description', ''),
        tags=task_dict.get('tags', ''),
        cover_text=task_dict.get('cover_text', ''),
    )

    # Update task status
    conn = _db()
    if result['status'] == 'pending_review':
        conn.execute(
            'UPDATE publish_task SET status=?, error_msg=? WHERE id=?',
            ('reviewing', result['message'], id)
        )
    elif result['status'] == 'error':
        conn.execute(
            'UPDATE publish_task SET status=?, error_msg=? WHERE id=?',
            ('failed', result['message'], id)
        )
    else:
        conn.execute(
            'UPDATE publish_task SET status=?, error_msg=? WHERE id=?',
            (result['status'], result.get('message', ''), id)
        )
    conn.commit()
    conn.close()

    return jsonify(result)


@bp.route('/api/publish/<int:id>', methods=['PUT'])
def update_publish(id):
    data = request.get_json(silent=True) or {}
    conn = _db()
    fields = []
    params = []
    for k in ['title', 'description', 'cover_text', 'tags', 'platform', 'scheduled_time',
              'status', 'publish_url', 'error_msg']:
        if k in data:
            fields.append(f'{k}=?')
            params.append(data[k])
    if fields:
        params.append(id)
        conn.execute(f'UPDATE publish_task SET {",".join(fields)} WHERE id=?', params)
        conn.commit()
    conn.close()
    return jsonify({'message': '已更新'})


@bp.route('/api/publish/<int:id>', methods=['DELETE'])
def delete_publish(id):
    conn = _db()
    conn.execute('DELETE FROM publish_task WHERE id=?', (id,))
    conn.commit()
    conn.close()
    return jsonify({'message': '已删除'})


@bp.route('/api/publish/status')
def publish_status():
    """Check publishing readiness for all platforms."""
    statuses = {}
    for platform in ['douyin', 'xiaohongshu', 'shipinhao']:
        statuses[platform] = get_publish_status(platform)
    statuses['playwright_installed'] = check_playwright()
    return jsonify(statuses)
