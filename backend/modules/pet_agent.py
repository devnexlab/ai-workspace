"""
桌宠数据问答 Agent：规划 → 多源检索/工具 → 带引用作答。
"""

from __future__ import annotations

import json
from typing import Any

from config import get_db
from modules.ai_writer import call_llm
from modules.pet_rag import search_vectors

MODE_SOURCES = {
    'auto': ['knowledge', 'script', 'stock_brief'],
    'knowledge': ['knowledge'],
    'script': ['script'],
    'stock': ['stock_brief'],
}

SOURCE_PATH = {
    'knowledge': '/knowledge',
    'script': '/scripts',
    'stock_brief': '/stocks',
    'watchlist': '/stocks/watchlist',
    'alert': '/stocks/watchlist',
}

# 内容/知识意图：默认不碰股票简报
_CONTENT_KEYS = (
    '口播', '文案', '开头', '知识库', '写一条', '写一', '话术', '脚本',
    '重疾', '养老', '养老金', '保险', '理赔', '保单', '条款', '对比',
    '避坑', '种草', '标题', '钩子', '收口', '根据知识',
)

_STOCK_KEYS = (
    '持仓', '自选', '跌破', '成本', '预警', '股价', '股票', '涨跌',
    '仓位', '目标价', '买入', '行情', '简报', '大盘', 'A股', '港股',
    '个股', '涨停', '跌停', '板块',
)


def _step(text: str, state: str = 'ok') -> dict:
    return {'text': text, 'state': state}


def _has_any(text: str, keys: tuple[str, ...]) -> bool:
    q = text or ''
    return any(k in q for k in keys)


def _resolve_sources(question: str, mode: str) -> tuple[list[str], str]:
    """
    按模式与意图选择检索源。
    Returns: (sources, reason)
    """
    if mode != 'auto':
        return list(MODE_SOURCES.get(mode, MODE_SOURCES['auto'])), f'模式锁定 {mode}'

    wants_content = _has_any(question, _CONTENT_KEYS)
    wants_stock = _has_any(question, _STOCK_KEYS)

    if wants_content and not wants_stock:
        return ['knowledge', 'script'], '识别为内容/知识问答，排除股票简报'
    if wants_stock and not wants_content:
        return ['stock_brief'], '识别为股票相关，检索简报'
    if wants_stock and wants_content:
        return ['knowledge', 'script', 'stock_brief'], '内容与股票意图并存'
    # 默认优先知识库+文案，避免无关简报噪声
    return ['knowledge', 'script'], '默认优先知识库与文案'


def _cite_from_hit(hit: dict) -> dict:
    st = hit['source_type']
    meta = hit.get('meta') or {}
    extra = ''
    if st == 'knowledge':
        extra = meta.get('category') or meta.get('tags') or ''
    elif st == 'script':
        extra = meta.get('status') or meta.get('content_type') or ''
    elif st == 'stock_brief':
        extra = meta.get('brief_date') or ''
    meta_line = ' · '.join(x for x in [hit.get('label') or st, extra] if x)
    return {
        'score': f"{hit['score']:.2f}",
        'title': hit.get('title') or f"{st}#{hit.get('source_id')}",
        'meta': meta_line,
        'source_type': st,
        'source_id': hit.get('source_id'),
        'path': SOURCE_PATH.get(st, '/'),
        'snippet': (hit.get('content') or '')[:180],
    }


