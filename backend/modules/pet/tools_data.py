# -*- coding: utf-8 -*-
"""智仔工具 · 本地库任意表查询（不联网 · Text-to-SQL 只读）。

把用户自然语言意图转成**只读 SELECT**，安全查询本地 PostgreSQL 业务表，
并按业务含义映射帮助模型对准正确的表。

安全底线（务必守住）：
- 只允许 SELECT / 只读 CTE(WITH)，禁止任何写/管理语句；
- 只允许查询白名单业务表，禁止碰 information_schema / pg_* / rag_chunk 等系统/向量表；
- 双保险：正则预校验 + psycopg2 readonly 事务；
- 强制 LIMIT≤200；敏感字段（phone/wechat）默认脱敏。
"""

from __future__ import annotations

import json
import re
from typing import Any

from config import get_db, get_setting, PG_HOST, PG_PORT, PG_DBNAME, PG_USER, PG_PASSWORD
from modules.ai.writer import call_llm

import psycopg2
import psycopg2.extras as _pg_extras

# ---- 允许查询的业务表白名单（系统/向量表一律不在内）----
ALLOWED_TABLES = {
    'customer', 'lead', 'follow_record', 'reminder',
    'publish_task', 'video_task', 'script',
    'hot_topic', 'knowledge_item',
    'stock_watchlist', 'stock_universe', 'stock_daily_briefing',
    'workflow', 'ai_agent',
    'ops_platform', 'pet_job',
    'system_setting',
    'customer_analysis', 'stock_strategy', 'stock_screening', 'stock_review',
}

# 表业务含义：专门帮模型把人话映射到正确的表
TABLE_MEANINGS = {
    'customer': '客户（昵称nickname/微信wechat/电话phone/意向intention/阶段lifecycle_stage/地区region/备注remark/来源source_channel）',
    'lead': '线索（进线未转客户；昵称nickname/电话phone/微信wechat/来源source/状态status）',
    'follow_record': '客户跟进记录（customer_id/内容content/方式method/下次时间next_time）',
    'reminder': '提醒（客户customer_id/类型type/标题title/内容content/状态status）',
    'publish_task': '发布任务（标题title/平台platform/状态status/播放plays/赞likes/评comments/收藏favorites/转发shares/发布时间published_at）',
    'video_task': '视频生产任务（标题title/配音voice_status/字幕subtitle_status/合成export_status/时长duration）',
    'script': '文案库（标题title/正文content/类型content_type/状态status/标签tags）',
    'hot_topic': '全网热点（平台platform/标题title/点赞likes/评论comments/热度ai_score）',
    'knowledge_item': '知识库条目（标题title/正文content/分类category/标签tags）',
    'stock_watchlist': '自选/持仓股（代码stock_code/名称stock_name/类型list_type/成本价buy_price/现价current_price/目标价target_price）',
    'stock_universe': '全市场 A 股快照（代码code/名称name/现价price/涨跌幅pct_chg/行业board）',
    'stock_daily_briefing': '股票每日简报（日期brief_date/新闻news_json/简报brief_md）',
    'workflow': '工作流（名称name/类型workflow_type/步骤steps_json/状态status）',
    'ai_agent': 'AI 助手配置（名称name/类型agent_type/系统提示词system_prompt/状态status）',
    'ops_platform': '平台配置（key/标签label/是否启用采集enable_collector/是否启用发布enable_publish）',
    'pet_job': '智仔定时任务（标题title/动作action/启用enabled/小时hour/间隔interval_hours）',
    'system_setting': '系统设置（分类category/键key/值value/标签label）',
    'customer_analysis': '客户 AI 分析（成交概率deal_probability/关注点focus_points/推荐产品recommended_products）',
    'stock_strategy': '股票策略（名称name/类型strategy_type/规则rules_json/胜率hit_rate）',
    'stock_screening': '股票筛选结果（名称name/条件conditions_json/结果results_json/状态status）',
    'stock_review': '股票复盘（标题title/输入input_text/摘要summary/结果result_json）',
}

# 默认脱敏的敏感列
SENSITIVE_COLUMNS = {'phone', 'wechat', 'mobile', 'contact_phone', 'wechat_id'}

