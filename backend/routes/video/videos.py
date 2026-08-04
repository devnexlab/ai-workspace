"""Videos routes - real video production pipeline."""

import os
import json
import threading
from flask import Blueprint, request, jsonify, send_file
from config import OUTPUT_DIR as _OUTPUT_DIR, get_db as _db
from modules import video_maker

bp = Blueprint('videos', __name__)

OUTPUT_DIR = str(_OUTPUT_DIR)

# Track running background tasks: {task_id: thread}
_running_tasks = {}


def _get_material_paths(material_ids_str):
    """Look up material file paths from comma-separated IDs.
    Returns (image_paths, video_paths) lists.
    """
    if not material_ids_str:
        return [], []
    try:
        ids = [int(x.strip()) for x in material_ids_str.split(',') if x.strip()]
    except ValueError:
        return [], []

    if not ids:
        return [], []

    conn = _db()
    placeholders = ','.join('?' * len(ids))
    rows = conn.execute(
        f'SELECT * FROM video_material WHERE id IN ({placeholders})', ids
    ).fetchall()
    conn.close()

    image_paths = []
    video_paths = []
    for row in rows:
        path = row['file_path']
        if path and os.path.exists(path):
            if row['type'] == 'video':
                video_paths.append(path)
            else:
                image_paths.append(path)

    return image_paths, video_paths


def _get_material_paths_dict(material_ids_str):
    """Return material paths as dict {images: [...], videos: [...]}."""
    images, videos = _get_material_paths(material_ids_str)
    return {'images': images, 'videos': videos}


