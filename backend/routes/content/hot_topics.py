"""
内容情报 API：全网实时热点 + 分龄口播平台采集 + 互动率排序。
"""

from flask import Blueprint, request, jsonify
from config import get_db as _db, get_ai_config
from modules.content_ops import (
    list_platforms, list_age_bands, platform_status,
    run_full_intelligence, fetch_all_hotspots, collect_platform_koubo,
)
from modules.content_ops.commercial_data import (
    fetch_all_commercial, list_commercial_providers, test_provider,
)

bp = Blueprint('hot_topics', __name__)


def _normalize_title(title):
    """统一空白，便于判定「同一选题」。"""
    if not title:
        return ''
    return ' '.join(str(title).strip().split())


def _title_key(title):
    """去重键：规范化后取前 40 字（同选题跨平台也合并）。"""
    t = _normalize_title(title)
    return t[:40] if t else ''


def _dedupe_existing_topics(conn=None):
    """
    清理库内同标题重复行：同一选题只留一条。
    保留规则：互动分高 > 点赞高 > id 新。
    返回删除条数。
    """
    own = conn is None
    if own:
        conn = _db()
    rows = conn.execute(
        'SELECT id, title, engagement_score, likes FROM hot_topic'
    ).fetchall()
    best = {}  # title_key -> (score, likes, id)
    drop_ids = []
    for row in rows:
        key = _title_key(row['title'])
        if not key:
            continue
        score = float(row['engagement_score'] or 0)
        likes = int(row['likes'] or 0)
        rid = row['id']
        cur = best.get(key)
        if cur is None:
            best[key] = (score, likes, rid)
            continue
        # 当前行更好 → 丢掉旧的 best.id；否则丢掉当前行
        better = (score, likes, rid) > (cur[0], cur[1], cur[2])
        if better:
            drop_ids.append(cur[2])
            best[key] = (score, likes, rid)
        else:
            drop_ids.append(rid)

    for rid in drop_ids:
        conn.execute('DELETE FROM hot_topic WHERE id=?', (rid,))
    if own:
        conn.commit()
        conn.close()
    return len(drop_ids)


