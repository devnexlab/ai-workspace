"""AI Knowledge Base routes - personal second brain (V1.2 new module)."""

from flask import Blueprint, request, jsonify
from config import get_db as _db
import json

bp = Blueprint('knowledge', __name__)


@bp.route('/api/knowledge')
def list_knowledge():
    conn = _db()
    page = int(request.args.get('page', 1))
    pageSize = int(request.args.get('pageSize', 20))
    category = request.args.get('category', '')
    source_type = request.args.get('source_type', '')
    q = request.args.get('q', '')

    where = []
    params = []
    if category:
        where.append('category=%s')
        params.append(category)
    if source_type:
        where.append('source_type=%s')
        params.append(source_type)
    if q:
        where.append('(title LIKE %s OR content LIKE %s OR tags LIKE %s)')
        params.extend([f'%{q}%' for _ in range(3)])

    where_clause = ('WHERE ' + ' AND '.join(where)) if where else ''
    offset = (page - 1) * pageSize

    total = conn.execute(
        f'SELECT COUNT(*) as c FROM knowledge_item {where_clause}', params
    ).fetchone()['c']

    rows = conn.execute(
        f'SELECT * FROM knowledge_item {where_clause} ORDER BY created_at DESC LIMIT %s OFFSET %s',
        params + [pageSize, offset]
    ).fetchall()
    conn.close()

    return jsonify({
        'list': [dict(r) for r in rows],
        'page': page,
        'pageSize': pageSize,
        'total': total,
    })


@bp.route('/api/knowledge/<int:id>')
def get_knowledge(id):
    conn = _db()
    row = conn.execute('SELECT * FROM knowledge_item WHERE id=%s', (id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'not found'}), 404
    result = dict(row)
    # Parse related_ids
    if result.get('related_ids'):
        try:
            result['related_ids'] = json.loads(result['related_ids'])
        except Exception:
            result['related_ids'] = []
    else:
        result['related_ids'] = []
    return jsonify(result)


@bp.route('/api/knowledge', methods=['POST'])
def create_knowledge():
    data = request.get_json(silent=True) or {}
    conn = _db()
    cur = conn.execute(
        '''INSERT INTO knowledge_item
           (title, content, source_type, category, tags, source_url)
           VALUES (%s, %s, %s, %s, %s, %s)''',
        (data.get('title', ''), data.get('content', ''),
         data.get('source_type', 'note'), data.get('category', ''),
         data.get('tags', ''), data.get('source_url', ''))
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'id': new_id, 'message': '知识已添加'})


