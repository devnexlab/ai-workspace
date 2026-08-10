"""
桌宠问答向量索引：知识库 / 文案 / 股票简报 → rag_chunk。
检索：余弦相似度 + 关键词加分（混合召回）。
"""

from __future__ import annotations

import json
import re
from typing import Any

from config import get_db
from modules.pet.embeddings import cosine_similarity, embed_query, embed_texts

CHUNK_SIZE = 520
CHUNK_OVERLAP = 80
SOURCE_LABELS = {
    'knowledge': '知识库',
    'script': '文案',
    'stock_brief': '股票简报',
}


def _split_chunks(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    raw = (text or '').strip()
    if not raw:
        return []
    # 先按段落
    parts = re.split(r'\n{2,}', raw)
    chunks: list[str] = []
    buf = ''
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if len(buf) + len(part) + 1 <= size:
            buf = f'{buf}\n{part}'.strip() if buf else part
            continue
        if buf:
            chunks.append(buf)
        if len(part) <= size:
            buf = part
        else:
            start = 0
            while start < len(part):
                end = min(start + size, len(part))
                chunks.append(part[start:end])
                if end >= len(part):
                    break
                start = max(0, end - overlap)
            buf = ''
    if buf:
        chunks.append(buf)
    return chunks or [raw[:size]]


def _upsert_chunks(
    conn,
    source_type: str,
    source_id: int,
    title: str,
    full_text: str,
    meta: dict | None = None,
) -> int:
    pieces = _split_chunks(full_text)
    if not pieces:
        conn.execute(
            'DELETE FROM rag_chunk WHERE source_type=%s AND source_id=%s',
            (source_type, source_id),
        )
        return 0

    vectors, model = embed_texts(pieces)
    meta_json = json.dumps(meta or {}, ensure_ascii=False)
    # 清旧再插，避免 chunk 数量变化后残留
    conn.execute(
        'DELETE FROM rag_chunk WHERE source_type=%s AND source_id=%s',
        (source_type, source_id),
    )
    for i, (content, vec) in enumerate(zip(pieces, vectors)):
        conn.execute(
            '''INSERT INTO rag_chunk
               (source_type, source_id, chunk_index, title, content, meta_json,
                embedding_json, embedding_model, updated_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)''',
            (
                source_type,
                source_id,
                i,
                title or '',
                content,
                meta_json,
                json.dumps(vec),
                model,
            ),
        )
    return len(pieces)


def reindex_all(limit_scripts: int = 200, limit_knowledge: int = 300) -> dict[str, Any]:
    """全量重建索引。返回统计。"""
    conn = get_db()
    stats = {'knowledge': 0, 'script': 0, 'stock_brief': 0, 'chunks': 0, 'errors': []}

    try:
        knowledge_rows = conn.execute(
            '''SELECT id, title, content, category, tags, summary
               FROM knowledge_item
               ORDER BY id DESC LIMIT %s''',
            (limit_knowledge,),
        ).fetchall()
        for row in knowledge_rows:
            text = '\n'.join(
                x for x in [
                    row['title'] or '',
                    row['summary'] or '',
                    row['content'] or '',
                    f"标签: {row['tags']}" if row.get('tags') else '',
                ] if x
            )
            try:
                n = _upsert_chunks(
                    conn,
                    'knowledge',
                    int(row['id']),
                    row['title'] or f"知识#{row['id']}",
                    text,
                    {'category': row.get('category') or '', 'tags': row.get('tags') or ''},
                )
                stats['knowledge'] += 1
                stats['chunks'] += n
            except Exception as e:
                stats['errors'].append(f"knowledge:{row['id']}:{e}")

        script_rows = conn.execute(
            '''SELECT id, title, hook, content, ending, tags, status, content_type
               FROM script
               ORDER BY id DESC LIMIT %s''',
            (limit_scripts,),
        ).fetchall()
        for row in script_rows:
            text = '\n'.join(
                x for x in [
                    row['title'] or '',
                    row['hook'] or '',
                    row['content'] or '',
                    row['ending'] or '',
                    f"标签: {row['tags']}" if row.get('tags') else '',
                ] if x
            )
            try:
                n = _upsert_chunks(
                    conn,
                    'script',
                    int(row['id']),
                    row['title'] or f"文案#{row['id']}",
                    text,
                    {
                        'status': row.get('status') or '',
                        'content_type': row.get('content_type') or '',
                        'tags': row.get('tags') or '',
                    },
                )
                stats['script'] += 1
                stats['chunks'] += n
            except Exception as e:
                stats['errors'].append(f"script:{row['id']}:{e}")

        brief_rows = conn.execute(
            '''SELECT id, brief_date, brief_md, ai_analysis_md, source_message
               FROM stock_daily_briefing
               ORDER BY brief_date DESC LIMIT 14'''
        ).fetchall()
        for row in brief_rows:
            text = '\n'.join(
                x for x in [
                    f"日期: {row['brief_date']}",
                    row['brief_md'] or '',
                    row['ai_analysis_md'] or '',
                    row['source_message'] or '',
                ] if x
            )
            try:
                n = _upsert_chunks(
                    conn,
                    'stock_brief',
                    int(row['id']),
                    f"股票简报 · {row['brief_date']}",
                    text,
                    {'brief_date': str(row['brief_date'])},
                )
                stats['stock_brief'] += 1
                stats['chunks'] += n
            except Exception as e:
                stats['errors'].append(f"stock_brief:{row['id']}:{e}")

        conn.commit()
    finally:
        conn.close()
    return stats


def index_status() -> dict[str, Any]:
    conn = get_db()
    try:
        total = conn.execute('SELECT COUNT(*) AS c FROM rag_chunk').fetchone()['c']
        by_type = conn.execute(
            '''SELECT source_type, COUNT(*) AS c FROM rag_chunk
               GROUP BY source_type'''
        ).fetchall()
        models = conn.execute(
            '''SELECT embedding_model, COUNT(*) AS c FROM rag_chunk
               GROUP BY embedding_model'''
        ).fetchall()
        return {
            'total_chunks': int(total or 0),
            'by_type': {r['source_type']: int(r['c']) for r in by_type},
            'models': {r['embedding_model']: int(r['c']) for r in models},
        }
    finally:
        conn.close()


def ensure_index() -> dict[str, Any] | None:
    """索引为空或明显落后于源表时自动重建。"""
    status = index_status()
    conn = get_db()
    try:
        k = int(conn.execute('SELECT COUNT(*) AS c FROM knowledge_item').fetchone()['c'] or 0)
        s = int(conn.execute('SELECT COUNT(*) AS c FROM script').fetchone()['c'] or 0)
        brief = int(conn.execute('SELECT COUNT(*) AS c FROM stock_daily_briefing').fetchone()['c'] or 0)
        indexed_k = int(conn.execute(
            "SELECT COUNT(DISTINCT source_id) AS c FROM rag_chunk WHERE source_type='knowledge'"
        ).fetchone()['c'] or 0)
        indexed_s = int(conn.execute(
            "SELECT COUNT(DISTINCT source_id) AS c FROM rag_chunk WHERE source_type='script'"
        ).fetchone()['c'] or 0)
        indexed_b = int(conn.execute(
            "SELECT COUNT(DISTINCT source_id) AS c FROM rag_chunk WHERE source_type='stock_brief'"
        ).fetchone()['c'] or 0)

        if status.get('total_chunks', 0) == 0:
            if k + s + brief == 0:
                return None
            need = True
        else:
            need = (k > indexed_k) or (s > indexed_s) or (brief > indexed_b)
        if not need:
            return None
    finally:
        conn.close()
    return reindex_all()


def _query_tokens(query: str) -> list[str]:
    """中英混合分词：空白切分 + 连续汉字 2~4 字片。"""
    q = (query or '').strip().lower()
    if not q:
        return []
    tokens: list[str] = []
    for t in re.split(r'[\s,，。；;、！!？?：:（）()【】\[\]/\\|]+', q):
        t = t.strip()
        if len(t) >= 2:
            tokens.append(t)
    for run in re.findall(r'[\u4e00-\u9fff]{2,}', q):
        for n in (2, 3, 4):
            if len(run) < n:
                continue
            for i in range(len(run) - n + 1):
                tokens.append(run[i:i + n])
    # 去重保序
    seen = set()
    out = []
    for t in tokens:
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def _keyword_bonus(query: str, content: str, title: str) -> float:
    tokens = _query_tokens(query)
    if not tokens:
        return 0.0
    hay = f'{title}\n{content}'.lower()
    hit = sum(1 for t in tokens if t in hay)
    # 标题命中额外加权
    title_l = (title or '').lower()
    title_hit = sum(1 for t in tokens if t in title_l)
    return 0.18 * (hit / len(tokens)) + 0.12 * (title_hit / max(len(tokens), 1))


def search_vectors(
    query: str,
    *,
    source_types: list[str] | None = None,
    top_k: int = 6,
    min_score: float = 0.28,
) -> list[dict[str, Any]]:
    """向量检索 + 关键词加分；过滤低分噪声。"""
    ensure_index()
    q_vec, _ = embed_query(query)
    conn = get_db()
    try:
        if source_types:
            placeholders = ','.join(['%s'] * len(source_types))
            rows = conn.execute(
                f'''SELECT id, source_type, source_id, title, content, meta_json, embedding_json
                    FROM rag_chunk
                    WHERE source_type IN ({placeholders})''',
                source_types,
            ).fetchall()
        else:
            rows = conn.execute(
                '''SELECT id, source_type, source_id, title, content, meta_json, embedding_json
                   FROM rag_chunk'''
            ).fetchall()
    finally:
        conn.close()

    scored: list[dict[str, Any]] = []
    for row in rows:
        try:
            emb = json.loads(row['embedding_json'] or '[]')
        except Exception:
            emb = []
        if not emb:
            continue
        # 超长新闻简报易产生哈希碰撞噪声，略降权
        raw = cosine_similarity(q_vec, emb) + _keyword_bonus(
            query, row['content'] or '', row['title'] or ''
        )
        st = row['source_type']
        if st == 'stock_brief' and len(row['content'] or '') > 800:
            raw *= 0.85
        try:
            meta = json.loads(row['meta_json'] or '{}')
        except Exception:
            meta = {}
        scored.append({
            'chunk_id': row['id'],
            'source_type': st,
            'source_id': row['source_id'],
            'title': row['title'] or '',
            'content': row['content'] or '',
            'meta': meta,
            'score': round(float(raw), 4),
            'label': SOURCE_LABELS.get(st, st),
        })

    scored.sort(key=lambda x: x['score'], reverse=True)
    if not scored:
        return []

    top = scored[0]['score']
    # 相对阈值：明显弱于最优结果的丢掉；绝对阈值防噪声
    floor = max(float(min_score), top * 0.55)

    seen: set[tuple] = set()
    unique: list[dict[str, Any]] = []
    for item in scored:
        if item['score'] < floor:
            continue
        key = (item['source_type'], item['source_id'])
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
        if len(unique) >= top_k:
            break
    return unique