def _get_material_info(material_ids_str):
    """Return material info list for scene matching: [{index, name, type, tags, file_path}].

    The index field corresponds to the order in material_ids_str,
    matching the material_index field in generated scenes.
    """
    if not material_ids_str:
        return []
    try:
        ids = [int(x.strip()) for x in material_ids_str.split(',') if x.strip()]
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

    # Preserve original order from material_ids_str
    row_map = {row['id']: row for row in rows}
    info_list = []
    for idx, mid in enumerate(ids):
        row = row_map.get(mid)
        if row and row['file_path'] and os.path.exists(row['file_path']):
            info_list.append({
                'index': idx,
                'id': row['id'],
                'name': row['name'],
                'type': row['type'],
                'tags': row['tags'] or '',
                'file_path': row['file_path'],
            })

    return info_list


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
    conn.close()

    return jsonify({
        'list': [dict(r) for r in rows],
        'page': page,
        'pageSize': pageSize,
        'total': total,
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
    conn = _db()
    cur = conn.execute(
        '''INSERT INTO video_task (script_id,title,video_style,material_ids,
           resolution,fps,render_quality,fade_transition,title_overlay,video_engine,
           narration_prompt,voice,voice_rate,
           voice_status,subtitle_status,video_status,export_status)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (data.get('script_id'), data.get('title', ''),
         data.get('video_style', 'default'), data.get('material_ids', ''),
         data.get('resolution', '1080x1920'), data.get('fps', '30'),
         data.get('render_quality', 'high'), data.get('fade_transition', 'true'),
         data.get('title_overlay', 'true'), data.get('video_engine', 'moviepy'),
         data.get('narration_prompt', ''), data.get('voice', ''), data.get('voice_rate', ''),
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
            conn.execute(
                'UPDATE video_task SET video_status=?, error_msg=? WHERE id=?',
                ('processing', '', id)
            )
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
            conn.execute(
                'UPDATE video_task SET voice_status=?, voice_url=?, duration=? WHERE id=?',
                ('done', audio_path, result['duration'], id)
            )
            conn.commit()
            conn.close()
            return jsonify({'message': '配音完成', 'result': result})

        elif step == 'subtitle':
            # Try to load narration text saved from the voice step (may be AI-rewritten)
            narration = ''
            narration_path = os.path.join(task_output_dir, 'narration.txt')
            if os.path.exists(narration_path):
                try:
                    with open(narration_path, 'r', encoding='utf-8') as f:
                        narration = f.read()
                except Exception:
                    pass

            # Fallback: build narration from original script
            if not narration.strip():
                if script_dict.get('hook'):
                    narration += script_dict['hook'] + '\n'
                narration += script_dict.get('content', '')
                if script_dict.get('ending'):
                    narration += '\n' + script_dict['ending']

            duration = task_dict.get('duration', 0) or 30

            # Try to load word boundaries saved from the voice step
            import json as _json
            word_boundaries = None
            boundaries_path = os.path.join(task_output_dir, f'word_boundaries.json')
            if os.path.exists(boundaries_path):
                try:
                    with open(boundaries_path, 'r', encoding='utf-8') as f:
                        word_boundaries = _json.load(f)
                except Exception:
                    pass

            sub_path = os.path.join(task_output_dir, f'subtitle.srt')
            result = video_maker.generate_subtitle(narration, duration, sub_path, word_boundaries)

            conn = _db()
            conn.execute(
                'UPDATE video_task SET subtitle_status=?, subtitle_url=? WHERE id=?',
                ('done', result['subtitle_path'], id)
            )
            conn.commit()
            conn.close()
            sync_note = ' (TTS同步)' if word_boundaries else ' (均匀分配)'
            return jsonify({'message': f'字幕生成完成{sync_note}', 'result': result})

        else:
            return jsonify({'error': f'未知步骤: {step}'}), 400

    except Exception as e:
        conn = _db()
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
            # Compose video with styled subtitles and visual effects
            audio_path = task_dict.get('voice_url', '')
            sub_path = task_dict.get('subtitle_url', '')

            if not audio_path or not sub_path:
                conn = _db()
                conn.execute('UPDATE video_task SET video_status=?, error_msg=? WHERE id=?',
                             ('failed', '请先完成配音和字幕步骤', task_id))
                conn.commit()
                conn.close()
                return

            # Get materials from material_ids
            material_ids_str = task_dict.get('material_ids', '')
            image_paths, video_paths = _get_material_paths(material_ids_str)

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
            }

            result = video_maker.compose_video(
                audio_path, sub_path, image_paths, video_path,
                title_text=title_text,
                video_style=video_style,
                video_paths=video_paths if video_paths else None,
                task_params=task_params,
            )

            conn = _db()
            conn.execute(
                'UPDATE video_task SET video_status=?, video_path=?, export_status=?, output_path=? WHERE id=?',
                ('done', result['video_path'], 'done', result['video_path'], task_id)
            )
            conn.commit()
            conn.close()
            print(f'[BackgroundTask] Compose done for task {task_id}')

        elif step == 'all':
            # Run full pipeline
            material_ids_str = task_dict.get('material_ids', '')
            material_paths = _get_material_paths_dict(material_ids_str)
            materials_info = _get_material_info(material_ids_str)
            video_style = task_dict.get('video_style', 'default')

            # Load pre-generated scenes if available
            pre_scenes = None
            scenes_json_str = task_dict.get('scenes_json', '')
            if scenes_json_str:
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
            }

            result = video_maker.produce_video(
                script_dict, task_id, task_output_dir,
                video_style=video_style,
                material_paths=material_paths,
                task_params=task_params,
                materials_info=materials_info if not pre_scenes else None,
                pre_scenes=pre_scenes,
            )

            conn = _db()
            conn.execute(
                '''UPDATE video_task SET voice_status=?, voice_url=?, subtitle_status=?,
                   subtitle_url=?, video_status=?, video_path=?, export_status=?,
                   output_path=?, duration=?, error_msg=? WHERE id=?''',
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
                 task_id)
            )
            # Save updated scenes (with timings) if available
            if result.get('scenes'):
                conn.execute('UPDATE video_task SET scenes_json=? WHERE id=?',
                             (json.dumps(result['scenes'], ensure_ascii=False), task_id))
            conn.commit()
            conn.close()
            print(f'[BackgroundTask] Full pipeline done for task {task_id}')

    except Exception as e:
        import traceback
        traceback.print_exc()
        conn = _db()
        conn.execute(
            'UPDATE video_task SET video_status=?, export_status=?, error_msg=? WHERE id=?',
            ('failed', 'failed', str(e), task_id)
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
              'voice_url', 'subtitle_url', 'video_path', 'output_path', 'error_msg']:
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
    from modules.video_maker import VOICE_OPTIONS
    from modules.ai_writer import NARRATION_PRESETS
    return jsonify({
        'voices': [{'value': k, 'label': v} for k, v in VOICE_OPTIONS.items()],
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
    material_ids_str = material_ids_override or task_dict.get('material_ids', '')
    materials_info = _get_material_info(material_ids_str)

    if not materials_info:
        return jsonify({'error': '请先选择素材，再生成场景'}), 400

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
           error_msg, duration, output_path FROM video_task WHERE id=?''',
        (id,)
    ).fetchone()
    conn.close()
    if not task:
        return jsonify({'error': 'not found'}), 404

    is_running = id in _running_tasks and _running_tasks[id].is_alive()
    return jsonify({
        'voice_status': task['voice_status'],
        'subtitle_status': task['subtitle_status'],
        'video_status': task['video_status'],
        'export_status': task['export_status'],
        'error_msg': task['error_msg'],
        'duration': task['duration'],
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