@bp.route('/api/knowledge/upload', methods=['POST'])
def upload_knowledge():
    """上传 PDF / 音频，抽取文本写入 knowledge_item。"""
    import os
    import time
    from pathlib import Path
    from werkzeug.utils import secure_filename
    from config import KNOWLEDGE_DIR

    if 'file' not in request.files:
        return jsonify({'error': '没有文件上传'}), 400
    file = request.files['file']
    if not file.filename:
        return jsonify({'error': '文件名为空'}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    pdf_ext = {'.pdf'}
    audio_ext = {'.mp3', '.wav', '.m4a', '.aac', '.ogg', '.flac', '.webm'}
    if ext not in pdf_ext and ext not in audio_ext:
        return jsonify({'error': f'仅支持 PDF 或音频文件，当前：{ext}'}), 400

    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    safe = secure_filename(file.filename) or f'upload{ext}'
    unique = f'{int(time.time() * 1000)}_{safe}'
    save_path = Path(KNOWLEDGE_DIR) / unique
    file.save(str(save_path))

    title = request.form.get('title') or os.path.splitext(file.filename)[0]
    category = request.form.get('category') or ''
    content = ''
    source_type = 'pdf' if ext in pdf_ext else 'voice'

    try:
        if source_type == 'pdf':
            try:
                from pypdf import PdfReader
            except ImportError:
                return jsonify({'error': '未安装 pypdf，请执行: pip install pypdf'}), 500
            reader = PdfReader(str(save_path))
            parts = []
            for page in reader.pages[:80]:
                try:
                    parts.append(page.extract_text() or '')
                except Exception:
                    continue
            content = '\n'.join(parts).strip()
            if not content:
                content = '（未能从 PDF 抽出文本，可能是扫描件）'
        else:
            try:
                from faster_whisper import WhisperModel
            except ImportError:
                return jsonify({
                    'error': '未安装 faster-whisper，请执行: pip install faster-whisper',
                    'hint': '安装后重启后端即可转写音频',
                }), 500
            model_size = request.form.get('model') or 'base'
            model = WhisperModel(model_size, device='cpu', compute_type='int8')
            segments, info = model.transcribe(str(save_path), language='zh')
            content = '\n'.join(seg.text.strip() for seg in segments if seg.text).strip()
            if not content:
                content = '（音频转写结果为空）'
            if info and getattr(info, 'language', None):
                content = f'[lang={info.language}]\n{content}'
    except Exception as e:
        return jsonify({'error': f'解析失败: {e}'}), 500

    conn = _db()
    cur = conn.execute(
        '''INSERT INTO knowledge_item
           (title, content, source_type, category, tags, source_url, source_file)
           VALUES (%s, %s, %s, %s, %s, %s, %s)''',
        (title, content, source_type, category, '', '', str(save_path))
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return jsonify({
        'id': new_id,
        'title': title,
        'source_type': source_type,
        'content_preview': content[:400],
        'message': '已导入并抽取文本，可继续 AI 整理',
    })


@bp.route('/api/knowledge/<int:id>', methods=['PUT'])
def update_knowledge(id):
    data = request.get_json(silent=True) or {}
    conn = _db()
    fields = []
    params = []
    for k in ['title', 'content', 'source_type', 'category', 'tags', 'summary', 'ai_analysis', 'related_ids', 'source_url']:
        if k in data:
            fields.append(f'{k}=%s')
            val = data[k]
            if k == 'related_ids' and isinstance(val, list):
                val = json.dumps(val, ensure_ascii=False)
            params.append(val)
    if fields:
        params.append(id)
        conn.execute(f'UPDATE knowledge_item SET {",".join(fields)} WHERE id=%s', params)
        conn.commit()
    conn.close()
    return jsonify({'message': '已更新'})


@bp.route('/api/knowledge/<int:id>', methods=['DELETE'])
def delete_knowledge(id):
    conn = _db()
    conn.execute('DELETE FROM knowledge_item WHERE id=%s', (id,))
    conn.commit()
    conn.close()
    return jsonify({'message': '已删除'})


@bp.route('/api/knowledge/<int:id>/ai-process', methods=['POST'])
def ai_process_knowledge(id):
    """AI auto-categorizes, tags, summarizes, and finds related items."""
    from modules.ai_writer import call_llm
    conn = _db()
    row = conn.execute('SELECT * FROM knowledge_item WHERE id=%s', (id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'not found'}), 404

    item = dict(row)

    # Get all other items for relation matching
    all_items = conn.execute(
        'SELECT id, title, tags, category FROM knowledge_item WHERE id != %s LIMIT 200', (id,)
    ).fetchall()
    conn.close()

    other_titles = '; '.join([f"[{r['id']}] {r['title']}" for r in all_items]) or '暂无其他知识'

    prompt = f"""请对以下知识内容进行AI整理：

标题：{item.get('title','')}
内容：{item.get('content','')[:2000]}
来源类型：{item.get('source_type','')}
当前分类：{item.get('category','')}
当前标签：{item.get('tags','')}

已有知识库条目（供关联参考）：
{other_titles}

请以JSON格式返回：
{{
  "category": "必须从这些分类里选一个：股票交易、股票市场分析、交易复盘、保险干货、客户跟进、产品话术、内容运营、学习笔记、政策法规、生活灵感、未分类",
  "tags": "逗号分隔的标签",
  "summary": "100字以内的摘要",
  "related_ids": [相关知识的ID列表],
  "ai_analysis": "深度分析和知识联想"
}}"""

    try:
        resp, _tokens, _model = call_llm(prompt, system_prompt="你是知识管理专家，擅长分类、总结和建立知识关联。")
        import re
        json_match = re.search(r'\{[\s\S]*\}', resp)
        if json_match:
            result = json.loads(json_match.group())
        else:
            result = {'summary': resp[:200], 'category': '', 'tags': '', 'related_ids': [], 'ai_analysis': ''}

        related_ids = json.dumps(result.get('related_ids', []), ensure_ascii=False)

        conn = _db()
        conn.execute(
            '''UPDATE knowledge_item
               SET category=%s, tags=%s, summary=%s, related_ids=%s, ai_analysis=%s
               WHERE id=%s''',
            (result.get('category', ''), result.get('tags', ''),
             result.get('summary', ''), related_ids,
             result.get('ai_analysis', ''), id)
        )
        conn.commit()
        conn.close()
        return jsonify({'result': result, 'message': 'AI整理完成'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# 默认知识分类（与库内已用分类合并返回）
DEFAULT_KNOWLEDGE_CATEGORIES = [
    '股票交易',
    '股票市场分析',
    '交易复盘',
    '保险干货',
    '客户跟进',
    '产品话术',
    '内容运营',
    '学习笔记',
    '政策法规',
    '生活灵感',
    '未分类',
]


@bp.route('/api/knowledge/categories')
def list_categories():
    """预设分类 + 库内已用分类（去重）。"""
    conn = _db()
    rows = conn.execute(
        'SELECT DISTINCT category FROM knowledge_item WHERE category IS NOT NULL AND category != %s ORDER BY category',
        ('',)
    ).fetchall()
    conn.close()
    used = [r['category'] for r in rows if r['category']]
    merged = []
    seen = set()
    for c in DEFAULT_KNOWLEDGE_CATEGORIES + used:
        if c and c not in seen:
            seen.add(c)
            merged.append(c)
    return jsonify({'list': merged, 'presets': DEFAULT_KNOWLEDGE_CATEGORIES, 'used': used})


@bp.route('/api/knowledge/compare', methods=['POST'])
def compare_knowledge():
    """
    多笔记对比 → 启发灵感。
    body: { ids: [1,2,3] } 或 { contents: [{title, content}, ...] }
    """
    from modules.ai_writer import call_llm
    import re
    data = request.get_json(silent=True) or {}
    ids = data.get('ids') or []
    blocks = []

    if ids:
        conn = _db()
        for kid in ids[:8]:
            row = conn.execute('SELECT * FROM knowledge_item WHERE id=%s', (kid,)).fetchone()
            if row:
                blocks.append(dict(row))
        conn.close()
    for c in (data.get('contents') or [])[:8]:
        blocks.append({'title': c.get('title', ''), 'content': c.get('content', '')})

    if len(blocks) < 1:
        return jsonify({'error': '请至少提供 1 条知识'}), 400

    joined = '\n\n'.join([
        f"【{i + 1}】{b.get('title', '')}\n{(b.get('content') or b.get('summary') or '')[:1200]}"
        for i, b in enumerate(blocks)
    ])
    prompt = f"""以下是我零散记录的学习/交易笔记，请做对比分析并激发新灵感：

{joined}

请以 JSON 返回：
{{
  "common_themes": "共同主题",
  "conflicts": "相互矛盾或待验证之处",
  "connections": "可打通的知识连接",
  "inspirations": ["灵感1", "灵感2", "灵感3"],
  "next_actions": ["下一步可做的事1", "下一步2"],
  "one_liner": "一句话启发"
}}"""
    try:
        resp, tokens, model = call_llm(prompt, system_prompt='你是擅长跨笔记联想的学习教练，帮技术交易者把散点知识织成系统。')
        m = re.search(r'\{[\s\S]*\}', resp or '')
        result = json.loads(m.group()) if m else {'one_liner': (resp or '')[:300], 'inspirations': []}
        return jsonify({'result': result, 'tokens': tokens, 'model': model, 'message': '对比完成'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
