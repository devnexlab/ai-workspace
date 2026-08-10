"""Videos routes - real video production pipeline."""

import os
import json
import threading
from datetime import datetime
from flask import Blueprint, request, jsonify, send_file
from config import OUTPUT_DIR as _OUTPUT_DIR, get_db as _db, get_setting, update_setting, get_settings_by_category, get_video_config, get_tts_config
from modules import video_maker

bp = Blueprint('videos', __name__)

OUTPUT_DIR = str(_OUTPUT_DIR)

# Track running background tasks: {task_id: thread}
_running_tasks = {}


def _mark_compose_start(conn, task_id):
    conn.execute(
        '''UPDATE video_task SET compose_started_at=?, compose_elapsed_sec=? WHERE id=?''',
        (datetime.now(), 0, task_id),
    )


def _compose_elapsed_sec(conn, task_id):
    row = conn.execute(
        'SELECT compose_started_at FROM video_task WHERE id=?', (task_id,)
    ).fetchone()
    if not row or not row['compose_started_at']:
        return None
    started = row['compose_started_at']
    if isinstance(started, str):
        try:
            started = datetime.strptime(started[:19], '%Y-%m-%d %H:%M:%S')
        except ValueError:
            return None
    return max(0.0, (datetime.now() - started).total_seconds())


def _mark_compose_finish(conn, task_id, extra_sql='', extra_params=()):
    """写入合成耗时；extra_sql 为额外 SET 片段（勿含 SET 关键字）。"""
    elapsed = _compose_elapsed_sec(conn, task_id)
    sets = ['compose_elapsed_sec=?']
    params = [elapsed if elapsed is not None else 0]
    if extra_sql:
        sets.append(extra_sql)
        params.extend(extra_params)
    params.append(task_id)
    conn.execute(f'UPDATE video_task SET {", ".join(sets)} WHERE id=?', params)


def _persist_video_prefs(task_dict):
    """Remember last successful export params for next create/produce."""
    if not task_dict:
        return
    mapping = {
        'last_voice': task_dict.get('voice') or '',
        'last_voice_rate': task_dict.get('voice_rate') or '',
        'last_resolution': task_dict.get('resolution') or '1080x1920',
        'last_video_style': task_dict.get('video_style') or 'default',
        'last_material_ids': task_dict.get('material_ids') or '',
        'last_narration_prompt': task_dict.get('narration_prompt') or '',
        'last_fps': task_dict.get('fps') or '30',
        'last_render_quality': task_dict.get('render_quality') or 'high',
        'last_video_engine': task_dict.get('video_engine') or 'moviepy',
        'last_fade_transition': task_dict.get('fade_transition') or 'true',
        'last_title_overlay': task_dict.get('title_overlay') or 'true',
        'last_compose_layout': task_dict.get('compose_layout') or 'default',
        'last_person_material_id': str(task_dict.get('person_material_id') or ''),
        'last_bg_material_id': str(task_dict.get('bg_material_id') or ''),
    }
    for key, value in mapping.items():
        try:
            update_setting('video_prefs', key, str(value))
        except Exception as e:
            print(f'[VideoPrefs] save {key} failed: {e}')


def get_last_video_prefs():
    """Merge saved prefs with system TTS/video defaults."""
    prefs = get_settings_by_category('video_prefs') or {}
    vcfg = get_video_config() or {}
    tcfg = get_tts_config() or {}
    return {
        'voice': prefs.get('last_voice') or tcfg.get('voice') or '',
        'voice_rate': prefs.get('last_voice_rate') or tcfg.get('rate') or '',
        'resolution': prefs.get('last_resolution') or vcfg.get('default_resolution') or '1080x1920',
        'video_style': prefs.get('last_video_style') or 'default',
        'material_ids': prefs.get('last_material_ids') or '',
        'narration_prompt': prefs.get('last_narration_prompt') or '',
        'fps': prefs.get('last_fps') or vcfg.get('default_fps') or '30',
        'render_quality': prefs.get('last_render_quality') or vcfg.get('default_render_quality') or 'high',
        'video_engine': prefs.get('last_video_engine') or vcfg.get('default_video_engine') or 'moviepy',
        'fade_transition': prefs.get('last_fade_transition') or vcfg.get('default_fade_transition') or 'true',
        'title_overlay': prefs.get('last_title_overlay') or vcfg.get('default_title_overlay') or 'true',
        'compose_layout': prefs.get('last_compose_layout') or 'default',
        'person_material_id': prefs.get('last_person_material_id') or '',
        'bg_material_id': prefs.get('last_bg_material_id') or '',
        'has_saved': bool(prefs.get('last_voice') or prefs.get('last_video_style') or prefs.get('last_resolution')),
    }


def _get_material_paths(material_ids_str):
    """Look up material file paths from comma-separated IDs.
    Returns (image_paths, video_paths, bgm_paths) — scenes only for image/video.
    """
    if not material_ids_str:
        return [], [], []
    try:
        ids = [int(x.strip()) for x in material_ids_str.split(',') if x.strip()]
    except ValueError:
        return [], [], []

    if not ids:
        return [], [], []

    conn = _db()
    placeholders = ','.join('?' * len(ids))
    rows = conn.execute(
        f'SELECT * FROM video_material WHERE id IN ({placeholders})', ids
    ).fetchall()
    conn.close()

    image_paths = []
    video_paths = []
    bgm_paths = []
    for row in rows:
        path = row['file_path']
        if not path or not os.path.exists(path):
            continue
        kind = (row.get('asset_kind') or 'scene')
        mtype = row['type']
        if kind == 'bgm' or mtype == 'audio':
            bgm_paths.append(path)
        elif mtype == 'video':
            video_paths.append(path)
        elif kind != 'cover':
            image_paths.append(path)

    return image_paths, video_paths, bgm_paths