# 业务枚举（与前端 CRM 一致；禁止臆造 mid/潜在客户 等不存在的取值）
ENUM_HINTS = (
    'customer.intention 取值（英文存库）：低意向=low / 中意向=medium / 高意向=high；'
    '「中高意向」= intention IN (\'medium\',\'high\')；'
    '「有没有中意向客户」必须 WHERE intention=\'medium\'，禁止写 mid、禁止写中文“中意向”。'
    'customer.lifecycle_stage：new(新增客户)/appointment(约访)/tracking(跟踪中)/'
    'proposal(方案沟通)/deal(成交)/aftercare(售后维护)；'
    '不要把「潜在客户/合作客户/意向客户」当成库字段——那是口语，应映射到 intention 或 lifecycle_stage；'
    'publish_task.status：pending/scheduled/done/failed；'
    'publish_task.platform：douyin/xiaohongshu/shipinhao；'
    'lead.status：pending_contact(待首联)/following(跟进中)/converted(已转化)/invalid(无效)。'
)


def _cite(title: str, table: str, snippet: str = '', meta: str = '') -> dict:
    return {
        'score': '工具',
        'title': title,
        'meta': meta or f'来源：本地数据库 · {table}',
        'source_type': 'data',
        'source_id': 0,
        'path': '/',
        'snippet': (snippet or '')[:220],
    }


def get_schema_catalog() -> str:
    """从 information_schema 动态读取白名单表的字段，叠加业务含义。"""
    conn = get_db()
    try:
        rows = conn.execute(
            '''SELECT table_name, column_name, data_type
               FROM information_schema.columns
               WHERE table_name = ANY(%s)
               ORDER BY table_name, ordinal_position''',
            (list(ALLOWED_TABLES),),
        ).fetchall()
        # 注入客户意向真实分布，避免模型用错枚举（如 mid）
        intent_dist = []
        try:
            for r in conn.execute(
                'SELECT intention, COUNT(*) AS n FROM customer GROUP BY intention ORDER BY n DESC'
            ).fetchall():
                intent_dist.append(f"{r['intention'] or '(空)'}:{r['n']}")
        except Exception:
            pass
    finally:
        conn.close()

    by_table: dict[str, list[str]] = {}
    for r in rows:
        t = r['table_name']
        col = f"{r['column_name']}({r['data_type']})"
        by_table.setdefault(t, []).append(col)

    lines = []
    for t in sorted(ALLOWED_TABLES):
        cols = by_table.get(t)
        if not cols:
            lines.append(f"- {t}：{TABLE_MEANINGS.get(t, '')}（字段待建）")
            continue
        lines.append(f"- {t}：{TABLE_MEANINGS.get(t, '')}")
        lines.append(f"    字段：{', '.join(cols)}")
    if intent_dist:
        lines.append(
            f"- 【当前库 customer.intention 实况】{'、'.join(intent_dist)}；"
            '筛选时必须用这些英文值（中意向=medium，不是 mid）'
        )
    return '\n'.join(lines)


def _extract_tables(sql: str) -> set[str]:
    low = sql.lower()
    found = set(re.findall(r'(?:from|join)\s+(?:public\.)?([a-zA-Z_][\w]*)', low))
    return found


def _extract_cte_names(sql: str) -> set[str]:
    """提取 WITH 子句里定义的 CTE 别名，避免被当成非法表拦截。"""
    low = sql.lower().strip()
    m = re.match(r'\s*with\s+(.*)', low, re.S)
    if not m:
        return set()
    rest = m.group(1)
    # CTE 列表结束于第一个顶层（不在括号内）的 SELECT
    depth = 0
    idx = None
    for i, ch in enumerate(rest):
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        elif depth == 0 and rest[i:i + 7] == ' select':
            idx = i
            break
    cte_body = rest[:idx] if idx is not None else rest
    return set(re.findall(r'([a-zA-Z_]\w*)\s+as\s*\(', cte_body))


