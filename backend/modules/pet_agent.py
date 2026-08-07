"""
桌宠数据问答 Agent：规划 → 多源检索/工具 → 带引用作答。
工具：金融实时（股票/资金）· 保险常识 · 自选股。
"""

from __future__ import annotations

import json
from typing import Any

from config import get_db
from modules.ai_writer import call_llm
from modules.pet_rag import search_vectors
from modules.pet_tools_finance import tool_finance_market
from modules.pet_tools_insurance import tool_insurance_knowledge

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
    'finance_tool': '/stocks',
    'insurance_tool': '/knowledge',
}

# 口播/文案创作意图
_CONTENT_WRITE_KEYS = (
    '口播', '文案', '开头', '写一条', '写一', '话术', '脚本',
    '种草', '标题', '钩子', '收口', '根据知识库写',
)

# 保险常识意图
_INSURANCE_KEYS = (
    '保险', '重疾', '医疗险', '寿险', '年金', '养老险', '养老金', '理赔',
    '保单', '条款', '等待期', '犹豫期', '保额', '保费', '现金价值',
    '核保', '受益人', '社保', '商保', '定寿', '终身寿', '避坑',
)

# 金融/股票实时（与自选股工具区分：偏市场数据）
_FINANCE_KEYS = (
    '北向', '南向', '沪股通', '深股通', '港股通', '资金净流入', '净流入',
    '行业流入', '板块流入', '主力净流入', '资金流向', '成交净买',
    '大盘', '沪深300', '上证', '深证', '行情', '涨跌幅', '板块',
    '股票', 'A股', '港股', '个股', '涨停', '跌停', '金融', '股市',
)

_WATCHLIST_KEYS = (
    '持仓', '自选', '跌破成本', '目标价', '预警', '仓位', '我的股票',
)


def _step(text: str, state: str = 'ok') -> dict:
    return {'text': text, 'state': state}


def _has_any(text: str, keys: tuple[str, ...]) -> bool:
    q = text or ''
    return any(k in q for k in keys)


def _resolve_intents(question: str, mode: str) -> dict[str, bool]:
    """根据问题与模式决定启用哪些工具 / 检索源。"""
    q = question or ''
    write = _has_any(q, _CONTENT_WRITE_KEYS)
    insurance = _has_any(q, _INSURANCE_KEYS) or mode == 'knowledge'
    finance = _has_any(q, _FINANCE_KEYS) or mode == 'stock'
    watch = _has_any(q, _WATCHLIST_KEYS)

    if mode == 'script':
        return {
            'write': True,
            'insurance': insurance or write,
            'finance': False,
            'watch': False,
            'vector_knowledge': True,
            'vector_script': True,
            'vector_brief': False,
        }

    if mode == 'knowledge':
        return {
            'write': write,
            'insurance': _has_any(q, _INSURANCE_KEYS),
            'finance': False,
            'watch': False,
            'vector_knowledge': True,
            'vector_script': True,
            'vector_brief': False,
        }

    if mode == 'stock':
        return {
            'write': False,
            'insurance': False,
            'finance': True,
            'watch': True,
            'vector_knowledge': False,
            'vector_script': False,
            'vector_brief': True,
        }

    # auto
    # 纯创作且无行情词：不开金融工具
    if write and not finance:
        finance = False
    # 保险常识问法默认开保险工具；若同时写口播也开
    if write and _has_any(q, _INSURANCE_KEYS):
        insurance = True
    # 「知识库」字样但不一定是保险
    if '知识库' in q and not finance:
        insurance = insurance or _has_any(q, _INSURANCE_KEYS)

    return {
        'write': write,
        'insurance': insurance,
        'finance': finance,
        'watch': watch,
        'vector_knowledge': (not finance) or insurance or write or (not finance and not watch),
        'vector_script': write or insurance or (not finance and not watch),
        'vector_brief': finance and not write,
    }


def _resolve_sources(intents: dict[str, bool], mode: str) -> tuple[list[str], str]:
    if mode != 'auto':
        return list(MODE_SOURCES.get(mode, MODE_SOURCES['auto'])), f'模式锁定 {mode}'

    sources = []
    if intents.get('vector_knowledge'):
        sources.append('knowledge')
    if intents.get('vector_script'):
        sources.append('script')
    if intents.get('vector_brief'):
        sources.append('stock_brief')

    if not sources:
        if intents.get('finance') or intents.get('watch'):
            sources = ['stock_brief']
        else:
            sources = ['knowledge', 'script']

    reasons = []
    if intents.get('finance'):
        reasons.append('金融实时')
    if intents.get('insurance'):
        reasons.append('保险常识')
    if intents.get('watch'):
        reasons.append('自选股')
    if intents.get('write'):
        reasons.append('内容创作')
    return sources, ('识别：' + ' + '.join(reasons)) if reasons else '默认知识库/文案'


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