def _get_material_paths_dict(material_ids_str):
    """Return material paths as dict {images, videos, bgm}."""
    images, videos, bgm = _get_material_paths(material_ids_str)
    return {'images': images, 'videos': videos, 'bgm': bgm}


def _material_file_by_id(material_id):
    """Return absolute file_path for one material id, or ''."""
    if not material_id:
        return ''
    try:
        mid = int(material_id)
    except (TypeError, ValueError):
        return ''
    conn = _db()
    row = conn.execute('SELECT file_path FROM video_material WHERE id=?', (mid,)).fetchone()
    conn.close()
    if not row:
        return ''
    path = row['file_path'] or ''
    return path if path and os.path.exists(path) else path


def _talking_paths_from_task(task_dict):
    """Resolve person/bg paths for 口播模板."""
    person_path = _material_file_by_id(task_dict.get('person_material_id'))
    bg_path = _material_file_by_id(task_dict.get('bg_material_id'))
    return person_path, bg_path


def _row_asset_kind(row):
    if hasattr(row, 'get'):
        return row.get('asset_kind') or 'scene'
    try:
        return row['asset_kind'] or 'scene'
    except Exception:
        return 'scene'


def _get_material_info(material_ids_str):
    """Return material info list for scene matching: [{index, name, type, tags, file_path}].

    Only scene image/video materials are included (skip BGM / cover / audio).
    Indices are contiguous from 0 for AI matching.
    """
    if not material_ids_str:
        return []
    try:
        ids = [int(x.strip()) for x in str(material_ids_str).split(',') if x.strip()]
    except ValueError:
        return []

    if not ids:
        return []

    conn = _db()
    placeholders = ','.join('?' * len(ids))
    rows = conn.execute(
        f'SELECT * FROM video_material WHERE id IN ({placeholders})', ids
    ).fetchall()
    conn.close()

    # int() 统一 key，避免 PG/驱动返回类型不一致导致查不到
    row_map = {}
    for row in rows:
        try:
            row_map[int(row['id'])] = row
        except (TypeError, ValueError):
            continue

    info_list = []
    for mid in ids:
        row = row_map.get(mid)
        if not row:
            continue
        file_path = row['file_path'] or ''
        kind = _row_asset_kind(row)
        mtype = row['type']
        if kind == 'bgm' or mtype == 'audio' or kind == 'cover':
            continue
        # 文件缺失仍参与分镜匹配（否则前端已选素材却被静默丢弃）
        info_list.append({
            'index': len(info_list),
            'id': int(row['id']),
            'name': row['name'],
            'type': row['type'],
            'tags': row['tags'] or '',
            'file_path': file_path,
            'file_missing': bool(file_path and not os.path.exists(file_path)),
        })

    return info_list


def _material_ids_diagnostic(material_ids_str):
    """Explain why scene materials are empty (for API error messages)."""
    raw = (material_ids_str or '').strip()
    if not raw:
        return 'empty'
    try:
        ids = [int(x.strip()) for x in raw.split(',') if x.strip()]
    except ValueError:
        return 'invalid'
    if not ids:
        return 'empty'
    conn = _db()
    placeholders = ','.join('?' * len(ids))
    rows = conn.execute(
        f'SELECT * FROM video_material WHERE id IN ({placeholders})', ids
    ).fetchall()
    conn.close()
    if not rows:
        return 'not_found'
    scene_like = 0
    for row in rows:
        kind = _row_asset_kind(row)
        mtype = row['type']
        if kind == 'bgm' or mtype == 'audio' or kind == 'cover':
            continue
        scene_like += 1
    if scene_like == 0:
        return 'only_bgm_or_cover'
    return 'unknown'


@bp.route('/api/videos/last-prefs')
def last_prefs():
    return jsonify(get_last_video_prefs())