def generate_sql(question: str, history: list[dict] | None = None) -> dict:
    """让 LLM 把自然语言转成只读 SELECT，返回 {'sql':..., 'thought':...}。"""
    catalog = get_schema_catalog()
    hist_lines = []
    for m in (history or [])[-6:]:
        role = '用户' if m.get('role') == 'user' else '助手'
        hist_lines.append(f"{role}: {(m.get('content') or '')[:300]}")
    history_block = '\n'.join(hist_lines) if hist_lines else '（无）'

    system = (
        '你是一个 PostgreSQL 查询生成器。根据用户自然语言问题，先判断该查哪张（或哪几张）业务表，'
        '再生成一条只读 SELECT。\n'
        '选表思路（必须先想清楚再写 SQL）：\n'
        '- 客户/意向/阶段/地区 → customer；线索进线 → lead；跟进/提醒 → follow_record / reminder\n'
        '- 作品播放赞评转藏/发布状态 → publish_task；视频制作进度 → video_task；口播文案 → script\n'
        '- 热点榜 → hot_topic；知识条目 → knowledge_item\n'
        '- 自选持仓 → stock_watchlist；A 股快照涨跌 → stock_universe；股票简报 → stock_daily_briefing\n'
        '- 策略/筛选/复盘 → stock_strategy / stock_screening / stock_review\n'
        '- 工作流/助手/平台/定时任务/设置 → workflow / ai_agent / ops_platform / pet_job / system_setting\n'
        '硬性规则：\n'
        '1) 只能 SELECT；禁止 INSERT/UPDATE/DELETE/DROP/ALTER/TRUNCATE 等任何写或管理操作。\n'
        '2) 只能查询下面列出的业务表；禁止查 information_schema、pg_*、rag_chunk 等系统/向量表。\n'
        '3) 必须带 LIMIT（默认 50，最大 200）；聚合统计（COUNT/SUM/AVG）也建议 LIMIT 或只返回单行。\n'
        '4) 表/字段名必须与 schema 完全一致（小写）。多轮里“这些客户/上面那些”指上一轮同一批客户（复用相同过滤）。\n'
        '5) 时间字段多为 TEXT（如 created_at 形如 2026-08-13 10:00:00），按文本比较或用 created_at::date。\n'
        '6) 只输出 JSON：{"sql":"...","thought":"选了哪张表+为何"}，不要解释。\n'
        '7) 本地库是业务数据库。北向资金、实时北向净买额、今日全市场涨跌榜以外的实时新闻/政策/天气等'
        '本地库明显没有的数据，返回 {"sql":"","thought":"本地库无此数据，建议用户切到联网模式"}，'
        '不要硬查任何表。注意：stock_universe 有本地快照现价/涨跌幅，可回答「库里股票涨跌」类问题；'
        'publish_task 可回答「我账号作品数据」。\n'
        f'业务枚举提示：{ENUM_HINTS}'
    )
    prompt = (
        f'可用业务表与字段（请从中选择最贴合用户问题的表）：\n{catalog}\n\n'
        f'对话历史：\n{history_block}\n\n'
        f'用户问题：{question}\n\n'
        '请生成 JSON。示例：\n'
        '问：我库里有多少客户、几个高意向？\n'
        '答：{"sql":"SELECT intention, COUNT(*) AS n FROM customer GROUP BY intention LIMIT 50",'
        '"thought":"选 customer，按意向分组统计"}\n'
        '问：客户表里有哪几个高意向客户？\n'
        '答：{"sql":"SELECT id, nickname, intention, phone FROM customer WHERE intention=\'high\' '
        'ORDER BY id LIMIT 50","thought":"选 customer，筛 intention=high"}\n'
        '问：有没有中高意向的客户？\n'
        '答：{"sql":"SELECT id, nickname, intention, phone, lifecycle_stage FROM customer '
        'WHERE intention IN (\'medium\',\'high\') ORDER BY CASE intention WHEN \'high\' THEN 0 ELSE 1 END, id LIMIT 50",'
        '"thought":"中高意向=medium+high"}\n'
        '问：上个月发布的视频里播放最高的是哪条？\n'
        '答：{"sql":"SELECT id,title,platform,plays FROM publish_task WHERE status=\'done\' '
        'ORDER BY plays DESC LIMIT 1","thought":"选 publish_task，已发作品按播放降序"}\n'
        '问：今天北向资金怎么样？\n'
        '答：{"sql":"","thought":"本地库无此数据，建议用户切到联网模式"}'
    )
    try:
        content, _tok, _model = call_llm(
            prompt, system_prompt=system, temperature=0.1, max_tokens=600,
        )
    except Exception as e:
        return {'sql': '', 'thought': f'SQL 生成失败：{e}'}

    raw = (content or '').strip()
    m = re.search(r'\{[\s\S]*\}', raw)
    if not m:
        return {'sql': '', 'thought': '模型未返回 JSON'}
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {'sql': '', 'thought': '模型返回非合法 JSON'}
    sql = (data.get('sql') or '').strip()
    if not sql:
        return {'sql': '', 'thought': data.get('thought') or '未生成 SQL'}
    return {'sql': sql, 'thought': data.get('thought') or ''}


