"""Scripts routes - AI 文案生成 + 每日 2 泛流量 + 1 保险计划。"""

from flask import Blueprint, request, jsonify
from config import get_db as _db, get_ai_config, get_setting
from datetime import date

bp = Blueprint('scripts', __name__)

AGE_ROTATION = ['20s', '30s', '40s', '50s', '60s', '70s', '80s']


@bp.route('/api/scripts')
def list_scripts():
    conn = _db()
    page = int(request.args.get('page', 1))
    pageSize = int(request.args.get('pageSize', 20))
    status = request.args.get('status', '')
    topic_id = request.args.get('topic_id', '')
    content_type = request.args.get('content_type', '')
    q = request.args.get('q', '')

    where = []
    params = []
    if status:
        where.append('s.status=?')
        params.append(status)
    if topic_id:
        where.append('s.topic_id=?')
        params.append(int(topic_id))
    if content_type:
        where.append('s.content_type=?')
        params.append(content_type)
    if q:
        where.append('(s.title LIKE ? OR s.content LIKE ?)')
        params.extend([f'%{q}%', f'%{q}%'])

    where_clause = ('WHERE ' + ' AND '.join(where)) if where else ''
    offset = (page - 1) * pageSize

    total = conn.execute(
        f'SELECT COUNT(*) as c FROM script s {where_clause}', params
    ).fetchone()['c']

    rows = conn.execute(
        f'''SELECT s.*, t.title as topic_title, t.platform as topic_platform
            FROM script s LEFT JOIN hot_topic t ON s.topic_id=t.id
            {where_clause} ORDER BY s.created_at DESC LIMIT ? OFFSET ?''',
        params + [pageSize, offset]
    ).fetchall()
    conn.close()

    return jsonify({
        'list': [dict(r) for r in rows],
        'page': page,
        'pageSize': pageSize,
        'total': total,
    })


@bp.route('/api/scripts/<int:id>')
def get_script(id):
    conn = _db()
    row = conn.execute(
        '''SELECT s.*, t.title as topic_title, t.platform as topic_platform
           FROM script s LEFT JOIN hot_topic t ON s.topic_id=t.id WHERE s.id=?''',
        (id,)
    ).fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'not found'}), 404
    return jsonify(dict(row))


