"""Scripts routes - AI 文案生成 + 每日 2 泛流量 + 1 保险计划。"""

from flask import Blueprint, request, jsonify
from config import get_db as _db, get_ai_config, get_setting
from datetime import date

bp = Blueprint('scripts', __name__)

AGE_ROTATION = ['20s', '30s', '40s', '50s', '60s', '70s']


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
    from modules.ai_writer import generate_script as gen_script, AGE_AUDIENCE

    data = request.get_json(silent=True) or {}
    traffic_n = int(data.get('traffic_count') or get_setting('system', 'daily_traffic_count', '2') or 2)
    insurance_n = int(data.get('insurance_count') or get_setting('system', 'daily_insurance_count', '1') or 1)

    conn = _db()
    # 今日已生成数量（按 content_type）
    today = date.today().isoformat()
    existing = conn.execute(
        '''SELECT content_type, COUNT(*) as c FROM script
           WHERE created_at::date = %s::date
           GROUP BY content_type''',
        (today,)
    ).fetchall()
    existing_map = {r['content_type']: r['c'] for r in existing}

    need_traffic = max(0, traffic_n - existing_map.get('traffic', 0))
    need_insurance = max(0, insurance_n - existing_map.get('insurance', 0))

    # 取高分热点
    topics = conn.execute(
        '''SELECT * FROM hot_topic
           WHERE status != 'ignored'
           ORDER BY ai_score DESC NULLS LAST, (likes+comments+shares) DESC, created_at DESC
           LIMIT 30'''
    ).fetchall()
    conn.close()
    topics = [dict(t) for t in topics]

    created = []
    errors = []
    used_topic_ids = set()

    # 分龄轮换：按星期选起点
    start_idx = date.today().toordinal() % len(AGE_ROTATION)

    def pick_topic(prefer_insurance=False):
        for t in topics:
            if t['id'] in used_topic_ids:
                continue
            title = (t.get('title') or '') + (t.get('keyword') or '') + (t.get('analysis') or '')
            has_ins = any(k in title for k in ('保险', '理赔', '保单', '重疾', '医保', '养老', '保障'))
            if prefer_insurance and not has_ins:
                continue
            if not prefer_insurance and has_ins and len(topics) > need_traffic + 2:
                # 泛流量优先非保险标题，不够时再放宽
                continue
            used_topic_ids.add(t['id'])
            return t
        # 放宽：任意未用热点
        for t in topics:
            if t['id'] not in used_topic_ids:
                used_topic_ids.add(t['id'])
                return t
        return None

    # 1) 泛流量
    for i in range(need_traffic):
        age_band = AGE_ROTATION[(start_idx + i) % len(AGE_ROTATION)]
        topic = pick_topic(prefer_insurance=False)
        try:
            if topic:
                script = gen_script(
                    topic, style='高转发共鸣', duration='40-60秒',
                    content_type='traffic', age_band=age_band,
                    tone='casual',
                    extra_req=f'面向{AGE_AUDIENCE.get(age_band, "")}，强共鸣可转发，不硬广',
                )
                topic_id = topic['id']
            else:
                # 无热点时用主题兜底
                prompt = f'结合今日社会热点，写一条面向{AGE_AUDIENCE.get(age_band)}的人生共鸣口播，不硬广保险'
                script = gen_script(
                    prompt, style='高转发共鸣', duration='40-60秒',
                    content_type='traffic', age_band=age_band, tone='casual',
                )
                topic_id = None
            conn = _db()
            sid = _save_script(conn, script, topic_id, 'traffic', age_band)
            conn.commit()
            conn.close()
            created.append({
                'id': sid, 'content_type': 'traffic', 'age_band': age_band,
                'title': script.get('title'), 'topic_id': topic_id,
            })
        except Exception as e:
            errors.append(f'泛流量#{i+1}: {e}')

    # 2) 保险干货
    for i in range(need_insurance):
        topic = pick_topic(prefer_insurance=True)
        try:
            if topic:
                script = gen_script(
                    topic, style='保险避坑干货', duration='40-60秒',
                    content_type='insurance', age_band='all',
                    tone='friendly',
                    extra_req='专业但不吓人，用案例建立信任，引导关注来找我',
                )
                topic_id = topic['id']
            else:
                script = gen_script(
                    '家庭保障常见误区与理赔避坑，面向全年龄段口播',
                    style='保险避坑干货', duration='40-60秒',
                    content_type='insurance', age_band='all', tone='friendly',
                )
                topic_id = None
            conn = _db()
            sid = _save_script(conn, script, topic_id, 'insurance', 'all')
            conn.commit()
            conn.close()
            created.append({
                'id': sid, 'content_type': 'insurance', 'age_band': 'all',
                'title': script.get('title'), 'topic_id': topic_id,
            })
        except Exception as e:
            errors.append(f'保险#{i+1}: {e}')

    ending = get_setting('system', 'fixed_ending', '')
    return jsonify({
        'message': f'今日计划完成：新生成 {len(created)} 条（目标泛流量{traffic_n}+保险{insurance_n}）',
        'created': created,
        'skipped': {
            'traffic_already': existing_map.get('traffic', 0),
            'insurance_already': existing_map.get('insurance', 0),
            'need_traffic': need_traffic,
            'need_insurance': need_insurance,
        },
        'brand_ending': ending,
        'errors': errors,
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