def validate_readonly_sql(sql: str) -> tuple[bool, str]:
    """预校验 SQL：只允许只读 SELECT，且只查白名单表。

    返回 (ok, sql_or_reason)。ok 时第二个元素是可能微调后的 SQL（补 LIMIT/封顶）。
    """
    s = sql.strip()
    if not s:
        return False, '空 SQL。'
    # 去注释
    s_nc = re.sub(r'--[^\n]*', ' ', s)
    s_nc = re.sub(r'/\*.*?\*/', ' ', s_nc, flags=re.S)
    low = s_nc.lower()

    if not (low.startswith('select') or low.startswith('with')):
        return False, '只允许 SELECT 查询（或以 WITH 开头的只读 CTE）。'

    if ';' in s_nc:
        return False, '不允许多条语句或分号（;）。'

    forbidden = [
        'insert', 'update', 'delete', 'drop', 'alter', 'truncate', 'create',
        'replace', 'grant', 'revoke', 'merge', 'call ', 'exec', 'do ', 'lock',
        'unlock', 'rollback', 'commit', 'savepoint', 'set ', 'vacuum', 'reindex',
        'copy ', 'begin', 'transaction', 'explain',
    ]
    for kw in forbidden:
        if re.search(r'\b' + re.escape(kw.strip()) + r'\b', low):
            return False, f'不允许包含写/管理关键字：{kw.strip()}'

    if re.search(r'\binformation_schema\b', low) or re.search(r'\bpg_', low) \
            or re.search(r'\brag_chunk\b', low):
        return False, '不允许查询系统/向量表（information_schema / pg_* / rag_chunk）。'

    tables = _extract_tables(low)
    cte_names = _extract_cte_names(low)
    bad = tables - ALLOWED_TABLES - cte_names
    if bad:
        return False, f'只允许查询白名单业务表，非法表：{", ".join(sorted(bad))}'

    fixed = s.rstrip().rstrip(';').strip()
    if 'limit' not in low:
        fixed = fixed + ' LIMIT 50'
    else:
        m = re.search(r'limit\s+(\d+)', low)
        if m and int(m.group(1)) > 200:
            fixed = re.sub(r'limit\s+\d+', 'LIMIT 200', fixed, flags=re.I)
    return True, fixed


def run_sql_ro(sql: str) -> list[dict]:
    """只读执行 SELECT。

    使用**独立专用只读连接**（独立 psycopg2.connect + set_session(readonly=True)，
    用完真正 close），绝不触碰应用连接池——避免在共享物理连接上留下只读事务，
    否则会污染池中连接导致后续 INSERT 报 ReadOnlySqlTransaction。

    安全双保险：调用方必须先经 validate_readonly_sql 校验，这里再叠加只读事务。
    """
    dsn = (
        f"host={PG_HOST} port={PG_PORT} dbname={PG_DBNAME} "
        f"user={PG_USER} password={PG_PASSWORD}"
    )
    conn = None
    try:
        conn = psycopg2.connect(dsn, connect_timeout=10)
        # 新连接尚无活动事务，set_session(readonly=True) 可安全生效
        conn.set_session(readonly=True)
        cur = conn.cursor(cursor_factory=_pg_extras.RealDictCursor)
        cur.execute(sql)
        rows = cur.fetchall()
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
    return [dict(r) for r in rows]


def _table_columns(table: str) -> list[str]:
    """取白名单表的真实列名（避免列名注入）。"""
    if table not in ALLOWED_TABLES:
        return []
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name=%s "
            "ORDER BY ordinal_position",
            (table,),
        ).fetchall()
    finally:
        conn.close()
    return [r['column_name'] for r in rows]


def _fallback_distribution(sql: str) -> str | None:
    """0 行时，若原 SQL 是单值过滤（col='val'），补一句该列取值分布，帮用户快速定位。

    仅对白名单表 + 真实列名生成 GROUP BY 查询，并再经 validate_readonly_sql 校验。
    """
    low = sql.lower()
    m_tbl = re.search(r'from\s+(?:public\.)?([a-zA-Z_]\w*)', low)
    if not m_tbl:
        return None
    table = m_tbl.group(1)
    if table not in ALLOWED_TABLES:
        return None
    m_eq = re.search(r'([a-zA-Z_]\w*)\s*=\s*\'([^\']*)\'', low)
    if not m_eq:
        return None
    col = m_eq.group(1)
    val = m_eq.group(2)
    cols = _table_columns(table)
    if col not in cols:
        return None
    # 列/表名已校验为真实标识符（仅字母数字下划线），无注入风险
    dist_sql = (
        f'SELECT {col}, COUNT(*) AS n FROM {table} '
        f'GROUP BY {col} ORDER BY n DESC LIMIT 50'
    )
    ok, fixed = validate_readonly_sql(dist_sql)
    if not ok:
        return None
    try:
        rows = run_sql_ro(fixed)
    except Exception:
        return None
    if not rows:
        return None
    parts = []
    for r in rows[:12]:
        cv = r.get(col)
        parts.append(f"{cv}:{r.get('n')}")
    return (
        f"未找到 {col}='{val}' 的记录。库内「{col}」分布：{'、'.join(parts)}。"
    )