def _tool_watchlist() -> tuple[list[dict], str]:
    """读取自选/持仓与跌破成本情况。"""
    conn = get_db()
    try:
        rows = conn.execute(
            '''SELECT id, stock_code, stock_name, list_type, buy_price, current_price,
                      quantity, target_price, notes
               FROM stock_watchlist
               ORDER BY list_type, id'''
        ).fetchall()
        alerts = conn.execute(
            '''SELECT id, title, content, priority, status, created_at
               FROM reminder
               WHERE type=%s
               ORDER BY created_at DESC LIMIT 20''',
            ('stock_alert',),
        ).fetchall()
    finally:
        conn.close()

    cites = [{
        'score': '工具',
        'title': '自选股 / 持仓列表',
        'meta': f'系统数据 · {len(rows)} 条',
        'source_type': 'watchlist',
        'source_id': 0,
        'path': '/stocks/watchlist',
        'snippet': '',
    }]
    if alerts:
        cites.append({
            'score': '工具',
            'title': '股价预警记录',
            'meta': f'stock_alert · {len(alerts)} 条',
            'source_type': 'alert',
            'source_id': 0,
            'path': '/stocks/watchlist',
            'snippet': '',
        })

    lines = []
    below = []
    for r in rows:
        name = r['stock_name'] or ''
        code = r['stock_code'] or ''
        lt = r['list_type'] or 'watch'
        buy = float(r['buy_price'] or 0)
        cur = float(r['current_price'] or 0)
        tgt = float(r['target_price'] or 0)
        line = f"- [{lt}] {name}({code}) 现价={cur}"
        if buy:
            line += f" 成本={buy}"
            if cur and cur < buy:
                below.append(f"{name}({code})")
                line += ' 【跌破成本】'
        if tgt:
            line += f" 目标={tgt}"
            if cur and cur >= tgt:
                line += ' 【触及目标】'
        if r.get('notes'):
            line += f" 备注={r['notes']}"
        lines.append(line)

    alert_lines = []
    for a in alerts[:8]:
        alert_lines.append(
            f"- [{a.get('status')}] {a.get('title') or ''} {a.get('content') or ''}"
        )

    body = '自选股快照：\n' + ('\n'.join(lines) if lines else '（暂无自选股）')
    if below:
        body += '\n\n跌破成本：' + '、'.join(below)
    if alert_lines:
        body += '\n\n近期预警：\n' + '\n'.join(alert_lines)
    body += '\n\n（行情可能延迟，不构成投资建议）'
    return cites, body


def _wants_stock_tool(question: str, mode: str) -> bool:
    if mode == 'stock':
        return True
    if mode in ('knowledge', 'script'):
        return False
    # 内容意图下即使含「成本」等词也不开股票工具（如「保险成本」）
    if _has_any(question, _CONTENT_KEYS) and not _has_any(question, (
        '持仓', '自选', '股价', '股票', '跌破成本', '目标价', '行情', '简报',
    )):
        return False
    return _has_any(question, (
        '持仓', '自选', '跌破', '预警', '股价', '股票', '涨跌',
        '仓位', '目标价', '行情',
    ))


def _build_context(hits: list[dict], tool_text: str) -> str:
    parts = []
    if tool_text:
        parts.append('【系统工具结果】\n' + tool_text)
    for i, h in enumerate(hits, 1):
        parts.append(
            f"【资料{i} | {h.get('label')} | 相似度{h['score']:.2f} | {h.get('title')}】\n"
            f"{(h.get('content') or '')[:900]}"
        )
    return '\n\n'.join(parts) if parts else '（未召回到相关资料）'