def _insert_items(items):
    """
    写入 hot_topic：同标题（规范化后前 40 字）则覆盖更新并刷新时间，否则新增。
    返回 (inserted, updated)。
    """
    if not items:
        return 0, 0
    conn = _db()
    # 同标题可能有多条历史重复：取 id 最大的一条作为覆盖目标
    existing = {}  # title_key -> id
    for r in conn.execute('SELECT id, title FROM hot_topic').fetchall():
        key = _title_key(r['title'])
        if not key:
            continue
        prev = existing.get(key)
        if prev is None or int(r['id']) > int(prev):
            existing[key] = r['id']

    inserted = 0
    updated = 0
    batch_seen = set()
    for item in items:
        try:
            key = _title_key(item.get('title', ''))
            if not key or key in batch_seen:
                continue
            batch_seen.add(key)

            ai_score = item.get('ai_score')
            if ai_score is None:
                ai_score = min(99, (item.get('engagement_rate') or 0) * 0.9 + 10)

            title = _normalize_title(item.get('title', ''))
            platform = item.get('platform', '')
            author = item.get('author', '')
            publish_time = item.get('publish_time', '')
            likes = int(item.get('likes') or 0)
            comments = int(item.get('comments') or 0)
            favorites = int(item.get('favorites') or 0)
            shares = int(item.get('shares') or 0)
            url = item.get('url', '')
            cover = item.get('cover', '')
            analysis = item.get('analysis', '')
            keyword = item.get('keyword', '')
            age_band = item.get('age_band', 'all')
            source_type = item.get('source_type', 'platform')
            content_kind = item.get('content_kind', 'koubo')
            engagement_rate = float(item.get('engagement_rate') or 0)
            engagement_score = float(item.get('engagement_score') or 0)
            score = float(ai_score or 0)

            rid = existing.get(key)
            if rid:
                conn.execute(
                    '''UPDATE hot_topic SET
                       platform=?, title=?, author=?, publish_time=?,
                       likes=?, comments=?, favorites=?, shares=?,
                       url=?, cover=?, ai_score=?, analysis=?,
                       status='collected', keyword=?,
                       age_band=?, source_type=?, content_kind=?,
                       engagement_rate=?, engagement_score=?,
                       created_at=CURRENT_TIMESTAMP
                       WHERE id=?''',
                    (
                        platform, title, author, publish_time,
                        likes, comments, favorites, shares,
                        url, cover, score, analysis,
                        keyword, age_band, source_type, content_kind,
                        engagement_rate, engagement_score, rid,
                    ),
                )
                updated += 1
            else:
                cur = conn.execute(
                    '''INSERT INTO hot_topic
                       (platform, title, author, publish_time, likes, comments, favorites, shares,
                        url, cover, ai_score, analysis, status, keyword,
                        age_band, source_type, content_kind, engagement_rate, engagement_score)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (
                        platform, title, author, publish_time,
                        likes, comments, favorites, shares,
                        url, cover, score, analysis, 'collected', keyword,
                        age_band, source_type, content_kind,
                        engagement_rate, engagement_score,
                    ),
                )
                inserted += 1
                new_id = getattr(cur, 'lastrowid', None)
                if new_id:
                    existing[key] = new_id
        except Exception as e:
            print(f'[ContentOps] upsert fail: {e}')
    conn.commit()
    conn.close()
    return inserted, updated


@bp.route('/api/content-ops/meta')
def content_ops_meta():
    """平台 / 年龄段 / 就绪状态 — 供前端动态渲染，加平台不用改前端写死。"""
    return jsonify({
        'platforms': platform_status(),
        'age_bands': list_age_bands(),
        'commercial_providers': list_commercial_providers(),
        'source_types': [
            {'key': 'hotspot', 'label': '全网实时热点'},
            {'key': 'platform', 'label': '平台口播素材'},
            {'key': 'commercial', 'label': '官方/商业数据台'},
        ],
        'content_kinds': [
            {'key': 'hotspot', 'label': '热点选题'},
            {'key': 'koubo', 'label': '口播素材'},
        ],
    })


@bp.route('/api/commercial-data/test/<provider_key>', methods=['POST'])
def commercial_test(provider_key):
    """试拉单个商业数据源（不入库）。"""
    result = test_provider(provider_key)
    status = 200 if result.get('ok') else 400
    return jsonify(result), status


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
    board = (request.args.get('board') or '').strip().lower()  # ride | viral
    sort = request.args.get('sort', 'time')  # time | engagement | likes | shares | score

    # 视频号板块预设：可蹭热点 / 爆款文案
    hint = ''
    if board == 'ride':
        source_type = source_type or 'hotspot'
        if sort == 'time':
            sort = 'engagement'
    elif board == 'viral':
        # 优先官方数据台；若库中无 commercial，回退热点并提示
        if not source_type:
            commercial_count = conn.execute(
                "SELECT COUNT(*) as c FROM hot_topic WHERE source_type='commercial'"
            ).fetchone()['c']
            if commercial_count and int(commercial_count) > 0:
                source_type = 'commercial'
            else:
                source_type = 'hotspot'
                hint = '暂无官方数据台数据，已回退全网热榜按互动排序；可到「设置·官方数据台」配置后拉取'
        if sort == 'time':
            sort = 'engagement'

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
        'engagement': 'engagement_score DESC NULLS LAST, likes DESC, shares DESC, created_at DESC',
        'likes': 'likes DESC NULLS LAST, engagement_score DESC, created_at DESC',
        'shares': 'shares DESC NULLS LAST, likes DESC, created_at DESC',
        'score': 'ai_score DESC NULLS LAST, engagement_score DESC, created_at DESC',
        'time': 'created_at DESC, id DESC',
    }.get(sort, 'created_at DESC, id DESC')

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
        'board': board or None,
        'sort': sort,
        'hint': hint,
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
    n_ins, n_upd = _insert_items([{
        **data,
        'source_type': data.get('source_type', 'manual'),
        'content_kind': data.get('content_kind', 'koubo'),
        'age_band': data.get('age_band', 'all'),
    }])
    return jsonify({'message': '已创建' if n_ins else '已更新', 'inserted': n_ins, 'updated': n_upd})


@bp.route('/api/content-ops/refresh', methods=['POST'])
def refresh_intelligence():
    """
    一键刷新内容情报：
      mode=full|hotspots|platforms|commercial
    """
    data = request.get_json(silent=True) or {}
    mode = data.get('mode', 'full')
    platforms = data.get('platforms')
    age_bands = data.get('age_bands')
    count = int(data.get('count', 5))
    max_keywords = int(data.get('max_keywords', 8))
    commercial_keys = data.get('commercial_providers') or data.get('providers')

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
        elif mode == 'commercial':
            items, message = fetch_all_commercial(provider_keys=commercial_keys)
            from modules.content_ops.pipeline import enrich_and_rank
            from modules.content_ops.age_bands import guess_age_band
            for it in items:
                it.setdefault('age_band', guess_age_band(it.get('title', ''), it.get('keyword', '')))
            items = enrich_and_rank(items)
        else:
            items, message = run_full_intelligence(
                platforms=platforms,
                age_bands=age_bands,
                include_hotspots=True,
                count_per_keyword=count,
                max_keywords=max_keywords,
            )
            # 全量时顺带拉已启用的商业数据台（未启用则跳过，不改提示）
            try:
                c_items, c_msg = fetch_all_commercial(provider_keys=commercial_keys)
                if c_items:
                    from modules.content_ops.pipeline import enrich_and_rank
                    from modules.content_ops.age_bands import guess_age_band
                    for it in c_items:
                        it.setdefault(
                            'age_band',
                            guess_age_band(it.get('title', ''), it.get('keyword', '')),
                        )
                    c_items = enrich_and_rank(c_items)
                    items = list(items or []) + c_items
                    message = f'{message}；{c_msg}'
            except Exception as ce:
                print(f'[commercial] skipped in full refresh: {ce}')
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'collected': 0, 'message': f'刷新失败: {e}'}), 500

    items = items or []
    inserted, updated = _insert_items(items)
    removed = _dedupe_existing_topics()
    base = message or '刷新完成'
    parts = [base, f'本次抓取 {len(items)}']
    if inserted:
        parts.append(f'新增 {inserted}')
    if updated:
        parts.append(f'覆盖更新 {updated}')
    if not items:
        parts.append('未抓到选题')
    elif not inserted and not updated:
        parts.append('无变更')
    msg = '；'.join(parts)
    if removed:
        msg += f'；已清理重复选题 {removed} 条'
    return jsonify({
        'collected': inserted + updated,
        'inserted': inserted,
        'updated': updated,
        'total_fetched': len(items),
        'deduped': removed,
        'message': msg,
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
        inserted, updated = _insert_items(items)
        removed = _dedupe_existing_topics()
        msg = message or f'新增 {inserted}，覆盖 {updated}'
        if removed:
            msg += f'；已清理重复选题 {removed} 条'
        return jsonify({
            'collected': inserted + updated,
            'inserted': inserted,
            'updated': updated,
            'deduped': removed,
            'message': msg,
        })

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
    inserted, updated = _insert_items(items)
    removed = _dedupe_existing_topics()
    msg = message or f'新增 {inserted}，覆盖 {updated}'
    if removed:
        msg += f'；已清理重复选题 {removed} 条'
    return jsonify({
        'collected': inserted + updated,
        'inserted': inserted,
        'updated': updated,
        'deduped': removed,
        'message': msg,
        'total_fetched': len(items),
    })


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
            duration=data.get('duration', '60秒'),
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
                topic, style='高转发共鸣', duration='60秒',
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