def _mask_value(val: str) -> str:
    v = (val or '').strip()
    if not v:
        return v
    if len(v) <= 4:
        return '****'
    if len(v) <= 6:
        return v[0] + '****' + v[-1]
    return v[:3] + '****' + v[-2:]


def _format_rows(rows: list[dict]) -> tuple[list[str], str]:
    if not rows:
        return [], '（查询成功，但没有匹配的数据行。）'
    cols = list(rows[0].keys())
    mask_on = str(get_setting('data', 'mask_sensitive', 'true')).lower() != 'false'
    lines = [' | '.join(cols)]
    shown = rows[:200]
    for r in shown:
        cells = []
        for c in cols:
            v = r.get(c)
            v = '' if v is None else str(v)
            if mask_on and str(c).lower() in SENSITIVE_COLUMNS:
                v = _mask_value(v)
            cells.append(v)
        lines.append(' | '.join(cells))
    body = '\n'.join(lines)
    if len(rows) > 200:
        body += f'\n\n（仅展示前 200 / 共 {len(rows)} 行；结果已截断）'
    return cols, body


def tool_query_database(question: str, history: list[dict] | None = None) -> tuple[list[dict], str]:
    """编排：开关 → schema → 生成 SQL → 校验 → 只读执行 → 格式化 + 引用。"""
    enabled = str(get_setting('data', 'query_enabled', 'true')).lower() != 'false'
    if not enabled:
        return [], '本地库自然语言查询已关闭（data.query_enabled=false），可在系统设置中开启。'

    gen = generate_sql(question, history=history)
    sql = gen.get('sql') or ''
    if not sql:
        thought = gen.get('thought') or ''
        if any(k in thought for k in ('联网', '本地库无', '无此数据', '建议', '不在')):
            return (
                [_cite('本地库查询', 'database', thought)],
                '本地数据库中没有匹配的数据（北向资金、实时行情等不在本地业务库）。'
                '请打开输入框右侧的「联网」开关，重新提问即可联网查询。',
            )
        return (
            [_cite('本地库查询', 'database', thought)],
            '我没能把这个问题转成安全的查询语句。换个说法试试，例如：'
            '「客户表里有几个高意向」「上个月发布的视频播放最高的是哪条」「库存里有多少条线索」。',
        )

    ok, payload = validate_readonly_sql(sql)
    if not ok:
        return (
            [_cite('本地库查询', 'database', payload)],
            f'这条查询被安全规则拦下了：{payload}\n你可以换种说法，例如用更明确的数据表/字段描述。',
        )

    try:
        rows = run_sql_ro(payload)
    except Exception as e:
        return (
            [_cite('本地库查询', 'database', str(e)[:120])],
            f'查询本地数据库失败：{e}\n（可能表/字段名与数据库不一致，或查询超时。）',
        )

    tables = _extract_tables(payload)
    primary = sorted(tables)[0] if tables else 'database'
    cols, body = _format_rows(rows)
    thought = (gen.get('thought') or '').strip()

    cite = _cite(
        f'本地库查询 · {primary}',
        primary,
        f'来源：本地数据库 · {primary} · {len(rows)} 行',
        meta=f'来源：本地数据库 · {primary} · {len(rows)} 行',
    )
    header = (
        f'【本地数据库查询结果】表={primary} · {len(rows)} 行'
        + (f' · 选表理由：{thought}' if thought else '')
        + '\n'
        '（以下为原始查询结果，供上层分析总结；回答时请归纳，勿整表粘贴。）\n\n'
    )
    body = header + body
    body += f'\n\n（来源：本地数据库 · 表 {primary}；本查询只读，未改动任何数据）'
    if not rows:
        dist = _fallback_distribution(payload)
        body += ('\n\n提示：本次未匹配到数据行。请确认取值写法，'
                 '例如「高意向」= intention=\'high\'、「中意向」=\'medium\'、'
                 '「中高意向」= intention IN (\'medium\',\'high\')；'
                 '也可直接问「按意向分组统计客户数」看分布。')
        if dist:
            body += '\n\n' + dist
    return [cite], body
