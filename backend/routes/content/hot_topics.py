"""
内容情报 API：全网实时热点 + 分龄口播平台采集 + 互动率排序。
"""

from flask import Blueprint, request, jsonify
from config import get_db as _db, get_ai_config
from modules.content_ops import (
    list_platforms, list_age_bands, platform_status,
    run_full_intelligence, fetch_all_hotspots, collect_platform_koubo,
)

bp = Blueprint('hot_topics', __name__)


def _insert_items(items):
    """写入 hot_topic，返回插入数。"""
    if not items:
        return 0
    conn = _db()
    inserted = 0
    for item in items:
        try:
            # AI 轻量评分：有互动分则映射，否则 50
            ai_score = item.get('ai_score')
            if ai_score is None:
                ai_score = min(99, (item.get('engagement_rate') or 0) * 0.9 + 10)

            conn.execute(
                '''INSERT INTO hot_topic
                   (platform, title, author, publish_time, likes, comments, favorites, shares,
                    url, cover, ai_score, analysis, status, keyword,
                    age_band, source_type, content_kind, engagement_rate, engagement_score)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (
                    item.get('platform', ''),
                    item.get('title', ''),
                    item.get('author', ''),
                    item.get('publish_time', ''),
                    int(item.get('likes') or 0),
                    int(item.get('comments') or 0),
                    int(item.get('favorites') or 0),
                    int(item.get('shares') or 0),
                    item.get('url', ''),
                    item.get('cover', ''),
                    float(ai_score or 0),
                    item.get('analysis', ''),
                    'collected',
                    item.get('keyword', ''),
                    item.get('age_band', 'all'),
                    item.get('source_type', 'platform'),
                    item.get('content_kind', 'koubo'),
                    float(item.get('engagement_rate') or 0),
                    float(item.get('engagement_score') or 0),
                )
            )
            inserted += 1
        except Exception as e:
            print(f'[ContentOps] insert fail: {e}')
    conn.commit()
    conn.close()
    return inserted


@bp.route('/api/content-ops/meta')
def content_ops_meta():
    """平台 / 年龄段 / 就绪状态 — 供前端动态渲染，加平台不用改前端写死。"""
    return jsonify({
        'platforms': platform_status(),
        'age_bands': list_age_bands(),
        'source_types': [
            {'key': 'hotspot', 'label': '全网实时热点'},
            {'key': 'platform', 'label': '平台口播素材'},
        ],
        'content_kinds': [
            {'key': 'hotspot', 'label': '热点选题'},
            {'key': 'koubo', 'label': '口播素材'},
        ],
    })


@bp.route('/api/hot-topics')
def list_topics():
    conn = _db()
    page = int(request.args.get('page', 1))
    pageSize = int(request.args.get('pageSize', 20))
    platform = request.args.get('platform', '')
    status = request.args.get('status', '')
    age_band = request.args.get('age_band', '')
    source_type = request.args.get('source_type', '')
    content_kind = request.args.get('content_kind', '')
    q = request.args.get('q', '')
    sort = request.args.get('sort', 'engagement')  # engagement | score | time

    where = []
    params = []
    if platform:
        where.append('platform=?')
        params.append(platform)
    if status:
        where.append('status=?')
        params.append(status)
    if age_band:
        where.append('age_band=?')
        params.append(age_band)
    if source_type:
        where.append('source_type=?')
        params.append(source_type)
    if content_kind:
        where.append('content_kind=?')
        params.append(content_kind)
    if q:
        where.append('(title LIKE ? OR author LIKE ? OR keyword LIKE ?)')
        params.extend([f'%{q}%', f'%{q}%', f'%{q}%'])

    where_clause = ('WHERE ' + ' AND '.join(where)) if where else ''
    order = {
        'engagement': 'engagement_score DESC NULLS LAST, likes DESC, created_at DESC',
        'score': 'ai_score DESC NULLS LAST, engagement_score DESC, created_at DESC',
        'time': 'created_at DESC',
    }.get(sort, 'engagement_score DESC NULLS LAST, created_at DESC')

    offset = (page - 1) * pageSize
    total = conn.execute(
        f'SELECT COUNT(*) as c FROM hot_topic {where_clause}', params
    ).fetchone()['c']
    rows = conn.execute(
        f'SELECT * FROM hot_topic {where_clause} ORDER BY {order} LIMIT ? OFFSET ?',
        params + [pageSize, offset]
    ).fetchall()

    # 统计
    stats = {}
    for r in conn.execute(
        'SELECT source_type, COUNT(*) as c FROM hot_topic GROUP BY source_type'
    ).fetchall():
        stats[r['source_type'] or 'unknown'] = r['c']
    age_stats = {}
    for r in conn.execute(
        'SELECT age_band, COUNT(*) as c FROM hot_topic GROUP BY age_band'
    ).fetchall():
        age_stats[r['age_band'] or 'all'] = r['c']
    conn.close()

    return jsonify({
        'list': [dict(r) for r in rows],
        'page': page,
        'pageSize': pageSize,
        'total': total,
        'stats': stats,
        'ageStats': age_stats,
    })


@bp.route('/api/hot-topics/<int:id>')
def get_topic(id):
    conn = _db()
    row = conn.execute('SELECT * FROM hot_topic WHERE id=?', (id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'not found'}), 404
    return jsonify(dict(row))


@bp.route('/api/hot-topics', methods=['POST'])
def create_topic():
    data = request.get_json(silent=True) or {}
    n = _insert_items([{
        **data,
        'source_type': data.get('source_type', 'manual'),
        'content_kind': data.get('content_kind', 'koubo'),
        'age_band': data.get('age_band', 'all'),
    }])
    return jsonify({'message': '已创建', 'inserted': n})


@bp.route('/api/content-ops/refresh', methods=['POST'])
def refresh_intelligence():
    """
    一键刷新内容情报：
      mode=full|hotspots|platforms
    """
    data = request.get_json(silent=True) or {}
    mode = data.get('mode', 'full')
    platforms = data.get('platforms')
    age_bands = data.get('age_bands')
    count = int(data.get('count', 5))
    max_keywords = int(data.get('max_keywords', 8))

    try:
        if mode == 'hotspots':
            items, message = fetch_all_hotspots(use_ai_fallback=True)
            from modules.content_ops.pipeline import enrich_and_rank
            items = enrich_and_rank(items)
        elif mode == 'platforms':
            items, message = collect_platform_koubo(
                platforms=platforms,
                age_bands=age_bands,
                count_per_keyword=count,
                max_keywords=max_keywords,
            )
        else:
            items, message = run_full_intelligence(
                platforms=platforms,
                age_bands=age_bands,
                include_hotspots=True,
                count_per_keyword=count,
                max_keywords=max_keywords,
            )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'collected': 0, 'message': f'刷新失败: {e}'}), 500

    inserted = _insert_items(items)
    return jsonify({
        'collected': inserted,
        'total_fetched': len(items),
        'message': message or f'已入库 {inserted} 条',
        'top': [
            {
                'title': x.get('title'),
                'platform': x.get('platform'),
                'age_band': x.get('age_band'),
                'engagement_score': x.get('engagement_score'),
                'source_type': x.get('source_type'),
            }
            for x in items[:8]
        ],
    })


# 兼容旧前端按钮
@bp.route('/api/hot-topics/collect', methods=['POST'])
def collect_compat():
    data = request.get_json(silent=True) or {}
    if data.get('keywords'):
        from modules.collector import collect_all
        from modules.content_ops.pipeline import enrich_and_rank
        from modules.content_ops.age_bands import guess_age_band
        try:
            items, message = collect_all(
                keywords=data.get('keywords'),
                platforms=data.get('platforms'),
                count_per_keyword=int(data.get('count', 10)),
            )
        except Exception as e:
            return jsonify({'collected': 0, 'message': str(e)}), 500
        for it in items:
            it['source_type'] = 'platform'
            it['content_kind'] = 'koubo'
            it['age_band'] = guess_age_band(it.get('title', ''), it.get('keyword', ''))
        items = enrich_and_rank(items)
        inserted = _insert_items(items)
        return jsonify({'collected': inserted, 'message': message})

    try:
        items, message = run_full_intelligence(
            platforms=data.get('platforms'),
            age_bands=data.get('age_bands'),
            include_hotspots=True,
            count_per_keyword=int(data.get('count', 5)),
            max_keywords=int(data.get('max_keywords', 8)),
        )
    except Exception as e:
        return jsonify({'collected': 0, 'message': str(e)}), 500
    inserted = _insert_items(items)
    return jsonify({'collected': inserted, 'message': message, 'total_fetched': len(items)})


@bp.route('/api/hot-topics/<int:id>/generate-script', methods=['POST'])
def generate_script(id):
    from modules.ai_writer import generate_script as gen_script

    conn = _db()
    topic = conn.execute('SELECT * FROM hot_topic WHERE id=?', (id,)).fetchone()
    conn.close()
    if not topic:
        return jsonify({'error': '不存在'}), 404

    topic_dict = dict(topic)
    data = request.get_json(silent=True) or {}
    ai_config = get_ai_config()
    content_type = data.get('content_type')
    if not content_type:
        # 热点→可做保险或泛流量；口播素材默认泛流量
        content_type = 'insurance' if topic_dict.get('keyword') == 'insurance' else 'traffic'
    age_band = data.get('age_band') or topic_dict.get('age_band') or 'all'

    try:
        script = gen_script(
            topic_dict,
            style=data.get('style', '高转发共鸣'),
            duration=data.get('duration', '40-60秒'),
            audience=data.get('audience') or ai_config.get('default_audience', ''),
            tone=data.get('tone') or ai_config.get('default_tone', 'casual'),
            content_type=content_type,
            age_band=age_band,
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    try:
        conn = _db()
        tags = str(script.get('tags', '') or '')
        type_tag = '泛流量' if content_type == 'traffic' else '保险干货'
        if type_tag not in tags:
            tags = f'{type_tag},{tags}' if tags else type_tag
        cur = conn.execute(
            '''INSERT INTO script (topic_id,title,hook,content,ending,cover_text,
               tags,version,status,model_name,tokens_used,content_type,age_band)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (id, script['title'], script['hook'], script['content'],
             script['ending'], script['cover_text'], tags,
             1, 'draft', script.get('model_name', ''), script.get('tokens_used', 0),
             content_type, age_band)
        )
        conn.commit()
        sid = cur.lastrowid
        conn.close()
        return jsonify({'id': sid, 'message': '文案已生成（含品牌收口）', 'script': script})
    except Exception as e:
        return jsonify({'error': f'保存失败: {e}'}), 500


