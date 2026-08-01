"""Materials routes - upload and manage video materials (images/videos)."""

import os
from flask import Blueprint, request, jsonify, send_file
from config import MATERIALS_DIR, get_db as _db
from werkzeug.utils import secure_filename

bp = Blueprint('materials', __name__)

UPLOAD_DIR = str(MATERIALS_DIR)

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'}
VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm'}


@bp.route('/api/materials')
def list_materials():
    """List all materials, optionally filtered by type."""
    conn = _db()
    mtype = request.args.get('type', '')
    q = request.args.get('q', '')

    where = []
    params = []
    if mtype:
        where.append('type=?')
        params.append(mtype)
    if q:
        where.append('name LIKE ?')
        params.append(f'%{q}%')

    where_clause = ('WHERE ' + ' AND '.join(where)) if where else ''
    rows = conn.execute(
        f'SELECT * FROM video_material {where_clause} ORDER BY created_at DESC',
        params
    ).fetchall()
    conn.close()

    return jsonify({'list': [dict(r) for r in rows], 'total': len(rows)})


@bp.route('/api/materials', methods=['POST'])
def create_material():
    """Upload a new material file."""
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    if 'file' not in request.files:
        return jsonify({'error': '没有文件上传'}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({'error': '文件名为空'}), 400

    name = request.form.get('name', '') or os.path.splitext(file.filename)[0]
    tags = request.form.get('tags', '')
    filename = secure_filename(file.filename)
    if not filename:
        filename = 'material_' + str(int(__import__('time').time()))

    # Preserve original extension
    ext = os.path.splitext(file.filename)[1].lower()
    filename = filename + ext if not filename.lower().endswith(ext) else filename

    # Determine type
    if ext in IMAGE_EXTENSIONS:
        mtype = 'image'
    elif ext in VIDEO_EXTENSIONS:
        mtype = 'video'
    else:
        return jsonify({'error': f'不支持的文件类型: {ext}'}), 400

    # Save file with unique name
    import time
    unique_name = f'{int(time.time() * 1000)}_{filename}'
    file_path = os.path.join(UPLOAD_DIR, unique_name)
    file.save(file_path)

    # Generate thumbnail for videos using ffprobe/ffmpeg
    thumbnail = ''
    if mtype == 'video':
        try:
            from modules.video_maker import _get_ffmpeg_path
            ffmpeg = _get_ffmpeg_path()
            thumb_path = os.path.join(UPLOAD_DIR, unique_name + '_thumb.jpg')
            import subprocess
            subprocess.run(
                [ffmpeg, '-i', file_path, '-ss', '00:00:01', '-vframes', '1',
                 '-q:v', '2', '-y', thumb_path],
                capture_output=True, text=True, timeout=30
            )
            if os.path.exists(thumb_path):
                thumbnail = thumb_path
        except Exception:
            pass
    elif mtype == 'image':
        thumbnail = file_path

    conn = _db()
    cur = conn.execute(
        '''INSERT INTO video_material (name, type, file_path, thumbnail, tags)
           VALUES (?,?,?,?,?)''',
        (name, mtype, file_path, thumbnail, tags)
    )
    conn.commit()
    material_id = cur.lastrowid
    conn.close()

    return jsonify({'id': material_id, 'message': '素材上传成功'})


@bp.route('/api/materials/<int:id>', methods=['DELETE'])
def delete_material(id):
    """Delete a material and its file."""
    conn = _db()
    row = conn.execute('SELECT * FROM video_material WHERE id=?', (id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'error': '素材不存在'}), 404

    # Delete file
    file_path = row['file_path']
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError:
            pass

    # Delete thumbnail
    thumb = row['thumbnail']
    if thumb and thumb != file_path and os.path.exists(thumb):
        try:
            os.remove(thumb)
        except OSError:
            pass

    conn.execute('DELETE FROM video_material WHERE id=?', (id,))
    conn.commit()
    conn.close()
    return jsonify({'message': '已删除'})


@bp.route('/api/materials/<int:id>/preview')
def preview_material(id):
    """Serve material file for preview."""
    conn = _db()
    row = conn.execute('SELECT * FROM video_material WHERE id=?', (id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'not found'}), 404

    file_path = row['file_path']
    if not file_path or not os.path.exists(file_path):
        return jsonify({'error': '文件不存在'}), 404

    mtype = row['type']
    mimetype = 'image/jpeg' if mtype == 'image' else 'video/mp4'
    return send_file(os.path.abspath(file_path), as_attachment=False, mimetype=mimetype)


@bp.route('/api/materials/styles')
def list_styles():
    """List available video style presets."""
    from modules.video_maker import get_available_styles
    return jsonify({'styles': get_available_styles()})