@bp.route('/api/videos')
def list_videos():
    conn = _db()
    page = int(request.args.get('page', 1))
    pageSize = int(request.args.get('pageSize', 20))
    export_status = request.args.get('export_status', '')
    q = request.args.get('q', '')

    where = []
    params = []
    if export_status:
        where.append('v.export_status=?')
        params.append(export_status)
    if q:
        where.append('v.title LIKE ?')
        params.append(f'%{q}%')

    where_clause = ('WHERE ' + ' AND '.join(where)) if where else ''
    offset = (page - 1) * pageSize

    total = conn.execute(
        f'SELECT COUNT(*) as c FROM video_task v {where_clause}', params
    ).fetchone()['c']

    rows = conn.execute(
        f'''SELECT v.*, s.title as script_title
            FROM video_task v LEFT JOIN script s ON v.script_id=s.id
            {where_clause} ORDER BY v.created_at DESC LIMIT ? OFFSET ?''',
        params + [pageSize, offset]
    ).fetchall()

    # 顶部 KPI：全库统计（不受分页影响；也不受当前筛选影响，避免筛「已完成」时其它卡片变 0）
    stats_row = conn.execute(
        '''SELECT
             COUNT(*) AS total,
             COUNT(*) FILTER (WHERE COALESCE(export_status, '') = 'done') AS done,
             COUNT(*) FILTER (
               WHERE COALESCE(export_status, '') = 'failed'
                  OR COALESCE(voice_status, '') = 'failed'
                  OR COALESCE(subtitle_status, '') = 'failed'
                  OR COALESCE(video_status, '') = 'failed'
             ) AS failed,
             COUNT(*) FILTER (
               WHERE COALESCE(export_status, '') NOT IN ('done', 'failed')
                 AND (
                   COALESCE(voice_status, '') = 'processing'
                   OR COALESCE(subtitle_status, '') = 'processing'
                   OR COALESCE(video_status, '') = 'processing'
                   OR COALESCE(export_status, '') = 'processing'
                   OR (
                     COALESCE(export_status, 'pending') = 'pending'
                     AND COALESCE(voice_status, 'pending') != 'pending'
                   )
                 )
             ) AS processing,
             COUNT(*) FILTER (
               WHERE COALESCE(export_status, 'pending') = 'pending'
                 AND COALESCE(voice_status, 'pending') = 'pending'
                 AND COALESCE(video_status, 'pending') = 'pending'
             ) AS pending
           FROM video_task'''
    ).fetchone()
    conn.close()

    stats = dict(stats_row) if stats_row else {
        'total': 0, 'done': 0, 'failed': 0, 'processing': 0, 'pending': 0,
    }

    return jsonify({
        'list': [dict(r) for r in rows],
        'page': page,
        'pageSize': pageSize,
        'total': total,
        'stats': stats,
    })


@bp.route('/api/videos/<int:id>')
def get_video(id):
    conn = _db()
    row = conn.execute(
        '''SELECT v.*, s.title as script_title, s.hook, s.content, s.ending
           FROM video_task v LEFT JOIN script s ON v.script_id=s.id WHERE v.id=?''',
        (id,)
    ).fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'not found'}), 404
    return jsonify(dict(row))