@bp.route('/api/hot-topics/batch-generate', methods=['POST'])
def batch_generate_scripts():
    from modules.ai_writer import generate_script as gen_script
    data = request.get_json(silent=True) or {}
    limit = int(data.get('limit', 5))
    content_type = data.get('content_type', 'traffic')
    ai_config = get_ai_config()

    conn = _db()
    rows = conn.execute(
        '''SELECT * FROM hot_topic WHERE status != 'ignored'
           ORDER BY engagement_score DESC NULLS LAST, ai_score DESC NULLS LAST
           LIMIT ?''',
        (limit,)
    ).fetchall()
    conn.close()

    created, errors = [], []
    for row in rows:
        topic = dict(row)
        try:
            script = gen_script(
                topic, style='高转发共鸣', duration='40-60秒',
                audience=ai_config.get('default_audience', ''),
                tone=ai_config.get('default_tone', 'casual'),
                content_type=content_type,
                age_band=topic.get('age_band') or 'all',
            )
            conn = _db()
            tags = str(script.get('tags', '') or '')
            type_tag = '泛流量' if content_type == 'traffic' else '保险干货'
            if type_tag not in tags:
                tags = f'{type_tag},{tags}' if tags else type_tag
            cur = conn.execute(
                '''INSERT INTO script (topic_id,title,hook,content,ending,cover_text,
                   tags,version,status,model_name,tokens_used,content_type,age_band)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (topic['id'], script['title'], script['hook'], script['content'],
                 script['ending'], script['cover_text'], tags,
                 1, 'draft', script.get('model_name', ''), script.get('tokens_used', 0),
                 content_type, topic.get('age_band') or 'all')
            )
            conn.commit()
            created.append({'id': cur.lastrowid, 'title': script['title'], 'topic_id': topic['id']})
            conn.close()
        except Exception as e:
            errors.append({'topic_id': topic['id'], 'error': str(e)})

    return jsonify({
        'message': f'批量完成 {len(created)}/{len(rows)}',
        'created': created,
        'errors': errors,
    })


@bp.route('/api/hot-topics/<int:id>', methods=['PUT'])
def update_topic(id):
    data = request.get_json(silent=True) or {}
    conn = _db()
    fields, params = [], []
    for k in ['platform', 'title', 'author', 'status', 'ai_score', 'analysis', 'keyword',
              'age_band', 'source_type', 'content_kind']:
        if k in data:
            fields.append(f'{k}=?')
            params.append(data[k])
    if fields:
        params.append(id)
        conn.execute(f'UPDATE hot_topic SET {",".join(fields)} WHERE id=?', params)
        conn.commit()
    conn.close()
    return jsonify({'message': '已更新'})


@bp.route('/api/hot-topics/<int:id>', methods=['DELETE'])
def delete_topic(id):
    conn = _db()
    conn.execute('DELETE FROM hot_topic WHERE id=?', (id,))
    conn.commit()
    conn.close()
    return jsonify({'message': '已删除'})
