"""Publish routes - real publishing via Playwright."""

from flask import Blueprint, request, jsonify
from config import get_db as _db
from modules.publisher import (
    publish_video, get_publish_status, check_playwright,
    list_sessions, close_session,
    sync_publish_engagement, apply_engagement_to_consult,
)

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
        task_id=id,
    )

    # Update task status
    conn = _db()
    sid = result.get('session_id') or ''
    if result['status'] == 'pending_review':
        conn.execute(
            'UPDATE publish_task SET status=?, error_msg=?, session_id=? WHERE id=?',
            ('reviewing', result['message'], sid, id)
        )
    elif result['status'] == 'need_login':
        conn.execute(
            'UPDATE publish_task SET status=?, error_msg=?, session_id=? WHERE id=?',
            ('reviewing', result['message'], sid, id)
        )
    elif result['status'] == 'error':
        conn.execute(
            'UPDATE publish_task SET status=?, error_msg=? WHERE id=?',
            ('failed', result['message'], id)
        )
    else:
        conn.execute(
            'UPDATE publish_task SET status=?, error_msg=?, session_id=? WHERE id=?',
            (result['status'], result.get('message', ''), sid, id)
        )
    conn.commit()
    conn.close()

    return jsonify(result)


@bp.route('/api/publish/<int:id>/confirm', methods=['POST'])
def confirm_publish(id):
    """用户在平台点完发布后，手动确认任务为已发布（可回写作品链接）。"""
    data = request.get_json(silent=True) or {}
    publish_url = (data.get('publish_url') or '').strip()
    got_consult = data.get('got_consult')
    conn = _db()
    row = conn.execute(
        'SELECT id, status, publish_url, session_id FROM publish_task WHERE id=?',
        (id,),
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({'error': '发布任务不存在'}), 404

    # 未手填时：优先用库内已自动抓到的链接，其次用会话检测到的链接
    if not publish_url:
        publish_url = (row['publish_url'] or '').strip()
    if not publish_url:
        sid = (row['session_id'] or '').strip()
        for s in list_sessions():
            if sid and s.get('id') == sid and s.get('detected_url'):
                publish_url = s['detected_url']
                break
            if s.get('task_id') == id and s.get('detected_url'):
                publish_url = s['detected_url']
                break

    if publish_url:
        conn.execute(
            "UPDATE publish_task SET status='done', publish_url=?, error_msg='', "
            "published_at=CURRENT_TIMESTAMP WHERE id=?",
            (publish_url, id),
        )
    else:
        conn.execute(
            "UPDATE publish_task SET status='done', error_msg='', "
            "published_at=CURRENT_TIMESTAMP WHERE id=?",
            (id,),
        )
    if got_consult is not None:
        conn.execute(
            'UPDATE publish_task SET got_consult=? WHERE id=?',
            (bool(got_consult), id),
        )
    conn.commit()
    conn.close()
    return jsonify({
        'message': '已标记为已发布',
        'status': 'done',
        'publish_url': publish_url or None,
        'got_consult': bool(got_consult) if got_consult is not None else None,
    })


@bp.route('/api/publish/<int:id>/sync', methods=['POST'])
def sync_publish(id):
    """从创作者后台同步作品链接与点赞/评论；有点赞或评论则自动标「有咨询」。"""
    conn = _db()
    row = conn.execute('SELECT * FROM publish_task WHERE id=?', (id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'error': '发布任务不存在'}), 404
    task = dict(row)
    conn.close()

    result = sync_publish_engagement(task)
    if not result.get('ok'):
        return jsonify({'error': result.get('error') or '同步失败', **result}), 400

    likes = int(result.get('likes') or 0)
    comments = int(result.get('comments') or 0)
    url = (result.get('publish_url') or '').strip()
    got = apply_engagement_to_consult(likes, comments)

    conn = _db()
    fields = ['likes=?', 'comments=?', 'engagement_synced_at=CURRENT_TIMESTAMP']
    params = [likes, comments]
    if url:
        fields.append('publish_url=?')
        params.append(url)
    if got:
        fields.append('got_consult=?')
        params.append(True)
    params.append(id)
    conn.execute(
        f'UPDATE publish_task SET {", ".join(fields)} WHERE id=?',
        params,
    )
    conn.commit()
    updated = dict(conn.execute('SELECT * FROM publish_task WHERE id=?', (id,)).fetchone())
    conn.close()

    return jsonify({
        'message': (
            f'已同步：赞 {likes} / 评 {comments}'
            + ('，已自动标记有咨询' if got else '')
            + ('，已回填作品链接' if url else '')
        ),
        'likes': likes,
        'comments': comments,
        'publish_url': url or updated.get('publish_url') or '',
        'got_consult': bool(updated.get('got_consult')),
        'matched': result.get('matched'),
        'task': updated,
    })


@bp.route('/api/publish/<int:id>', methods=['PUT'])
def update_publish(id):
    data = request.get_json(silent=True) or {}
    conn = _db()
    fields = []
    params = []
    for k in ['title', 'description', 'cover_text', 'tags', 'platform', 'scheduled_time',
              'status', 'publish_url', 'error_msg', 'got_consult', 'likes', 'comments']:
        if k in data:
            fields.append(f'{k}=?')
            val = data[k]
            if k == 'got_consult':
                val = bool(val)
            if k in ('likes', 'comments'):
                val = int(val or 0)
            params.append(val)
    if fields:
        params.append(id)
        conn.execute(f'UPDATE publish_task SET {",".join(fields)} WHERE id=?', params)
        conn.commit()
    conn.close()
    return jsonify({'message': '已更新'})


@bp.route('/api/publish/analytics')
def publish_analytics():
    """本周发布复盘：条数、按 content_type、咨询率。"""
    range_key = (request.args.get('range') or 'week').lower()
    days = 7 if range_key != 'month' else 30
    conn = _db()
    rows = conn.execute(
        f'''SELECT p.id, p.got_consult, p.platform, p.published_at, p.created_at,
                   COALESCE(s.content_type, 'traffic') AS content_type
            FROM publish_task p
            LEFT JOIN video_task v ON p.video_task_id = v.id
            LEFT JOIN script s ON v.script_id = s.id
            WHERE p.status = 'done'
              AND COALESCE(p.published_at, p.created_at)::date
                  >= CURRENT_DATE - INTERVAL '{days - 1} days'
            ORDER BY COALESCE(p.published_at, p.created_at) DESC'''
    ).fetchall()
    conn.close()

    by_type = {}
    consult = 0
    for r in rows:
        ct = r['content_type'] or 'traffic'
        by_type.setdefault(ct, {'count': 0, 'consult': 0})
        by_type[ct]['count'] += 1
        if r['got_consult']:
            by_type[ct]['consult'] += 1
            consult += 1
    total = len(rows)
    type_labels = {'traffic': '泛流量', 'insurance': '保险干货'}
    return jsonify({
        'range': range_key,
        'days': days,
        'published': total,
        'consult': consult,
        'consult_rate': round(consult / total, 3) if total else 0,
        'by_content_type': [
            {
                'key': k,
                'label': type_labels.get(k, k),
                'count': v['count'],
                'consult': v['consult'],
            }
            for k, v in by_type.items()
        ],
    })


@bp.route('/api/publish/<int:id>', methods=['DELETE'])
def delete_publish(id):
    conn = _db()
    conn.execute('DELETE FROM publish_task WHERE id=?', (id,))
    conn.commit()
    conn.close()
    return jsonify({'message': '已删除'})


@bp.route('/api/publish/sessions')
def publish_sessions():
    """当前保持打开的发布浏览器会话。"""
    return jsonify({'list': list_sessions()})


@bp.route('/api/publish/sessions/<sid>/close', methods=['POST'])
def publish_session_close(sid):
    return jsonify(close_session(sid))


@bp.route('/api/publish/status')
def publish_status():
    """Check publishing readiness for all platforms."""
    from modules.content_ops.platforms import list_platforms
    statuses = {}
    for p in list_platforms():
        if not p.get('enable_publish', True):
            continue
        statuses[p['key']] = get_publish_status(p['key'])
    statuses['playwright_installed'] = check_playwright()
    return jsonify(statuses)