def _build_context(hits: list[dict], tool_blocks: list[str]) -> str:
    parts = []
    for block in tool_blocks:
        if block:
            parts.append('【系统工具结果】\n' + block)
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

    intents = _resolve_intents(q, mode)
    sources, route_reason = _resolve_sources(intents, mode)
    steps.append(_step(f'路由 · {route_reason}'))

    hits: list[dict] = []
    tool_blocks: list[str] = []

    # —— 工具调用 ——
    if intents.get('finance'):
        steps.append(_step('工具调用 · 金融实时（北向 / 行业资金）'))
        try:
            c, text = tool_finance_market(q)
            cites.extend(c)
            tool_blocks.append(text)
        except Exception as e:
            tool_blocks.append(f'金融实时工具失败：{e}')

    if intents.get('watch'):
        steps.append(_step('工具调用 · 读取自选股 / 预警'))
        try:
            c, text = _tool_watchlist()
            cites.extend(c)
            tool_blocks.append(text)
        except Exception as e:
            tool_blocks.append(f'自选股工具失败：{e}')

    if intents.get('insurance'):
        steps.append(_step('工具调用 · 保险常识'))
        try:
            c, text = tool_insurance_knowledge(q)
            cites.extend(c)
            tool_blocks.append(text)
        except Exception as e:
            tool_blocks.append(f'保险常识工具失败：{e}')

    # —— 向量检索（保险工具已含知识库召回时，auto 下可减少重复）——
    skip_vector = bool(intents.get('insurance') and not intents.get('write') and not intents.get('finance'))
    if not skip_vector and sources:
        label_map = {
            'knowledge': '知识库',
            'script': '文案库',
            'stock_brief': '股票简报',
        }
        src_names = ' / '.join(label_map.get(s, s) for s in sources)
        steps.append(_step(f'向量检索 · {src_names}'))
        min_score = 0.30
        if intents.get('finance'):
            # 金融问法主要靠工具；简报仅作补充且阈值更高
            min_score = 0.35
        hits = search_vectors(q, source_types=sources, top_k=5, min_score=min_score)
        for h in hits:
            cites.append(_cite_from_hit(h))
    elif skip_vector:
        steps.append(_step('向量检索 · 已由保险工具覆盖，跳过重复召回'))

    if mode == 'auto' and not hits and not tool_blocks:
        steps.append(_step('放宽检索 · 知识库/文案'))
        hits = search_vectors(q, source_types=['knowledge', 'script'], top_k=6, min_score=0.18)
        for h in hits:
            cites.append(_cite_from_hit(h))

    steps.append(_step('汇总并标注引用'))

    context = _build_context(hits, tool_blocks)
    hist_lines = []
    for m in (history or [])[-6:]:
        role = '用户' if m.get('role') == 'user' else '助手'
        hist_lines.append(f"{role}: {(m.get('content') or '')[:400]}")
    history_block = '\n'.join(hist_lines) if hist_lines else '（无）'

    has_refs = bool(hits) or bool(tool_blocks)
    system_prompt = (
        '你是「智仔」，智能运营台内的数据问答助手。'
        '优先使用【系统工具结果】中的实时数据与保险常识；不要编造数字或条款。'
        '问北向资金/行业流入时，只依据金融实时工具数据作答；不要拿无关新闻标题充数。'
        '若工具写明北向「未披露」，必须如实说暂未披露，禁止把 0 或空值说成「净流入 0 亿元」。'
        '行业资金有数据时可照常回答流入最多的行业。'
        '问保险常识时，可综合内置常识与知识库召回；条款细节以用户知识库与产品合同为准。'
        '若资料与问题无关，必须忽略并说明不足。'
        '不要在正文里罗列引用清单；系统会单独展示引用卡片。'
        '涉及股票/资金时声明不构成投资建议；涉及保险时声明不构成销售误导。'
        '不要输出 JSON。'
    )
    ref_hint = (
        '若确实使用了相关资料或工具，文末只需一句「详见下方引用」。'
        if has_refs else
        '当前没有可用相关资料，请如实说明，不要编造。'
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
        answer = f'AI 暂不可用（{e}）。根据工具/检索摘录如下：\n\n' + '\n\n'.join(
            b[:800] for b in tool_blocks[:2]
        )
        if hits:
            answer += '\n\n' + '\n\n'.join(
                f"· {h['title']}\n{(h['content'] or '')[:220]}" for h in hits[:3]
            )
        if not hits and not tool_blocks:
            answer = (
                f'未能完成回答：{e}。请配置大模型，或稍后重试金融/保险工具。'
            )

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
        'cites': uniq[:10],
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