@bp.route('/api/videos', methods=['POST'])
def create_video():
    data = request.get_json(silent=True) or {}
    person_id = data.get('person_material_id') or None
    bg_id = data.get('bg_material_id') or None
    try:
        person_id = int(person_id) if person_id not in (None, '', 0, '0') else None
    except (TypeError, ValueError):
        person_id = None
    try:
        bg_id = int(bg_id) if bg_id not in (None, '', 0, '0') else None
    except (TypeError, ValueError):
        bg_id = None
    # 口播模板：material_ids 同步为人像+背景，便于列表展示
    material_ids = data.get('material_ids', '') or ''
    layout = (data.get('compose_layout') or 'default').strip() or 'default'
    if layout == 'talking':
        ids = [str(x) for x in (person_id, bg_id) if x]
        if ids:
            material_ids = ','.join(ids)

    conn = _db()
    cur = conn.execute(
        '''INSERT INTO video_task (script_id,title,video_style,material_ids,
           resolution,fps,render_quality,fade_transition,title_overlay,video_engine,
           narration_prompt,voice,voice_rate,compose_layout,person_material_id,bg_material_id,
           voice_status,subtitle_status,video_status,export_status)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (data.get('script_id'), data.get('title', ''),
         data.get('video_style', 'default'), material_ids,
         data.get('resolution', '1080x1920'), data.get('fps', '30'),
         data.get('render_quality', 'high'), data.get('fade_transition', 'true'),
         data.get('title_overlay', 'true'), data.get('video_engine', 'moviepy'),
         data.get('narration_prompt', ''), data.get('voice', ''), data.get('voice_rate', ''),
         layout, person_id, bg_id,
         'pending', 'pending', 'pending', 'pending')
    )
    script_id = data.get('script_id')
    if script_id:
        conn.execute('UPDATE script SET status=? WHERE id=?', ('used', script_id))
    conn.commit()
    video_id = cur.lastrowid
    conn.close()
    return jsonify({'id': video_id, 'message': '视频任务已创建'})


@bp.route('/api/videos/<int:id>/execute/<step>', methods=['POST'])
def execute_step(id, step):
    """Execute a single step of the video production pipeline.

    Steps: voice, subtitle, compose, all

    For 'compose' and 'all' steps, runs in background thread to avoid
    HTTP timeout (MoviePy rendering can take 10+ minutes).
    """
    conn = _db()
    task = conn.execute('SELECT * FROM video_task WHERE id=?', (id,)).fetchone()
    if not task:
        conn.close()
        return jsonify({'error': '任务不存在'}), 404

    task_dict = dict(task)

    # Get the script
    script = conn.execute('SELECT * FROM script WHERE id=?', (task['script_id'],)).fetchone()
    conn.close()

    if not script:
        return jsonify({'error': '关联的文案不存在'}), 400

    script_dict = dict(script)

    # For long-running steps (compose, all), run in background thread
    if step in ('compose', 'all'):
        # Check if already running
        if id in _running_tasks and _running_tasks[id].is_alive():
            return jsonify({'error': '该任务正在执行中，请等待完成'}), 409

        # Mark as processing immediately
        conn = _db()
        if step == 'all':
            conn.execute(
                'UPDATE video_task SET voice_status=?, subtitle_status=?, video_status=?, export_status=?, error_msg=? WHERE id=?',
                ('processing', 'processing', 'processing', 'processing', '', id)
            )
        else:
            # 重试合成时必须同时清掉 export_status=failed，否则前端仍显示「合成失败」和重试按钮
            conn.execute(
                'UPDATE video_task SET video_status=?, export_status=?, error_msg=? WHERE id=?',
                ('processing', 'processing', '', id)
            )
        _mark_compose_start(conn, id)
        conn.commit()
        conn.close()

        # Start background thread
        thread = threading.Thread(
            target=_run_video_step_background,
            args=(id, step, script_dict, task_dict),
            daemon=True
        )
        _running_tasks[id] = thread
        thread.start()

        return jsonify({
            'message': f'{step} 已开始后台执行，请稍后查看状态',
            'task_id': id,
            'status': 'processing',
        })

    # For voice and subtitle steps, run synchronously (they're fast)
    task_output_dir = os.path.join(OUTPUT_DIR, f'task_{id}')
    os.makedirs(task_output_dir, exist_ok=True)

    try:
        if step == 'voice':
            # Build narration text from script
            narration = ''
            if script_dict.get('hook'):
                narration += script_dict['hook'] + '\n'
            narration += script_dict.get('content', '')
            if script_dict.get('ending'):
                narration += '\n' + script_dict['ending']

            if not narration.strip():
                return jsonify({'error': '文案内容为空'}), 400

            # AI narration rewrite if prompt is provided
            narration_prompt = task_dict.get('narration_prompt', '').strip()
            if narration_prompt:
                try:
                    from modules.ai_writer import generate_narration
                    rewritten = generate_narration(script_dict, narration_prompt)
                    if rewritten.strip():
                        narration = rewritten
                        # Save narration text for reference
                        narration_path = os.path.join(task_output_dir, 'narration.txt')
                        with open(narration_path, 'w', encoding='utf-8') as f:
                            f.write(narration)
                except Exception as e:
                    print(f'[Voice] AI narration rewrite failed: {e}')

            audio_path = os.path.join(task_output_dir, f'audio.mp3')
            voice = task_dict.get('voice', '') or None
            voice_rate = task_dict.get('voice_rate', '') or None
            result = video_maker.generate_tts(narration, audio_path, voice=voice, rate=voice_rate)

            # Save word boundaries for the subtitle step
            import json as _json
            boundaries_path = os.path.join(task_output_dir, f'word_boundaries.json')
            with open(boundaries_path, 'w', encoding='utf-8') as f:
                _json.dump(result.get('word_boundaries', []), f, ensure_ascii=False)

            conn = _db()
            # 配音更新后作废下游：字幕/合成需按新音频重做
            conn.execute(
                '''UPDATE video_task SET voice_status=?, voice_url=?, duration=?,
                   subtitle_status=?, subtitle_url=?,
                   video_status=?, export_status=?, video_path=?, output_path=?, error_msg=?
                   WHERE id=?''',
                (
                    'done', audio_path, result['duration'],
                    'pending', '',
                    'pending', 'pending', '', '', '',
                    id,
                )
            )
            conn.commit()
            conn.close()
            return jsonify({'message': '配音完成', 'result': result})

        elif step == 'subtitle':
            if (task_dict.get('voice_status') or '') != 'done' or not (task_dict.get('voice_url') or '').strip():
                return jsonify({'error': '请先完成配音步骤'}), 400

            conn = _db()
            conn.execute(
                'UPDATE video_task SET subtitle_status=?, error_msg=? WHERE id=?',
                ('processing', '', id),
            )
            conn.commit()
            conn.close()

            # Try to load narration text saved from the voice step (may be AI-rewritten)
            narration = ''
            narration_candidates = [
                os.path.join(task_output_dir, 'narration.txt'),
                os.path.join(task_output_dir, f'task_{id}_narration.txt'),
            ]
            for narration_path in narration_candidates:
                if os.path.exists(narration_path):
                    try:
                        with open(narration_path, 'r', encoding='utf-8') as f:
                            narration = f.read()
                        if narration.strip():
                            break
                    except Exception:
                        pass

            # Fallback: build narration from original script
            if not narration.strip():
                if script_dict.get('hook'):
                    narration += script_dict['hook'] + '\n'
                narration += script_dict.get('content', '')
                if script_dict.get('ending'):
                    narration += '\n' + script_dict['ending']

            if not narration.strip():
                conn = _db()
                conn.execute(
                    'UPDATE video_task SET subtitle_status=?, error_msg=? WHERE id=?',
                    ('failed', '文案内容为空，无法生成字幕', id),
                )
                conn.commit()
                conn.close()
                return jsonify({'error': '文案内容为空，无法生成字幕'}), 400

            duration = task_dict.get('duration', 0) or 30

            # Try to load word boundaries saved from the voice step
            import json as _json
            word_boundaries = None
            for boundaries_path in (
                os.path.join(task_output_dir, 'word_boundaries.json'),
                os.path.join(task_output_dir, f'task_{id}_boundaries.json'),
            ):
                if os.path.exists(boundaries_path):
                    try:
                        with open(boundaries_path, 'r', encoding='utf-8') as f:
                            word_boundaries = _json.load(f)
                        break
                    except Exception:
                        pass

            sub_path = os.path.join(task_output_dir, f'subtitle.srt')
            result = video_maker.generate_subtitle(narration, duration, sub_path, word_boundaries)
            if not result.get('subtitle_path') or not os.path.exists(result.get('subtitle_path') or ''):
                raise Exception('字幕文件未生成')

            conn = _db()
            conn.execute(
                '''UPDATE video_task SET subtitle_status=?, subtitle_url=?,
                   video_status=?, export_status=?, video_path=?, output_path=?, error_msg=?
                   WHERE id=?''',
                (
                    'done', result['subtitle_path'],
                    'pending', 'pending', '', '', '',
                    id,
                )
            )
            conn.commit()
            conn.close()
            sync_note = ' (TTS同步)' if word_boundaries else ' (均匀分配)'
            return jsonify({'message': f'字幕生成完成{sync_note}', 'result': result})

        else:
            return jsonify({'error': f'未知步骤: {step}'}), 400

    except Exception as e:
        conn = _db()
        status_col = 'voice_status' if step == 'voice' else ('subtitle_status' if step == 'subtitle' else None)
        if status_col:
            conn.execute(
                f'UPDATE video_task SET {status_col}=?, error_msg=? WHERE id=?',
                ('failed', str(e), id),
            )
        else:
            conn.execute('UPDATE video_task SET error_msg=? WHERE id=?', (str(e), id))
        conn.commit()
        conn.close()
        return jsonify({'error': str(e)}), 500


def _run_video_step_background(task_id, step, script_dict, task_dict):
    """Run video composition step in a background thread.

    Updates the database with results or error when done.
    """
    task_output_dir = os.path.join(OUTPUT_DIR, f'task_{task_id}')
    os.makedirs(task_output_dir, exist_ok=True)

    try:
        if step == 'compose':
            # 后台启动时 task_dict 可能是旧快照；合成前再读一次最新配音/字幕路径
            conn = _db()
            fresh = conn.execute(
                'SELECT voice_url, subtitle_url, voice_status, subtitle_status FROM video_task WHERE id=?',
                (task_id,),
            ).fetchone()
            conn.close()
            if fresh:
                task_dict = {**task_dict, **dict(fresh)}

            audio_path = (task_dict.get('voice_url') or '').strip()
            sub_path = (task_dict.get('subtitle_url') or '').strip()

            if (task_dict.get('voice_status') or '') != 'done' or not audio_path or not os.path.exists(audio_path):
                conn = _db()
                _mark_compose_finish(
                    conn, task_id,
                    'video_status=?, export_status=?, error_msg=?',
                    ('failed', 'failed', '请先完成配音步骤'),
                )
                conn.commit()
                conn.close()
                return

            if (task_dict.get('subtitle_status') or '') != 'done' or not sub_path or not os.path.exists(sub_path):
                conn = _db()
                _mark_compose_finish(
                    conn, task_id,
                    'video_status=?, export_status=?, error_msg=?',
                    ('failed', 'failed', '请先完成字幕步骤'),
                )
                conn.commit()
                conn.close()
                return

            # Get materials from material_ids
            material_ids_str = task_dict.get('material_ids', '')
            image_paths, video_paths, bgm_paths = _get_material_paths(material_ids_str)

            # If no user materials, try configured image source
            if not image_paths and not video_paths:
                keywords = script_dict.get('tags', script_dict.get('title', ''))
                image_paths = video_maker.get_images(keywords, count=5)

            video_style = task_dict.get('video_style', 'default')
            video_path = os.path.join(task_output_dir, f'video.mp4')
            title_text = script_dict.get('title', '')

            task_params = {
                'resolution': task_dict.get('resolution', '1080x1920'),
                'fps': task_dict.get('fps', '30'),
                'render_quality': task_dict.get('render_quality', 'high'),
                'fade_transition': task_dict.get('fade_transition', 'true'),
                'title_overlay': task_dict.get('title_overlay', 'true'),
                'video_engine': task_dict.get('video_engine', 'moviepy'),
                'narration_prompt': task_dict.get('narration_prompt', ''),
                'voice': task_dict.get('voice', ''),
                'voice_rate': task_dict.get('voice_rate', ''),
                'bgm_path': bgm_paths[0] if bgm_paths else '',
                'bgm_volume': get_setting('video', 'bgm_volume', '0.12') or '0.12',
                'compose_layout': task_dict.get('compose_layout') or 'default',
            }
            if (task_dict.get('compose_layout') or '') == 'talking':
                person_path, bg_path = _talking_paths_from_task(task_dict)
                task_params['person_path'] = person_path
                task_params['bg_path'] = bg_path

            # 单独点「合成」时也要带上已保存的分镜，否则会走顺序铺素材且裁切易丢主体
            pre_scenes = None
            scenes_json_str = task_dict.get('scenes_json') or ''
            if scenes_json_str and (task_dict.get('compose_layout') or '') != 'talking':
                try:
                    pre_scenes = json.loads(scenes_json_str)
                except json.JSONDecodeError:
                    pre_scenes = None

            result = video_maker.compose_video(
                audio_path, sub_path, image_paths, video_path,
                title_text=title_text,
                video_style=video_style,
                video_paths=None if task_params.get('compose_layout') == 'talking' else (video_paths if video_paths else None),
                task_params=task_params,
                scenes=pre_scenes,
            )

            conn = _db()
            _mark_compose_finish(
                conn, task_id,
                'video_status=?, video_path=?, export_status=?, output_path=?',
                ('done', result['video_path'], 'done', result['video_path']),
            )
            conn.commit()
            conn.close()
            _persist_video_prefs(task_dict)
            print(f'[BackgroundTask] Compose done for task {task_id}')

        elif step == 'all':
            # Run full pipeline
            material_ids_str = task_dict.get('material_ids', '')
            material_paths = _get_material_paths_dict(material_ids_str)
            materials_info = _get_material_info(material_ids_str)
            video_style = task_dict.get('video_style', 'default')

            # Load pre-generated scenes if available（口播模板不用分镜）
            pre_scenes = None
            is_talking = (task_dict.get('compose_layout') or '') == 'talking'
            scenes_json_str = task_dict.get('scenes_json', '')
            if scenes_json_str and not is_talking:
                try:
                    pre_scenes = json.loads(scenes_json_str)
                    print(f'[BackgroundTask] Loaded {len(pre_scenes)} pre-generated scenes')
                except json.JSONDecodeError:
                    pass

            task_params = {
                'resolution': task_dict.get('resolution', '1080x1920'),
                'fps': task_dict.get('fps', '30'),
                'render_quality': task_dict.get('render_quality', 'high'),
                'fade_transition': task_dict.get('fade_transition', 'true'),
                'title_overlay': task_dict.get('title_overlay', 'true'),
                'video_engine': task_dict.get('video_engine', 'moviepy'),
                'narration_prompt': task_dict.get('narration_prompt', ''),
                'voice': task_dict.get('voice', ''),
                'voice_rate': task_dict.get('voice_rate', ''),
                'bgm_path': (material_paths.get('bgm') or [None])[0] or '',
                'bgm_volume': get_setting('video', 'bgm_volume', '0.12') or '0.12',
                'compose_layout': task_dict.get('compose_layout') or 'default',
            }
            if is_talking:
                person_path, bg_path = _talking_paths_from_task(task_dict)
                task_params['person_path'] = person_path
                task_params['bg_path'] = bg_path

            result = video_maker.produce_video(
                script_dict, task_id, task_output_dir,
                video_style=video_style,
                material_paths=material_paths if not is_talking else {'images': [], 'videos': [], 'bgm': material_paths.get('bgm') or []},
                task_params=task_params,
                materials_info=None if is_talking else (materials_info if not pre_scenes else None),
                pre_scenes=None if is_talking else pre_scenes,
            )

            conn = _db()
            elapsed = _compose_elapsed_sec(conn, task_id)
            conn.execute(
                '''UPDATE video_task SET voice_status=?, voice_url=?, subtitle_status=?,
                   subtitle_url=?, video_status=?, video_path=?, export_status=?,
                   output_path=?, duration=?, error_msg=?, compose_elapsed_sec=? WHERE id=?''',
                (result.get('voice_status', 'pending'),
                 result.get('voice', {}).get('audio_path', ''),
                 result.get('subtitle_status', 'pending'),
                 result.get('subtitle', {}).get('subtitle_path', ''),
                 result.get('video_status', 'pending'),
                 result.get('video', {}).get('video_path', ''),
                 result.get('export_status', 'pending'),
                 result.get('output_path', ''),
                 result.get('voice', {}).get('duration', 0),
                 result.get('error_msg', ''),
                 elapsed if elapsed is not None else 0,
                 task_id)
            )
            # Save updated scenes (with timings) if available
            if result.get('scenes'):
                conn.execute('UPDATE video_task SET scenes_json=? WHERE id=?',
                             (json.dumps(result['scenes'], ensure_ascii=False), task_id))
            conn.commit()
            conn.close()
            if result.get('export_status') == 'done':
                _persist_video_prefs(task_dict)
            print(f'[BackgroundTask] Full pipeline done for task {task_id}')

    except Exception as e:
        import traceback
        traceback.print_exc()
        conn = _db()
        elapsed = _compose_elapsed_sec(conn, task_id)
        # all 步骤失败时，把仍停在 processing 的配音/字幕一并标失败，避免前端一直转圈
        conn.execute(
            '''UPDATE video_task SET
                 voice_status=CASE WHEN voice_status='processing' THEN 'failed' ELSE voice_status END,
                 subtitle_status=CASE WHEN subtitle_status='processing' THEN 'failed' ELSE subtitle_status END,
                 video_status=?, export_status=?, error_msg=?, compose_elapsed_sec=? WHERE id=?''',
            ('failed', 'failed', str(e), elapsed if elapsed is not None else 0, task_id)
        )
        conn.commit()
        conn.close()
        print(f'[BackgroundTask] Error for task {task_id}: {e}')

    # Clean up thread reference
    if task_id in _running_tasks:
        del _running_tasks[task_id]


@bp.route('/api/videos/<int:id>', methods=['PUT'])
def update_video(id):
    data = request.get_json(silent=True) or {}
    conn = _db()
    fields = []
    params = []
    for k in ['title', 'voice_status', 'subtitle_status', 'video_status', 'export_status',
              'voice_url', 'subtitle_url', 'video_path', 'output_path', 'error_msg',
              'material_ids', 'video_style', 'resolution', 'voice', 'voice_rate', 'narration_prompt',
              'compose_layout', 'person_material_id', 'bg_material_id',
              'fps', 'render_quality', 'fade_transition', 'title_overlay', 'video_engine']:
        if k in data:
            fields.append(f'{k}=?')
            params.append(data[k])
    if fields:
        params.append(id)
        conn.execute(f'UPDATE video_task SET {",".join(fields)} WHERE id=?', params)
        conn.commit()
    conn.close()
    return jsonify({'message': '已更新'})


@bp.route('/api/videos/<int:id>', methods=['DELETE'])
def delete_video(id):
    conn = _db()
    conn.execute('DELETE FROM video_task WHERE id=?', (id,))
    conn.commit()
    conn.close()
    return jsonify({'message': '已删除'})


@bp.route('/api/videos/check-ffmpeg')
def check_ffmpeg():
    return jsonify({'available': video_maker.check_ffmpeg()})


@bp.route('/api/videos/voice-options')
def voice_options():
    """Return available TTS voices and narration style presets."""
    from modules.video_maker import get_voice_options_for_api
    from modules.ai_writer import NARRATION_PRESETS
    return jsonify({
        'voices': get_voice_options_for_api(),
        'narration_presets': [{'value': k, 'label': v} for k, v in NARRATION_PRESETS.items()],
    })


# ============================================================
# Scene management APIs - AI scene segmentation + material matching
# ============================================================

def _build_narration_for_task(task_dict, script_dict):
    """Build narration text from script, applying AI rewrite if narration_prompt is set."""
    narration = ''
    if script_dict.get('hook'):
        narration += script_dict['hook'] + '\n'
    narration += script_dict.get('content', '')
    if script_dict.get('ending'):
        narration += '\n' + script_dict['ending']

    if not narration.strip():
        return ''

    # AI narration rewrite if prompt is provided
    narration_prompt = task_dict.get('narration_prompt', '').strip()
    if narration_prompt:
        try:
            from modules.ai_writer import generate_narration
            rewritten = generate_narration(script_dict, narration_prompt)
            if rewritten.strip():
                narration = rewritten
        except Exception as e:
            print(f'[Scene] AI narration rewrite failed: {e}')

    return narration


@bp.route('/api/videos/<int:id>/generate-scenes', methods=['POST'])
def generate_scenes_api(id):
    """Generate scenes via AI and auto-match materials.

    Body (optional):
        narration_override: str - custom narration text (overrides script)
        material_ids_override: str - comma-separated material IDs
    """
    conn = _db()
    task = conn.execute('SELECT * FROM video_task WHERE id=?', (id,)).fetchone()
    if not task:
        conn.close()
        return jsonify({'error': '任务不存在'}), 404

    script = conn.execute('SELECT * FROM script WHERE id=?', (task['script_id'],)).fetchone()
    conn.close()

    if not script:
        return jsonify({'error': '关联的文案不存在'}), 400

    task_dict = dict(task)
    script_dict = dict(script)

    data = request.get_json(silent=True) or {}
    narration_override = data.get('narration_override', '').strip()
    material_ids_override = data.get('material_ids_override', '').strip()

    # Build narration text
    if narration_override:
        narration = narration_override
    else:
        narration = _build_narration_for_task(task_dict, script_dict)

    if not narration.strip():
        return jsonify({'error': '文案内容为空，无法生成场景'}), 400

    # Get material info
    material_ids_str = material_ids_override or (task_dict.get('material_ids') or '')
    # 覆盖时写回任务，避免下次仍为空
    if material_ids_override:
        conn = _db()
        conn.execute(
            'UPDATE video_task SET material_ids=? WHERE id=?',
            (material_ids_override, id),
        )
        conn.commit()
        conn.close()
        task_dict['material_ids'] = material_ids_override

    materials_info = _get_material_info(material_ids_str)

    if not materials_info:
        why = _material_ids_diagnostic(material_ids_str)
        msg = {
            'empty': '请先选择场景素材（图片/视频），再生成场景',
            'invalid': '素材 ID 格式无效，请重新选择素材',
            'not_found': '任务上的素材已不存在，请重新选择场景素材',
            'only_bgm_or_cover': '当前选的是 BGM/封面，分镜需要「场景」图片或视频素材',
            'unknown': '无法加载场景素材，请重新选择图片或视频素材',
        }.get(why, '请先选择素材，再生成场景')
        return jsonify({'error': msg, 'reason': why}), 400

    try:
        from modules.ai_writer import generate_scenes, auto_match_materials
        scenes = generate_scenes(narration, materials_info)

        # Auto-match if AI didn't assign materials
        if scenes and all(s.get('material_index', -1) == -1 for s in scenes):
            scenes = auto_match_materials(scenes, materials_info)

        # Enrich scenes with material details for frontend
        mat_by_index = {m['index']: m for m in materials_info}
        for scene in scenes:
            mat_idx = scene.get('material_index', -1)
            if mat_idx >= 0 and mat_idx in mat_by_index:
                mat = mat_by_index[mat_idx]
                scene['material_id'] = mat['id']
                scene['material_name'] = mat['name']
                scene['material_type'] = mat['type']
                scene['material_path'] = mat['file_path']
            else:
                scene['material_id'] = None
                scene['material_name'] = ''
                scene['material_type'] = ''
                scene['material_path'] = ''

        # Save to database
        conn = _db()
        conn.execute('UPDATE video_task SET scenes_json=? WHERE id=?',
                     (json.dumps(scenes, ensure_ascii=False), id))
        conn.commit()
        conn.close()

        return jsonify({
            'message': f'已生成 {len(scenes)} 个场景',
            'scenes': scenes,
            'materials_info': [{'index': m['index'], 'id': m['id'], 'name': m['name'],
                                'type': m['type'], 'tags': m['tags']}
                               for m in materials_info],
        })
    except Exception as e:
        return jsonify({'error': f'场景生成失败: {str(e)}'}), 500


@bp.route('/api/videos/<int:id>/scenes', methods=['GET'])
def get_scenes_api(id):
    """Get saved scenes for a video task."""
    conn = _db()
    task = conn.execute('SELECT scenes_json, material_ids FROM video_task WHERE id=?', (id,)).fetchone()
    conn.close()
    if not task:
        return jsonify({'error': '任务不存在'}), 404

    scenes = []
    if task['scenes_json']:
        try:
            scenes = json.loads(task['scenes_json'])
        except json.JSONDecodeError:
            pass

    # Also return material info for the dropdown
    materials_info = _get_material_info(task['material_ids'] or '')

    return jsonify({
        'scenes': scenes,
        'materials_info': [{'index': m['index'], 'id': m['id'], 'name': m['name'],
                            'type': m['type'], 'tags': m['tags']}
                           for m in materials_info],
    })


@bp.route('/api/videos/<int:id>/scenes', methods=['PUT'])
def update_scenes_api(id):
    """Update scene-material mappings (manual editing).

    Body:
        scenes: list of scene dicts with updated material_index/material_id
    """
    data = request.get_json(silent=True) or {}
    scenes = data.get('scenes', [])

    if not isinstance(scenes, list):
        return jsonify({'error': 'scenes must be a list'}), 400

    # Enrich scenes with material details
    task_dict = None
    conn = _db()
    task = conn.execute('SELECT material_ids FROM video_task WHERE id=?', (id,)).fetchone()
    if task:
        task_dict = dict(task)
    conn.close()

    if task_dict:
        materials_info = _get_material_info(task_dict['material_ids'] or '')
        mat_by_index = {m['index']: m for m in materials_info}
        mat_by_id = {m['id']: m for m in materials_info}

        for scene in scenes:
            # Support both material_index and material_id for updates
            mat_id = scene.get('material_id')
            mat_idx = scene.get('material_index', -1)

            if mat_id is not None and mat_id in mat_by_id:
                mat = mat_by_id[mat_id]
                scene['material_index'] = mat['index']
                scene['material_name'] = mat['name']
                scene['material_type'] = mat['type']
                scene['material_path'] = mat['file_path']
            elif mat_idx >= 0 and mat_idx in mat_by_index:
                mat = mat_by_index[mat_idx]
                scene['material_id'] = mat['id']
                scene['material_name'] = mat['name']
                scene['material_type'] = mat['type']
                scene['material_path'] = mat['file_path']
            else:
                scene['material_id'] = None
                scene['material_name'] = ''
                scene['material_type'] = ''
                scene['material_path'] = ''

    # Save to database
    conn = _db()
    conn.execute('UPDATE video_task SET scenes_json=? WHERE id=?',
                 (json.dumps(scenes, ensure_ascii=False), id))
    conn.commit()
    conn.close()

    return jsonify({'message': '场景已更新', 'scenes': scenes})


@bp.route('/api/videos/<int:id>/status')
def video_status(id):
    """Lightweight status check for polling (used by frontend during background tasks)."""
    conn = _db()
    task = conn.execute(
        '''SELECT voice_status, subtitle_status, video_status, export_status,
           error_msg, duration, output_path, compose_started_at, compose_elapsed_sec
           FROM video_task WHERE id=?''',
        (id,)
    ).fetchone()
    if not task:
        conn.close()
        return jsonify({'error': 'not found'}), 404

    is_running = id in _running_tasks and _running_tasks[id].is_alive()
    elapsed = task['compose_elapsed_sec']
    processing = (
        task['video_status'] == 'processing'
        or task['export_status'] == 'processing'
        or (task['voice_status'] == 'processing' and is_running)
    )
    if processing:
        live = _compose_elapsed_sec(conn, id)
        if live is not None:
            elapsed = live
    conn.close()
    return jsonify({
        'voice_status': task['voice_status'],
        'subtitle_status': task['subtitle_status'],
        'video_status': task['video_status'],
        'export_status': task['export_status'],
        'error_msg': task['error_msg'],
        'duration': task['duration'],
        'compose_started_at': task['compose_started_at'],
        'compose_elapsed_sec': elapsed,
        'has_output': bool(task['output_path']),
        'is_running': is_running,
    })


@bp.route('/api/videos/<int:id>/download')
def download_video(id):
    """Download or preview the generated video file."""
    conn = _db()
    task = conn.execute('SELECT * FROM video_task WHERE id=?', (id,)).fetchone()
    conn.close()
    if not task:
        return jsonify({'error': 'not found'}), 404

    video_path = task['output_path'] or task['video_path']
    if not video_path or not os.path.exists(video_path):
        return jsonify({'error': '视频文件不存在'}), 404

    return send_file(
        os.path.abspath(video_path),
        as_attachment=False,
        mimetype='video/mp4'
    )
