"""
桌宠数据问答 Agent：规划 → 多源检索/工具 → 带引用作答。
工具：金融实时（股票/资金）· 保险常识 · 自选股。
"""

from __future__ import annotations

import json
import re
from typing import Any

from config import get_db
from modules.ai.writer import call_llm
from modules.pet.rag import search_vectors
from modules.pet.tools_finance import tool_finance_market
from modules.pet.tools_insurance import tool_insurance_knowledge
from modules.pet.tools_ops import try_run_ops
from modules.pet.tools_data import tool_query_database
from modules.pet.tools_web import web_search

MODE_SOURCES = {
    'auto': ['knowledge', 'script', 'stock_brief'],
    'knowledge': ['knowledge'],
    'script': ['script'],
    'stock': ['stock_brief'],
    'ops': [],
    'data': [],
    'web': [],
}

SOURCE_PATH = {
    'knowledge': '/knowledge',
    'script': '/scripts',
    'stock_brief': '/stocks',
    'watchlist': '/stocks/watchlist',
    'alert': '/stocks/watchlist',
    'finance_tool': '/stocks',
    'insurance_tool': '/knowledge',
    'ops_tool': '/videos',
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

# 金融/股票实时（与自选股工具区分：偏市场数据）——仅作 LLM 提示说明，不作关键词硬判
_FINANCE_TOOL_HINT = (
    '金融实时工具适用：北向/南向/沪深港通净买额、行业资金流入流出、即时资金类行情。'
    '不适用于：政策、监管、新闻解读、一般百科（这些应走联网检索）。'
)

_WATCHLIST_KEYS = (
    '持仓', '自选', '跌破成本', '目标价', '预警', '仓位', '我的股票',
)

# 本地库 / 联网：仅作 auto 模式的弱提示；data/web 锁定模式由 LLM 路由决定
_DATA_KEYS = (
    '我的数据库', '查表', '客户表', '线索表', '有多少客户', '几个客户', '统计一下',
    '全部表', '库里', '订单', '哪个表', '查一下库', '库里有多少', '客户数',
    '高意向', '几条数据', '数据库里', '查数据库', '本地库',
)

_WEB_KEYS = (
    '网上', '搜索', '查一下网上', '最新消息', '新闻', '百科', '这个链接', '网页',
    '联网', '上网查', '搜一下', '网上怎么说', '最新的政策', '网上看看',
)

def _step(text: str, state: str = 'ok') -> dict:
    return {'text': text, 'state': state}


def _has_any(text: str, keys: tuple[str, ...]) -> bool:
    q = text or ''
    return any(k in q for k in keys)


def _parse_route_json(raw: str) -> dict:
    m = re.search(r'\{[\s\S]*\}', (raw or '').strip())
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _normalize_choices(raw) -> list[dict]:
    out: list[dict] = []
    if not isinstance(raw, list):
        return out
    for i, c in enumerate(raw[:5]):
        if isinstance(c, str) and c.strip():
            out.append({'id': f'v{i}', 'label': c.strip()[:40], 'message': c.strip()[:120]})
        elif isinstance(c, dict):
            label = str(c.get('label') or c.get('text') or '').strip()
            message = str(c.get('message') or c.get('value') or label).strip()
            if label and message:
                out.append({
                    'id': str(c.get('id') or f'v{i}'),
                    'label': label[:40],
                    'message': message[:160],
                })
    return out


def plan_source_route(
    question: str,
    mode: str,
    history: list[dict] | None = None,
) -> dict:
    """用语义理解决定工具，不写死关键词。

    mode: web | data | auto
    返回 finance/web/data/watch/needs_clarify/clarify_question/choices/reason
    """
    q = (question or '').strip()
    hist_lines = []
    for m in (history or [])[-6:]:
        role = '用户' if m.get('role') == 'user' else '助手'
        hist_lines.append(f"{role}: {(m.get('content') or '')[:280]}")
    history_block = '\n'.join(hist_lines) if hist_lines else '（无）'

    if mode == 'data':
        mode_rules = (
            '当前锁定「本地」。区分「查数」与「做事」：\n'
            '【查数】客户意向/阶段/作品/视频/线索列表 → data=true，ops=false\n'
            '【做事】线索转客户、跟进客户、改意向/阶段、建提醒、建客户、'
            '生成文案、热点出文案、出片、创建/准备发布、同步工作台、日更、建定时、'
            '股票筛选、加自选、刷新自选、股票复盘 → '
            'ops=true，data=false（交给运营工具真正执行，禁止只查库假装完成）\n'
            '客户真实字段：intention=low/medium/high；lifecycle_stage=new/appointment/tracking/proposal/deal/aftercare\n'
            '禁止发明「潜在客户/合作客户」等库里不存在的分类去追问。\n'
            '- 能查就查：data=true，needs_clarify=false\n'
            '- 要做事：ops=true；若范围不清再由运营工具澄清\n'
            '- needs_clarify 仅当完全不知道是查客户还是作品等业务大类\n'
            '- finance/web 必须为 false'
        )
        fallback = {
            'finance': False, 'web': False, 'data': True, 'watch': False,
            'ops': False,
            'needs_clarify': False, 'clarify_question': '', 'choices': [],
            'reason': '本地库默认查询',
        }
    elif mode == 'web':
        mode_rules = (
            '当前锁定「联网」：\n'
            f'- {_FINANCE_TOOL_HINT}\n'
            '- finance=true：用户明确要资金流/北向南向/行业净流入等实时行情类数据\n'
            '- web=true：政策、监管、新闻、一般检索、或需要综合公开网页的问题\n'
            '- 可同时 true（例如既问资金又问配套新闻），按语义决定，不要因为出现「A股」就默认开 finance\n'
            '- needs_clarify 仅用于「完全看不出领域」的过宽问题（如只说「最近有什么政策」）；'
            '若用户已点明领域（如央行/证监会政策、某平台规则、某只股票），直接选工具，禁止再追问\n'
            '- 澄清时按用户原话动态生成 3～4 个具体方向选项，finance/web=false\n'
            '- data 必须为 false'
        )
        fallback = {
            'finance': False, 'web': True, 'data': False, 'watch': False,
            'ops': False,
            'needs_clarify': False, 'clarify_question': '', 'choices': [],
            'reason': '联网默认检索',
        }
    else:  # auto
        mode_rules = (
            '当前为智能模式（非锁定数据源）：\n'
            f'- {_FINANCE_TOOL_HINT}\n'
            '- 按语义决定 finance / web / data / watch / ops，可多选\n'
            '- 线索转客户、跟进、改客户、建提醒、文案/出片/发布、股票筛选/自选、同步工作台、日更等写操作 → ops=true\n'
            '- 不要因为出现「A股」「股市」就默认 finance；政策新闻应 web\n'
            '- needs_clarify 仅当完全看不出领域；已点明领域则直接选工具'
        )
        fallback = {
            'finance': False, 'web': False, 'data': False, 'watch': False,
            'ops': False,
            'needs_clarify': False, 'clarify_question': '', 'choices': [],
            'reason': '未识别到需额外取数工具',
        }

    system = (
        '你是智仔的意图路由。根据用户问题语义选择工具，禁止用关键词机械匹配。'
        '只输出 JSON，不要解释。'
    )
    prompt = (
        f'{mode_rules}\n\n'
        '输出 JSON 字段：\n'
        '{"finance":bool,"web":bool,"data":bool,"watch":bool,"ops":bool,'
        '"needs_clarify":bool,"clarify_question":"...",'
        '"choices":[{"label":"...","message":"..."}],'
        '"reason":"一句话理由"}\n\n'
        f'对话历史：\n{history_block}\n\n'
        f'用户问题：{q}\n'
    )
    try:
        content, _tok, _model = call_llm(
            prompt, system_prompt=system, temperature=0.1, max_tokens=500,
        )
    except Exception as e:
        fallback = {**fallback, 'reason': f'意图路由暂不可用，已用保守默认（{e}）'}
        return fallback

    data = _parse_route_json(content or '')
    if not data:
        return fallback

    choices = _normalize_choices(data.get('choices'))
    needs_clarify = bool(data.get('needs_clarify'))
    if needs_clarify and choices:
        # 语义判定需要引导时，优先澄清，不当场开工具
        data['finance'] = False
        data['web'] = False
        data['data'] = False
        data['watch'] = False
        data['ops'] = False
    elif needs_clarify and not choices:
        needs_clarify = False
        if mode == 'web':
            data['web'] = True
        elif mode == 'data':
            data['data'] = True
    out = {
        'finance': bool(data.get('finance')),
        'web': bool(data.get('web')),
        'data': bool(data.get('data')),
        'watch': bool(data.get('watch')),
        'ops': bool(data.get('ops')),
        'needs_clarify': needs_clarify,
        'clarify_question': str(
            data.get('clarify_question') or data.get('question') or ''
        ).strip(),
        'choices': choices if needs_clarify else [],
        'reason': str(data.get('reason') or '').strip() or fallback['reason'],
    }
    # 模式硬约束（能力边界，不是问题关键词）
    if mode == 'data':
        out['finance'] = False
        out['web'] = False
        if out['ops']:
            out['data'] = False
        elif not out['needs_clarify']:
            out['data'] = True
    elif mode == 'web':
        out['data'] = False
        if not out['needs_clarify'] and not out['finance'] and not out['web'] and not out['ops']:
            out['web'] = True
    if out['needs_clarify'] and not out['clarify_question']:
        out['clarify_question'] = (
            '这个问题有点宽，我怕找偏。你更关心哪一类？点选项或补充一句具体方向。'
        )
    return out


def _resolve_intents(question: str, mode: str) -> dict[str, bool]:
    """根据问题与模式决定启用哪些工具 / 检索源。运营动作由 LLM 路由，不在此用关键词硬判。"""
    q = question or ''
    write = _has_any(q, _CONTENT_WRITE_KEYS)
    insurance = _has_any(q, _INSURANCE_KEYS) or mode == 'knowledge'
    watch = _has_any(q, _WATCHLIST_KEYS)
    # finance：stock 模式必开；web/data/auto 的资金类由 plan_source_route 语义决定
    finance = mode == 'stock'

    if mode == 'script':
        return {
            'write': True,
            'insurance': insurance or write,
            'finance': False,
            'watch': False,
            'ops': False,
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
            'ops': False,
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
            'ops': False,
            'vector_knowledge': False,
            'vector_script': False,
            'vector_brief': True,
        }

    if mode == 'ops':
        return {
            'write': False,
            'insurance': False,
            'finance': False,
            'watch': False,
            'ops': True,
            'vector_knowledge': False,
            'vector_script': False,
            'vector_brief': False,
        }

    if mode == 'data':
        # 占位：具体是否查询 / 澄清由 plan_source_route 语义决定
        return {
            'write': False,
            'insurance': False,
            'finance': False,
            'watch': False,
            'ops': False,
            'data': True,
            'web': False,
            'vector_knowledge': False,
            'vector_script': False,
            'vector_brief': False,
        }

    if mode == 'web':
        # 占位：finance/web/澄清由 plan_source_route 语义决定
        return {
            'write': False,
            'insurance': False,
            'finance': False,
            'watch': False,
            'ops': False,
            'data': False,
            'web': True,
            'vector_knowledge': False,
            'vector_script': False,
            'vector_brief': False,
        }

    # auto：运营工具是否执行由 try_run_ops(LLM) 决定；资金/联网由后续语义路由补齐
    data = _has_any(q, _DATA_KEYS)
    web = _has_any(q, _WEB_KEYS)
    if write and not finance:
        finance = False
    if write and _has_any(q, _INSURANCE_KEYS):
        insurance = True
    if '知识库' in q and not finance:
        insurance = insurance or _has_any(q, _INSURANCE_KEYS)

    no_v = not (data or web)
    return {
        'write': write,
        'insurance': insurance,
        'finance': finance,
        'watch': watch,
        'ops': mode in ('auto', 'ops'),
        'data': data,
        'web': web,
        'vector_knowledge': no_v and ((not finance) or insurance or write or (not finance and not watch)),
        'vector_script': no_v and (write or insurance or (not finance and not watch)),
        'vector_brief': no_v and (finance and not write),
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
        if mode == 'ops':
            sources = []
        elif intents.get('finance') or intents.get('watch'):
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
    if intents.get('ops'):
        reasons.append('运营操作')
    if intents.get('write'):
        reasons.append('内容创作')
    if intents.get('data'):
        reasons.append('本地库查询')
    if intents.get('web'):
        reasons.append('联网读取')
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
    source: str | None = None,
    history: list[dict] | None = None,
) -> dict[str, Any]:
    q = (question or '').strip()
    mode = mode if mode in MODE_SOURCES else 'auto'
    # 数据源开关优先：命中 data/web 时强制锁定数据源；否则回落到角色 mode 原逻辑
    effective_mode = (
        source if source in ('data', 'web') else (mode if mode in MODE_SOURCES else 'auto')
    )
    steps: list[dict] = []
    cites: list[dict] = []

    if not q:
        return {
            'answer': '请先输入问题。',
            'steps': [_step('空问题，已跳过')],
            'cites': [],
            'mode': effective_mode,
        }

    mode_label = {
        'auto': '智能 Agent',
        'knowledge': '偏知识库',
        'script': '偏文案',
        'stock': '偏股票',
        'ops': '偏运营',
        'data': '偏本地库查询',
        'web': '偏联网读取',
    }.get(effective_mode, effective_mode)
    steps.append(_step(f'理解问题 · 模式「{mode_label}」'))

    intents = _resolve_intents(q, effective_mode)
    sources, route_reason = _resolve_sources(intents, effective_mode)
    steps.append(_step(f'路由 · {route_reason}'))

    hits: list[dict] = []
    tool_blocks: list[str] = []
    ops_ran = False
    choices: list[dict] = []
    clarify_only = False

    # —— 本地/联网：语义路由（不写死关键词）→ 必要时澄清 → 再选工具 ——
    if effective_mode in ('data', 'web'):
        try:
            route = plan_source_route(q, effective_mode, history=history)
            reason = route.get('reason') or '语义路由'
            steps.append(_step(f'意图理解 · {reason}'))
            if route.get('needs_clarify') and route.get('choices'):
                steps.append(_step('澄清 · 问题较宽，先请你选方向'))
                return {
                    'answer': route.get('clarify_question')
                    or '这个问题有点宽，我怕找偏。你更关心哪一类？',
                    'steps': steps,
                    'cites': [],
                    'mode': effective_mode,
                    'choices': route.get('choices') or [],
                }
            intents['ops'] = bool(route.get('ops'))
            intents['finance'] = bool(route.get('finance'))
            intents['web'] = bool(route.get('web')) if effective_mode == 'web' else False
            intents['data'] = bool(route.get('data')) if effective_mode == 'data' else False
            intents['watch'] = bool(route.get('watch'))
            if intents['ops']:
                # 写操作优先，避免只查库假装完成
                intents['data'] = False
            if effective_mode == 'web' and not intents['finance'] and not intents['web'] and not intents['ops']:
                intents['web'] = True
            if effective_mode == 'data' and not intents['data'] and not intents['ops']:
                intents['data'] = True
        except Exception as e:
            steps.append(_step(f'意图理解失败，已用保守默认：{e}'))

    # —— 运营操作（含本地模式下的线索转客户等写操作）——
    run_ops = bool(intents.get('ops')) and not (
        intents.get('data') or intents.get('web')
    )
    # 本地/联网锁定时：仅当语义路由显式标记 ops 才执行
    if effective_mode in ('data', 'web'):
        run_ops = bool(intents.get('ops'))
    elif effective_mode == 'auto':
        run_ops = bool(intents.get('ops')) and not (intents.get('data') or intents.get('web'))
    elif effective_mode == 'ops':
        run_ops = True

    if run_ops:
        try:
            ops_result = try_run_ops(
                q,
                history=history,
                force=(effective_mode == 'ops' or effective_mode == 'data'),
            )
            if ops_result:
                c = ops_result.get('cites') or []
                text = ops_result.get('text') or ''
                step_label = ops_result.get('step') or '运营工具'
                choices = list(ops_result.get('choices') or [])
                clarify_only = bool(ops_result.get('clarify'))
                steps.append(_step(step_label))
                cites.extend(c)
                tool_blocks.append(text)
                ops_ran = True
                intents['finance'] = False
                intents['watch'] = False
                intents['insurance'] = False
                intents['data'] = False
                intents['web'] = False
                intents['vector_knowledge'] = False
                intents['vector_script'] = False
                intents['vector_brief'] = False
                sources = []
            elif effective_mode == 'ops':
                steps.append(_step('运营路由 · 未匹配到可执行工具'))
            else:
                steps.append(_step('运营路由 · 未匹配到可执行工具'))
                # 本地模式写操作失败时，不要默默改回去只查库糊弄用户
                if effective_mode == 'data' and intents.get('ops'):
                    tool_blocks.append(
                        '没能执行该操作。你可以换种说法，例如「把线索池里待转化的线索全部转成客户」。'
                    )
                    ops_ran = True
                    intents['data'] = False
        except Exception as e:
            steps.append(_step(f'运营工具失败：{e}'))
            tool_blocks.append(f'运营操作失败：{e}')
            if effective_mode == 'data' and intents.get('ops'):
                ops_ran = True
                intents['data'] = False

    # auto：运营未接手时，再用语义决定是否走行情/联网（避免「A股政策」误开北向）
    if effective_mode == 'auto' and not ops_ran and not clarify_only:
        try:
            route = plan_source_route(q, 'auto', history=history)
            if route.get('reason'):
                steps.append(_step(f'意图理解 · {route["reason"]}'))
            if route.get('needs_clarify') and route.get('choices'):
                steps.append(_step('澄清 · 问题较宽，先请你选方向'))
                return {
                    'answer': route.get('clarify_question')
                    or '这个问题有点宽，我怕找偏。你更关心哪一类？',
                    'steps': steps,
                    'cites': [],
                    'mode': effective_mode,
                    'choices': route.get('choices') or [],
                }
            intents['finance'] = bool(route.get('finance'))
            if route.get('web'):
                intents['web'] = True
            if route.get('data'):
                intents['data'] = True
            if route.get('watch'):
                intents['watch'] = True
            if route.get('ops') and not ops_ran:
                intents['ops'] = True
                # 稍后不会再跑 ops（已过 ops 段）；若 auto 路由说 ops，补跑一次
                try:
                    ops_result = try_run_ops(q, history=history, force=False)
                    if ops_result:
                        cites.extend(ops_result.get('cites') or [])
                        tool_blocks.append(ops_result.get('text') or '')
                        choices = list(ops_result.get('choices') or [])
                        clarify_only = bool(ops_result.get('clarify'))
                        steps.append(_step(ops_result.get('step') or '运营工具'))
                        ops_ran = True
                        intents['data'] = False
                        intents['web'] = False
                        intents['finance'] = False
                        sources = []
                except Exception as e:
                    steps.append(_step(f'运营补跑失败：{e}'))
            intents['vector_brief'] = bool(intents.get('finance') and not intents.get('write'))
        except Exception as e:
            steps.append(_step(f'意图理解跳过：{e}'))

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

    if intents.get('data'):
        steps.append(_step('工具调用 · 本地库查询（按意图生成只读 SQL）'))
        try:
            c, text = tool_query_database(q, history=history)
            cites.extend(c)
            tool_blocks.append(text)
        except Exception as e:
            tool_blocks.append(f'本地库查询失败：{e}')

    if intents.get('web'):
        steps.append(_step('工具调用 · 联网读取（搜索/抓网页）'))
        try:
            c, text = web_search(q, history=history)
            cites.extend(c)
            tool_blocks.append(text)
        except Exception as e:
            tool_blocks.append(f'联网读取失败：{e}')

    # —— 向量检索 ——
    skip_vector = bool(
        ops_ran
        or (intents.get('insurance') and not intents.get('write') and not intents.get('finance'))
    )
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
            min_score = 0.35
        hits = search_vectors(q, source_types=sources, top_k=5, min_score=min_score)
        for h in hits:
            cites.append(_cite_from_hit(h))
    elif skip_vector and ops_ran:
        steps.append(_step('向量检索 · 运营指令已由工具处理，跳过'))
    elif skip_vector:
        steps.append(_step('向量检索 · 已由保险工具覆盖，跳过重复召回'))

    if effective_mode == 'auto' and not hits and not tool_blocks:
        steps.append(_step('放宽检索 · 知识库/文案'))
        hits = search_vectors(q, source_types=['knowledge', 'script'], top_k=6, min_score=0.18)
        for h in hits:
            cites.append(_cite_from_hit(h))

    steps.append(_step('汇总并标注引用'))

    def _uniq_cites(items: list[dict]) -> list[dict]:
        out: list[dict] = []
        seen: set[tuple] = set()
        for c in items:
            key = (c.get('source_type'), c.get('source_id'), c.get('title'))
            if key in seen:
                continue
            seen.add(key)
            out.append(c)
        return out[:10]

    # 澄清选项：直接返回引导文案，避免二次改写冲掉选项
    # 但一旦命中「本地库查询/联网读取」意图，不要让运营澄清短路掉数据/联网结果
    if clarify_only and tool_blocks and not (intents.get('data') or intents.get('web')):
        return {
            'answer': tool_blocks[0],
            'steps': steps,
            'cites': _uniq_cites(cites),
            'mode': effective_mode,
            'choices': choices,
        }

    context = _build_context(hits, tool_blocks)
    hist_lines = []
    for m in (history or [])[-6:]:
        role = '用户' if m.get('role') == 'user' else '助手'
        hist_lines.append(f"{role}: {(m.get('content') or '')[:400]}")
    history_block = '\n'.join(hist_lines) if hist_lines else '（无）'

    has_refs = bool(hits) or bool(tool_blocks)
    system_prompt = (
        '你是「智仔」，智能运营台的运营总控助手。'
        '核心工作方式：理解问题 → 依据【系统工具结果】取数 → 分析总结后回答。'
        '优先使用工具结果；工具已执行的操作要如实告知，不要装作还没做。'
        '意图不清时会先给选项请用户确认；不要替用户瞎猜。'
        '「全网热点/热搜」与「自己账号的作品数据」是两件事，回答时不要混淆。'
        '涉及出片/日更等写操作时，以工具返回为准；不要编造任务 ID。'
        '发布默认半自动（准备发布），提醒用户在官方页确认发表。'
        '不要在正文里罗列引用清单；系统会单独展示引用卡片。'
        '涉及股票时声明不构成投资建议；涉及保险时声明不构成销售误导。'
        '数据库查询绝不写库；引用必须真实可溯。不要写「理解：」这类元描述。不要输出 JSON。'
    )

    if effective_mode == 'data':
        system_prompt += (
            '\n\n【模式锁定·本地库】只使用本地业务数据库查询结果。'
            '流程：根据用户问题理解查哪类业务数据 → 工具已选出表并查出结果 → 你做分析总结再回答。'
            '回答结构：①一句话结论；②用查询结果中的关键数字/名单作依据（可摘要，不必全文粘贴表格）；'
            '③一两句业务解读或下一步建议（仅基于已查到的数据）。'
            '开头用一句话点明「以下基于本地数据库（只读）」。'
            '结果为空时：说明本地库没有匹配数据；若工具提示可切联网，可简短告知；'
            '不要编造行数据，不要改写成网页搜索，不要反问无关的政策/新闻类问题。'
        )
    elif effective_mode == 'web':
        system_prompt += (
            '\n\n【模式锁定·联网】只使用联网检索与/或金融实时快照等在线数据源。'
            '流程：取数 → 筛选相关信息 → 分析总结后回答（严禁把检索列表原文堆给用户）。'
            '回答结构：①一句话结论；②2～5 句分析（综合多条来源的共同点与差异）；③免责声明（若涉行情）。'
            '若有「金融/股票实时快照」且问题是资金流/北向：优先据此作答；'
            '若问题是政策/新闻/监管：只依据网页检索归纳，不要扯北向净买额。'
            '工具写明「未披露」时说「公开渠道暂未披露」，严禁说成「关闭 / 外资没动作 / 净流入 0」。'
            '正文不要粘贴超长网址或「详见下方引用」编号列表；系统会单独展示引用卡片。'
            '若只有网页且资料偏旧或无关：明确说未找到可用的今日信息，不要用无关文章硬凑。'
            '严禁改写成本地库查询、严禁写「理解：」。'
        )
    else:
        system_prompt += (
            '\n\n通用取数规则：'
            '有金融实时快照时优先据此分析北向/资金流；'
            '有本地数据库结果时基于库表数据作答并标明来源；'
            '有联网检索时归纳后作答，不要堆列表；'
            '无数据时如实说明，不要编造。'
        )

    ref_hint = (
        '若确实使用了相关资料或工具，文末只需一句「详见下方引用」。'
        if has_refs else
        '当前没有可用相关资料，请如实说明，不要编造。'
    )
    analysis_hint = (
        '\n请输出「分析总结后的答案」：先结论、后依据与解读；'
        '不要粘贴工具原文表格或网页检索列表。'
    )
    prompt = (
        f'对话历史：\n{history_block}\n\n'
        f'用户问题：{q}\n\n'
        f'检索到的资料与工具结果：\n{context}\n\n'
        f'{ref_hint}{analysis_hint}'
    )
    if effective_mode == 'data':
        prompt += (
            '\n\n（已锁定「本地库」：只依据数据库查询结果分析总结作答；'
            '不要追问、不要联想网页、不要写「理解：」。）'
        )
    elif effective_mode == 'web':
        prompt += (
            '\n\n（已锁定「联网」：只依据在线工具/检索结果分析总结作答；'
            '不要追问、不要改查本地库、不要写「理解：」。）'
        )

    try:
        answer, _tokens, _model = call_llm(
            prompt,
            system_prompt=system_prompt,
            # 锁模式降低随机性，避免模型自由发挥成网页式追问
            temperature=0.2 if effective_mode in ('data', 'web') else 0.35,
            max_tokens=1200,
        )
        answer = (answer or '').strip()
        # 锁模式安全兜底：清掉「理解：」式元描述前缀
        if effective_mode in ('data', 'web'):
            answer = re.sub(r'^[（(]?\s*理解[：:][^）)]*[）)]?\s*', '', answer, flags=re.S).strip()
            answer = re.sub(r'^理解[：:][^\n]*\n?', '', answer, flags=re.S).strip()
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

    return {
        'answer': answer,
        'steps': steps,
        'cites': _uniq_cites(cites),
        'mode': effective_mode,
        'choices': choices,
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


def list_sessions(limit: int = 30) -> list[dict]:
    conn = get_db()
    try:
        rows = conn.execute(
            '''SELECT s.id, s.title, s.created_at, s.updated_at,
                      (SELECT COUNT(*) FROM pet_chat_message m WHERE m.session_id=s.id) AS msg_count,
                      (SELECT content FROM pet_chat_message m
                       WHERE m.session_id=s.id AND m.role='user'
                       ORDER BY m.id DESC LIMIT 1) AS last_user
               FROM pet_chat_session s
               ORDER BY s.updated_at DESC NULLS LAST, s.id DESC
               LIMIT %s''',
            (limit,),
        ).fetchall()
        out = []
        for r in rows:
            out.append({
                'id': r['id'],
                'title': (r['title'] or '智仔对话')[:60],
                'created_at': str(r['created_at'] or ''),
                'updated_at': str(r['updated_at'] or ''),
                'msg_count': int(r['msg_count'] or 0),
                'preview': ((r['last_user'] or r['title'] or '')[:48]),
            })
        return out
    finally:
        conn.close()


def load_session_messages(session_id: int, limit: int = 100) -> list[dict]:
    """返回前端可用的消息列表（含 meta）。"""
    conn = get_db()
    try:
        rows = conn.execute(
            '''SELECT id, role, content, meta_json, created_at
               FROM pet_chat_message
               WHERE session_id=%s
               ORDER BY id ASC
               LIMIT %s''',
            (session_id, limit),
        ).fetchall()
        messages = []
        for r in rows:
            meta = {}
            raw = r.get('meta_json') or ''
            if raw:
                try:
                    meta = json.loads(raw) if isinstance(raw, str) else (raw or {})
                except Exception:
                    meta = {}
            role = r['role']
            ui_role = 'user' if role == 'user' else 'bot'
            messages.append({
                'id': f"db-{r['id']}",
                'role': ui_role,
                'content': r['content'] or '',
                'steps': meta.get('steps') or [],
                'cites': meta.get('cites') or [],
                'choices': meta.get('choices') or [],
                'created_at': str(r.get('created_at') or ''),
            })
        return messages
    finally:
        conn.close()


def session_exists(session_id: int) -> bool:
    conn = get_db()
    try:
        row = conn.execute(
            'SELECT id FROM pet_chat_session WHERE id=%s', (session_id,)
        ).fetchone()
        return bool(row)
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


def load_history(session_id: int, limit: int = 20) -> list[dict]:
    conn = get_db()
    try:
        rows = conn.execute(
            '''SELECT role, content, meta_json FROM pet_chat_message
               WHERE session_id=%s
               ORDER BY id DESC LIMIT %s''',
            (session_id, limit),
        ).fetchall()
        out = []
        for r in reversed(list(rows)):
            meta = {}
            raw = r.get('meta_json') or ''
            if raw:
                try:
                    meta = json.loads(raw) if isinstance(raw, str) else (raw or {})
                except Exception:
                    meta = {}
            out.append({
                'role': r['role'],
                'content': r['content'],
                'meta': meta,
            })
        return out
    finally:
        conn.close()