def run_pet_agent(
    question: str,
    *,
    mode: str = 'auto',
    history: list[dict] | None = None,
) -> dict[str, Any]:
    """
    执行一轮问答。

    Returns:
        answer, steps, cites, mode
    """
    q = (question or '').strip()
    mode = mode if mode in MODE_SOURCES else 'auto'
    steps: list[dict] = []
    cites: list[dict] = []

    if not q:
        return {
            'answer': '请先输入问题。',
            'steps': [_step('空问题，已跳过')],
            'cites': [],
            'mode': mode,
        }

    mode_label = {
        'auto': '智能 Agent',
        'knowledge': '偏知识库',
        'script': '偏文案',
        'stock': '偏股票',
    }.get(mode, mode)
    steps.append(_step(f'理解问题 · 模式「{mode_label}」'))

    sources, route_reason = _resolve_sources(q, mode)
    steps.append(_step(f'路由 · {route_reason}'))

    hits: list[dict] = []
    tool_text = ''

    use_stock = _wants_stock_tool(q, mode)
    if use_stock:
        steps.append(_step('工具调用 · 读取自选股 / 预警'))
        tool_cites, tool_text = _tool_watchlist()
        cites.extend(tool_cites)

    label_map = {
        'knowledge': '知识库',
        'script': '文案库',
        'stock_brief': '股票简报',
    }
    src_names = ' / '.join(label_map.get(s, s) for s in sources)
    steps.append(_step(f'向量检索 · {src_names}'))
    hits = search_vectors(q, source_types=sources, top_k=6, min_score=0.30)

    # 仅在股票意图且简报未命中时，补捞简报；内容意图绝不扩到股票
    if (
        mode == 'auto'
        and use_stock
        and 'stock_brief' in sources
        and not any(h['source_type'] == 'stock_brief' for h in hits)
    ):
        extra = search_vectors(q, source_types=['stock_brief'], top_k=2, min_score=0.32)
        hits.extend(extra)

    # 内容意图：知识库+文案都空时，不要去搜股票；可再放宽阈值重试内容源
    if mode == 'auto' and not hits and not tool_text:
        if sources == ['knowledge', 'script']:
            steps.append(_step('放宽阈值 · 仅知识库/文案重试'))
            hits = search_vectors(q, source_types=sources, top_k=6, min_score=0.18)
        elif not _has_any(q, _CONTENT_KEYS):
            steps.append(_step('扩大检索范围 · 全库重试'))
            hits = search_vectors(q, source_types=None, top_k=6, min_score=0.30)

    for h in hits:
        cites.append(_cite_from_hit(h))

    steps.append(_step('汇总并标注引用'))

    context = _build_context(hits, tool_text)
    hist_lines = []
    for m in (history or [])[-6:]:
        role = '用户' if m.get('role') == 'user' else '助手'
        hist_lines.append(f"{role}: {(m.get('content') or '')[:400]}")
    history_block = '\n'.join(hist_lines) if hist_lines else '（无）'

    has_refs = bool(hits) or bool(tool_text)
    system_prompt = (
        '你是「智仔」，智能运营台内的数据问答助手。'
        '只根据提供的【资料】与【系统工具结果】回答，不要编造库中没有的数字或条款。'
        '若资料与问题明显无关（例如问口播/养老金却给了股市新闻），必须忽略无关资料，'
        '明确说明知识库或文案中暂无足够依据，不要复述无关新闻标题或行情。'
        '不要在正文里罗列「引用列表」或新闻标题清单；系统会单独展示引用卡片。'
        '若资料不足，说明不足并建议去知识库/文案页补充。'
        '回答用简洁中文；涉及股票时声明不构成投资建议。'
        '不要输出 JSON。'
    )
    ref_hint = (
        '若确实使用了相关资料，文末只需一句「详见下方引用」，不要自己列出处标题。'
        if has_refs else
        '当前没有可用相关资料，请如实说明，不要编造引用。'
    )
    prompt = (
        f'对话历史：\n{history_block}\n\n'
        f'用户问题：{q}\n\n'
        f'检索到的资料与工具结果：\n{context}\n\n'
        f'{ref_hint}'
    )

    try:
        answer, _tokens, _model = call_llm(
            prompt,
            system_prompt=system_prompt,
            temperature=0.35,
            max_tokens=1200,
        )
        answer = (answer or '').strip()
    except Exception as e:
        answer = (
            f'AI 暂不可用（{e}）。根据检索结果摘录如下：\n\n'
            + (tool_text[:800] if tool_text else '')
        )
        if hits:
            answer += '\n\n' + '\n\n'.join(
                f"· {h['title']}\n{(h['content'] or '')[:220]}" for h in hits[:3]
            )
        if not hits and not tool_text:
            answer = (
                f'未能完成回答：{e}。请先在系统设置配置可用的大模型，'
                '并确认知识库/文案有相关数据。'
            )

    # 引用去重；工具引用仅在真正使用股票工具时保留
    uniq: list[dict] = []
    seen: set[tuple] = set()
    for c in cites:
        key = (c.get('source_type'), c.get('source_id'), c.get('title'))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(c)

    return {
        'answer': answer,
        'steps': steps,
        'cites': uniq[:8],
        'mode': mode,
    }


def create_session(title: str = '') -> int:
    conn = get_db()
    try:
        cur = conn.execute(
            'INSERT INTO pet_chat_session (title) VALUES (%s)',
            (title or '智仔对话',),
        )
        sid = cur.lastrowid
        conn.commit()
        return int(sid)
    finally:
        conn.close()


def append_message(session_id: int, role: str, content: str, meta: dict | None = None) -> None:
    conn = get_db()
    try:
        conn.execute(
            '''INSERT INTO pet_chat_message (session_id, role, content, meta_json)
               VALUES (%s, %s, %s, %s)''',
            (session_id, role, content or '', json.dumps(meta or {}, ensure_ascii=False)),
        )
        conn.execute(
            'UPDATE pet_chat_session SET updated_at=CURRENT_TIMESTAMP WHERE id=%s',
            (session_id,),
        )
        conn.commit()
    finally:
        conn.close()


def load_history(session_id: int, limit: int = 12) -> list[dict]:
    conn = get_db()
    try:
        rows = conn.execute(
            '''SELECT role, content FROM pet_chat_message
               WHERE session_id=%s
               ORDER BY id DESC LIMIT %s''',
            (session_id, limit),
        ).fetchall()
        return [{'role': r['role'], 'content': r['content']} for r in reversed(list(rows))]
    finally:
        conn.close()