def _save_script(conn, script, topic_id=None, content_type='traffic', age_band='all'):
    tags = str(script.get('tags', '') or '')
    # 打上类型标签方便筛选
    type_tag = '泛流量' if content_type == 'traffic' else '保险干货'
    if type_tag not in tags:
        tags = f'{type_tag},{tags}' if tags else type_tag

    cur = conn.execute(
        '''INSERT INTO script (topic_id,title,hook,content,ending,cover_text,
           tags,version,status,model_name,tokens_used,content_type,age_band)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (topic_id, str(script['title']), str(script['hook']),
         str(script['content']), str(script['ending']), str(script['cover_text']),
         tags, 1, 'draft', str(script.get('model_name', '')),
         int(script.get('tokens_used', 0) or 0), content_type, age_band)
    )
    return cur.lastrowid


@bp.route('/api/scripts/generate', methods=['POST'])
def generate():
    """Generate a script using AI. Can be from a topic ID or custom prompt."""
    from modules.ai_writer import (
        generate_script as gen_script, call_llm, build_script_prompt,
        parse_script_response, apply_brand_ending, SYSTEM_PROMPT,
    )

    data = request.get_json(silent=True) or {}
    ai_config = get_ai_config()
    default_audience = ai_config.get('default_audience', '')
    default_tone = ai_config.get('default_tone', 'casual')

    style = data.get('style', '干货分享')
    duration = data.get('duration', '40-60秒')
    audience = data.get('audience', '') or default_audience
    tone = data.get('tone', '') or default_tone
    extra_req = data.get('extra_req', '')
    content_type = data.get('content_type', 'traffic')
    age_band = data.get('age_band', 'all')

    topic_dict = None
    if data.get('topic_id'):
        conn = _db()
        topic = conn.execute('SELECT * FROM hot_topic WHERE id=?', (data['topic_id'],)).fetchone()
        conn.close()
        if not topic:
            return jsonify({'error': '热点不存在'}), 404
        topic_dict = dict(topic)
    else:
        prompt_text = data.get('prompt', '')
        if not prompt_text:
            return jsonify({'error': '请提供 topic_id 或 prompt'}), 400

    try:
        if topic_dict:
            script = gen_script(
                topic_dict, style=style, duration=duration,
                audience=audience, tone=tone, extra_req=extra_req,
                content_type=content_type, age_band=age_band,
            )
        else:
            full_prompt = build_script_prompt(
                prompt_text, style=style, duration=duration,
                audience=audience, tone=tone, extra_req=extra_req,
                content_type=content_type, age_band=age_band,
            )
            result, tokens, model = call_llm(full_prompt, system_prompt=SYSTEM_PROMPT)
            script = parse_script_response(result)
            apply_brand_ending(script)
            script['tokens_used'] = tokens
            script['model_name'] = model
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    try:
        conn = _db()
        script_id = _save_script(conn, script, data.get('topic_id'), content_type, age_band)
        conn.commit()
        conn.close()
        return jsonify({
            'id': script_id,
            'message': '文案生成成功（已套用品牌收口）',
            'script': script,
        })
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return jsonify({'error': f'文案已生成但保存失败: {str(e)}'}), 500


@bp.route('/api/scripts/daily-plan', methods=['POST'])
def daily_plan():
    """
    一键生成今日内容计划：
      - N 条泛流量（默认 2，分龄轮换，基于热点）
      - M 条保险干货（默认 1）
    全部强制品牌收口。
    """
    from modules.content_ops.daily_runner import generate_daily_scripts

    data = request.get_json(silent=True) or {}
    traffic_n = data.get('traffic_count')
    insurance_n = data.get('insurance_count')
    result = generate_daily_scripts(
        traffic_count=int(traffic_n) if traffic_n is not None else None,
        insurance_count=int(insurance_n) if insurance_n is not None else None,
    )
    return jsonify(result)


@bp.route('/api/scripts/daily-run', methods=['POST'])
def daily_run():
    """
    日更编排器：采热点 → 2+1 文案 → 自动建视频并出片。
    body:
      refresh: bool=true
      include_platforms: bool=false  # true 时顺带采抖音/小红书（较慢）
      produce_video: bool=true
      traffic_count / insurance_count: optional
    """
    from modules.content_ops.daily_runner import run_daily_pipeline

    data = request.get_json(silent=True) or {}
    try:
        result = run_daily_pipeline(
            refresh=bool(data.get('refresh', True)),
            include_platforms=bool(data.get('include_platforms', False)),
            produce_video=bool(data.get('produce_video', True)),
            traffic_count=data.get('traffic_count'),
            insurance_count=data.get('insurance_count'),
        )
        return jsonify(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'ok': False, 'error': str(e), 'message': f'日更失败: {e}'}), 500


@bp.route('/api/scripts/daily-run/status')
def daily_run_status():
    """今日日更进度快照。"""
    today = date.today().isoformat()
    conn = _db()
    scripts = conn.execute(
        '''SELECT content_type, COUNT(*) as c FROM script
           WHERE created_at::date = %s::date GROUP BY content_type''',
        (today,)
    ).fetchall()
    videos = conn.execute(
        '''SELECT v.export_status, COUNT(*) as c FROM video_task v
           JOIN script s ON v.script_id = s.id
           WHERE s.created_at::date = %s::date
           GROUP BY v.export_status''',
        (today,)
    ).fetchall()
    conn.close()
    return jsonify({
        'date': today,
        'scripts': {r['content_type']: r['c'] for r in scripts},
        'videos': {r['export_status']: r['c'] for r in videos},
        'daily_auto_enabled': get_setting('system', 'daily_auto_enabled', 'false'),
        'daily_run_hour': get_setting('system', 'daily_run_hour', '8'),
        'daily_last_run': get_setting('system', 'daily_last_run', ''),
        'daily_last_run_date': get_setting('system', 'daily_last_run_date', ''),
        'traffic_target': get_setting('system', 'daily_traffic_count', '2'),
        'insurance_target': get_setting('system', 'daily_insurance_count', '1'),
    })


@bp.route('/api/scripts/<int:id>', methods=['PUT'])
def update_script(id):
    data = request.get_json(silent=True) or {}
    conn = _db()
    fields = []
    params = []
    for k in ['title', 'hook', 'content', 'ending', 'cover_text', 'tags', 'status',
              'version', 'content_type', 'age_band']:
        if k in data:
            fields.append(f'{k}=?')
            params.append(data[k])
    if fields:
        params.append(id)
        conn.execute(f'UPDATE script SET {",".join(fields)} WHERE id=?', params)
        conn.commit()
    conn.close()
    return jsonify({'message': '已更新'})


@bp.route('/api/scripts/<int:id>', methods=['DELETE'])
def delete_script(id):
    conn = _db()
    conn.execute('DELETE FROM script WHERE id=?', (id,))
    conn.commit()
    conn.close()
    return jsonify({'message': '已删除'})
