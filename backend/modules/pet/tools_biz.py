# -*- coding: utf-8 -*-
"""智仔业务工具扩展：股票筛选/自选、CRM 写操作、发布准备、热点出文案。

复用页面已有模块逻辑，禁止另起一套。由 tools_ops 统一注册与调度。
"""

from __future__ import annotations

import json
import re
from typing import Any

from config import get_db


def _cite(title: str, path: str, snippet: str = '', meta: str = '系统操作') -> dict:
    return {
        'score': '工具',
        'title': title,
        'meta': meta,
        'source_type': 'ops_tool',
        'source_id': 0,
        'path': path,
        'snippet': (snippet or '')[:220],
    }


def _resolve_customer(name_or_id: str | int | None):
    from modules.pet.tools_ops import _resolve_customer as _rc
    return _rc(name_or_id)


# ---------- 股票 ----------

def tool_run_stock_screen(
    text: str = '',
    conditions: list | None = None,
    match_mode: str | None = None,
    min_hits: int | None = None,
    max_stocks: int = 150,
    question: str = '',
) -> tuple[list[dict], str]:
    """技术面筛选（对话场景默认抽样上限，避免卡死）。"""
    from modules.stocks.screener import parse_strategy_text, run_screen

    raw = (text or question or '').strip()
    conds = list(conditions or [])
    mode = match_mode
    hits = min_hits
    rules = None

    # 从白话里解析策略
    if raw and (not conds or any(k in raw for k in ('金叉', '均线', '涨停', '筛选', '形态', 'MACD', 'RSI'))):
        parsed = parse_strategy_text(raw)
        if parsed.get('rules'):
            rules = parsed['rules']
            mode = mode or parsed.get('match_mode')
            hits = hits if hits is not None else parsed.get('min_hits')
            labels = parsed.get('matched_labels') or []
            hint = parsed.get('unmatched_hint') or ''
        else:
            labels, hint = [], parsed.get('unmatched_hint') or ''
    else:
        labels, hint = [], ''

    limit = max(30, min(500, int(max_stocks or 150)))
    try:
        result = run_screen(
            conditions=conds or None,
            rules=rules,
            match_mode=mode or 'and',
            min_hits=int(hits or 1),
            max_stocks=limit,
            workers=6,
        )
    except Exception as e:
        return [_cite('股票筛选', '/stocks')], f'筛选失败：{e}'

    matched = result.get('results') or []
    msg = result.get('message') or '完成'
    lines = [
        f'【技术面筛选】{msg}',
        f'扫描 {result.get("scanned") or 0} / 样本上限 {limit}，命中 {len(matched)} 只'
        f'（模式={result.get("match_mode")}）。',
    ]
    if labels:
        lines.append('启用规则：' + '、'.join(labels[:8]))
    if hint:
        lines.append(f'提示：{hint}')
    lines.append('')
    if not matched:
        lines.append('没有命中股票。可换说法，例如「MACD金叉且均线多头，命中任一，扫200只」。')
    else:
        lines.append(f'命中 TOP{min(15, len(matched))}：')
        for i, r in enumerate(matched[:15], 1):
            hits_l = '、'.join(r.get('hits') or [])[:40]
            lines.append(
                f"{i}. {r.get('name')}({r.get('code')}) "
                f"现价={r.get('close')} 涨跌={r.get('pct_chg')}% "
                f"命中={hits_l}"
            )
        lines.append('')
        lines.append('可以说「把前3只加入自选」或到股票页看完整结果。')

    # 落库一条历史，方便页面查看
    try:
        conn = get_db()
        name = '智仔筛选'
        if labels:
            name = '智仔·' + '+'.join(labels[:2])
        conn.execute(
            '''INSERT INTO stock_screening (name, conditions_json, results_json, status, message)
               VALUES (%s, %s, %s, 'completed', %s)''',
            (
                name[:80],
                json.dumps({
                    'conditions': conds,
                    'rules': result.get('rules') or rules or [],
                    'match_mode': result.get('match_mode'),
                    'matched': len(matched),
                    'scanned': result.get('scanned'),
                    'via': 'pet',
                }, ensure_ascii=False),
                json.dumps(matched[:200], ensure_ascii=False),
                msg[:200],
            ),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

    body = '\n'.join(lines)
    return [_cite('技术面筛选', '/stocks', body[:160])], body


def tool_list_stock_screens(limit: int = 5) -> tuple[list[dict], str]:
    limit = max(1, min(20, int(limit or 5)))
    conn = get_db()
    try:
        rows = conn.execute(
            '''SELECT id, name, status, message, created_at, results_json
               FROM stock_screening ORDER BY id DESC LIMIT %s''',
            (limit,),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                results = json.loads(d.pop('results_json', None) or '[]')
            except Exception:
                results = []
                d.pop('results_json', None)
            d['matched'] = len(results) if isinstance(results, list) else 0
            out.append(d)
    finally:
        conn.close()
    if not out:
        return [_cite('筛选历史', '/stocks')], '还没有筛选记录。可以说「帮我筛 MACD金叉」。'
    lines = ['最近筛选任务：']
    for r in out:
        lines.append(
            f"- #{r['id']} [{r.get('status')}] {r.get('name')} · "
            f"命中约 {r.get('matched')} · {r.get('created_at')}"
        )
    lines.append('可以说「看筛选#id结果」查看详情。')
    return [_cite('筛选历史', '/stocks')], '\n'.join(lines)


def tool_get_stock_screen(screen_id: int | str) -> tuple[list[dict], str]:
    try:
        sid = int(str(screen_id).lstrip('#'))
    except (TypeError, ValueError):
        return [_cite('筛选详情', '/stocks')], '请提供筛选任务编号，例如「看筛选#12」。'
    conn = get_db()
    try:
        row = conn.execute('SELECT * FROM stock_screening WHERE id=%s', (sid,)).fetchone()
    finally:
        conn.close()
    if not row:
        return [_cite('筛选详情', '/stocks')], f'未找到筛选任务 #{sid}'
    d = dict(row)
    try:
        results = json.loads(d.get('results_json') or '[]')
    except Exception:
        results = []
    lines = [
        f"筛选 #{sid} [{d.get('status')}] {d.get('name')}",
        d.get('message') or '',
        f'命中 {len(results)} 只：',
    ]
    for i, r in enumerate((results or [])[:15], 1):
        if not isinstance(r, dict):
            continue
        lines.append(
            f"{i}. {r.get('name')}({r.get('code')}) "
            f"{r.get('close')} / {r.get('pct_chg')}% · "
            + '、'.join(r.get('hits') or [])[:40]
        )
    return [_cite(f'筛选#{sid}', '/stocks')], '\n'.join(lines)


def tool_watchlist_list(limit: int = 20) -> tuple[list[dict], str]:
    limit = max(1, min(50, int(limit or 20)))
    conn = get_db()
    try:
        rows = conn.execute(
            '''SELECT id, stock_code, stock_name, list_type, buy_price, current_price,
                      target_price, notes
               FROM stock_watchlist ORDER BY added_at DESC LIMIT %s''',
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        return [_cite('自选股', '/stocks')], '自选股为空。可以说「把 600519 加入自选」。'
    lines = [f'自选/持仓（最近 {len(rows)} 条）：']
    for r in rows:
        bp = float(r['buy_price'] or 0)
        cp = float(r['current_price'] or 0)
        pnl = ''
        if bp and cp:
            pnl = f' 盈亏={(cp - bp) / bp * 100:.1f}%'
        lines.append(
            f"- #{r['id']} [{r.get('list_type')}] {r.get('stock_name')}({r.get('stock_code')}) "
            f"现价={cp or '—'} 成本={bp or '—'}{pnl}"
        )
    return [_cite('自选股', '/stocks')], '\n'.join(lines)


def tool_watchlist_add(
    code: str = '',
    name: str = '',
    list_type: str = 'watch',
    buy_price: float = 0,
    question: str = '',
) -> tuple[list[dict], str]:
    code = re.sub(r'\D', '', str(code or ''))
    if not code:
        m = re.search(r'(\d{6})', question or '')
        code = m.group(1) if m else ''
    if not code:
        return [_cite('加自选', '/stocks')], '请提供股票代码，例如「把 600519 加入自选」。'
    code = code.zfill(6)
    if not name:
        # 尝试从 universe 取名
        conn = get_db()
        try:
            row = conn.execute(
                'SELECT name FROM stock_universe WHERE code=%s LIMIT 1', (code,)
            ).fetchone()
            name = (row['name'] if row else '') or code
        finally:
            conn.close()
    lt = list_type if list_type in ('watch', 'observe', 'holding') else 'watch'
    conn = get_db()
    try:
        cur = conn.execute(
            '''INSERT INTO stock_watchlist
               (stock_code, stock_name, list_type, buy_price, quantity, notes,
                target_price, alert_below_cost, alert_on_target)
               VALUES (%s,%s,%s,%s,0,'',0,true,true)''',
            (code, name, lt, float(buy_price or 0)),
        )
        new_id = cur.lastrowid
        conn.commit()
    finally:
        conn.close()
    return (
        [_cite('加自选', '/stocks')],
        f'已将 {name}({code}) 加入自选（#{new_id}，类型={lt}）。可以说「刷新自选现价」。',
    )


def tool_watchlist_refresh() -> tuple[list[dict], str]:
    try:
        from modules.stocks.watchlist_scheduler import refresh_watchlist_prices
        result = refresh_watchlist_prices(force_spot=True)
    except Exception as e:
        return [_cite('刷新自选', '/stocks')], f'刷新现价失败：{e}'
    msg = result.get('message') if isinstance(result, dict) else str(result)
    return [_cite('刷新自选', '/stocks')], f'自选现价已刷新。{msg or ""}'


def tool_stock_review(text: str = '', question: str = '') -> tuple[list[dict], str]:
    """AI 复盘：复用 stocks 路由逻辑的精简版。"""
    from modules.ai.writer import call_llm

    raw = (text or question or '').strip()
    if not raw:
        return [_cite('股票复盘', '/stocks')], '请描述要复盘的内容，例如「复盘今天茅台冲高回落」。'
    system = (
        '你是 A 股复盘助手。根据用户描述给出简洁复盘：走势要点、可能原因、风险、下一步观察。'
        '声明不构成投资建议。不要编造未给出的精确价格。'
    )
    try:
        content, _t, model = call_llm(raw, system_prompt=system, temperature=0.3, max_tokens=900)
    except Exception as e:
        return [_cite('股票复盘', '/stocks')], f'复盘失败：{e}'
    conn = get_db()
    try:
        conn.execute(
            '''INSERT INTO stock_review (title, input_text, summary, result_json)
               VALUES (%s,%s,%s,%s)''',
            (
                raw[:40],
                raw[:2000],
                (content or '')[:500],
                json.dumps({'model': model, 'via': 'pet'}, ensure_ascii=False),
            ),
        )
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()
    body = f'【复盘】\n{(content or "").strip()}\n\n（不构成投资建议）'
    return [_cite('股票复盘', '/stocks', body[:160])], body


# ---------- CRM ----------

_STAGE_MAP = {
    '新增': 'new', '新客户': 'new', 'new': 'new',
    '约访': 'appointment', 'appointment': 'appointment',
    '跟踪': 'tracking', '跟踪中': 'tracking', 'tracking': 'tracking',
    '方案': 'proposal', '方案沟通': 'proposal', 'proposal': 'proposal',
    '成交': 'deal', 'deal': 'deal',
    '售后': 'aftercare', 'aftercare': 'aftercare',
}
_INTENT_MAP = {
    '高': 'high', '高意向': 'high', 'high': 'high',
    '中': 'medium', '中意向': 'medium', 'medium': 'medium', 'mid': 'medium',
    '低': 'low', '低意向': 'low', 'low': 'low',
}


def tool_create_customer(
    nickname: str = '',
    phone: str = '',
    wechat: str = '',
    intention: str = 'medium',
    question: str = '',
) -> tuple[list[dict], str]:
    nick = (nickname or '').strip()
    if not nick:
        # 「新建客户张女士」
        m = re.search(r'(?:客户|建档|录入)\s*([^\s，,。]{2,20})', question or '')
        nick = (m.group(1) if m else '').strip()
    if not nick:
        return [_cite('新建客户', '/customers')], '请提供客户称呼，例如「新建客户 张女士」。'
    intent = _INTENT_MAP.get((intention or 'medium').strip(), intention or 'medium')
    if intent not in ('low', 'medium', 'high'):
        intent = 'medium'
    conn = get_db()
    try:
        cur = conn.execute(
            '''INSERT INTO customer
               (nickname, phone, wechat, intention, lifecycle_stage, source_channel)
               VALUES (%s,%s,%s,%s,'new','智仔')''',
            (nick, phone or '', wechat or '', intent),
        )
        cid = cur.lastrowid
        conn.commit()
    finally:
        conn.close()
    return (
        [_cite('新建客户', '/customers')],
        f'已新建客户 #{cid}「{nick}」，意向={intent}，阶段=新增。可说「跟进客户#{cid}：…」。',
    )


def tool_update_customer(
    customer: str | int | None = None,
    intention: str | None = None,
    stage: str | None = None,
    question: str = '',
) -> tuple[list[dict], str]:
    cust, cands, hint = _resolve_customer(customer)
    if not cust:
        if cands:
            lines = [hint, ''] + [
                f"- #{c['id']} {c.get('nickname')}" for c in cands
            ]
            return [_cite('改客户·待确认', '/customers')], '\n'.join(lines)
        return [_cite('改客户', '/customers')], hint or '未找到客户'

    sets, params = [], []
    intent_v = None
    if intention:
        intent_v = _INTENT_MAP.get(str(intention).strip(), str(intention).strip())
        if intent_v in ('low', 'medium', 'high'):
            sets.append('intention=%s')
            params.append(intent_v)
    stage_v = None
    if stage:
        stage_v = _STAGE_MAP.get(str(stage).strip(), str(stage).strip())
        if stage_v in ('new', 'appointment', 'tracking', 'proposal', 'deal', 'aftercare'):
            sets.append('lifecycle_stage=%s')
            params.append(stage_v)
            sets.append('stage_entered_at=CURRENT_TIMESTAMP')

    # 从问句兜底抽
    if not sets and question:
        for k, v in _INTENT_MAP.items():
            if k in question and v in ('low', 'medium', 'high'):
                sets.append('intention=%s')
                params.append(v)
                intent_v = v
                break
        for k, v in _STAGE_MAP.items():
            if k in question and v in ('new', 'appointment', 'tracking', 'proposal', 'deal', 'aftercare'):
                if 'lifecycle_stage=%s' not in sets:
                    sets.append('lifecycle_stage=%s')
                    params.append(v)
                    sets.append('stage_entered_at=CURRENT_TIMESTAMP')
                    stage_v = v
                break

    if not sets:
        return (
            [_cite('改客户', '/customers')],
            '请说明要改什么，例如「把客户#3意向改为高」或「推进到约访」。',
        )

    params.append(cust['id'])
    conn = get_db()
    try:
        conn.execute(f"UPDATE customer SET {', '.join(sets)} WHERE id=%s", params)
        conn.commit()
    finally:
        conn.close()
    bits = []
    if intent_v:
        bits.append(f'意向→{intent_v}')
    if stage_v:
        bits.append(f'阶段→{stage_v}')
    return (
        [_cite('改客户', '/customers')],
        f"已更新客户 #{cust['id']}「{cust.get('nickname') or ''}」：" + '，'.join(bits),
    )


def tool_create_reminder(
    customer: str | int | None = None,
    title: str = '',
    remind_date: str = '',
    question: str = '',
) -> tuple[list[dict], str]:
    cust, cands, hint = _resolve_customer(customer)
    if not cust:
        if cands:
            return [_cite('建提醒·待确认', '/customers')], hint + '\n' + '\n'.join(
                f"- #{c['id']} {c.get('nickname')}" for c in cands
            )
        return [_cite('建提醒', '/customers')], hint or '未找到客户'
    ttl = (title or '').strip() or (question or '跟进提醒')[:40]
    date_s = (remind_date or '').strip()
    if not date_s:
        m = re.search(r'(20\d{2}-\d{1,2}-\d{1,2})', question or '')
        date_s = m.group(1) if m else ''
    conn = get_db()
    try:
        cur = conn.execute(
            '''INSERT INTO reminder (customer_id, type, title, content, remind_date, status)
               VALUES (%s,'follow',%s,%s,%s,'pending')''',
            (cust['id'], ttl[:80], ttl[:200], date_s or None),
        )
        rid = cur.lastrowid
        conn.commit()
    finally:
        conn.close()
    return (
        [_cite('建提醒', '/customers')],
        f"已为客户 #{cust['id']}「{cust.get('nickname') or ''}」创建提醒 #{rid}"
        + (f'，日期 {date_s}' if date_s else '') + '。',
    )


def tool_create_lead(
    nickname: str = '',
    phone: str = '',
    wechat: str = '',
    question: str = '',
) -> tuple[list[dict], str]:
    from modules.crm.leads import create_lead_row

    nick = (nickname or '').strip()
    if not nick:
        m = re.search(r'(?:线索|登记)\s*([^\s，,。]{2,20})', question or '')
        nick = (m.group(1) if m else '').strip()
    if not nick:
        return [_cite('建线索', '/leads')], '请提供称呼，例如「登记线索 李先生 电话138…」。'
    phone = phone or ''
    wechat = wechat or ''
    if not phone:
        m = re.search(r'1\d{10}', question or '')
        phone = m.group(0) if m else ''
    if not wechat:
        m = re.search(r'(?:微信|wx)[:：\s]*([A-Za-z0-9_-]{4,})', question or '', re.I)
        wechat = m.group(1) if m else ''
    if not phone and not wechat:
        return (
            [_cite('建线索', '/leads')],
            f'登记「{nick}」还需要手机或微信号之一，例如「登记线索 {nick} 电话13800138000」。',
        )
    try:
        lead = create_lead_row({
            'nickname': nick,
            'phone': phone,
            'wechat': wechat,
            'source': 'manual',
            'remark': '智仔录入',
        })
    except Exception as e:
        return [_cite('建线索', '/leads')], f'创建线索失败：{e}'
    lid = lead.get('id') if isinstance(lead, dict) else lead
    return (
        [_cite('建线索', '/leads')],
        f'已登记线索 #{lid}「{nick}」。可说「把线索#{lid}转成客户」。',
    )


# ---------- 发布 / 内容 ----------

def tool_create_publish_task(
    platform: str = '',
    video_id: int | str | None = None,
    question: str = '',
) -> tuple[list[dict], str]:
    """用最新成片（或指定视频）创建发布任务。"""
    plat = (platform or '').strip().lower()
    if not plat:
        q = question or ''
        if '抖音' in q:
            plat = 'douyin'
        elif '小红书' in q:
            plat = 'xiaohongshu'
        elif '视频号' in q:
            plat = 'shipinhao'
        else:
            plat = 'douyin'
    if plat in ('抖音',):
        plat = 'douyin'
    if plat in ('小红书',):
        plat = 'xiaohongshu'
    if plat in ('视频号',):
        plat = 'shipinhao'

    conn = get_db()
    try:
        vid = None
        if video_id:
            try:
                vid = int(str(video_id).lstrip('#'))
            except ValueError:
                vid = None
        if vid:
            row = conn.execute(
                'SELECT id, title, output_path FROM video_task WHERE id=%s', (vid,)
            ).fetchone()
        else:
            row = conn.execute(
                '''SELECT id, title, output_path FROM video_task
                   WHERE COALESCE(output_path,'') <> ''
                   ORDER BY id DESC LIMIT 1'''
            ).fetchone()
        if not row:
            return [_cite('创建发布', '/publish')], '没有可用成片。请先出片，再说「准备发布到抖音」。'
        cur = conn.execute(
            '''INSERT INTO publish_task
               (video_task_id, title, description, cover_text, tags, platform, status)
               VALUES (%s,%s,'','','',%s,'pending')''',
            (row['id'], row['title'] or f'视频#{row["id"]}', plat),
        )
        pid = cur.lastrowid
        conn.commit()
    finally:
        conn.close()
    return (
        [_cite('创建发布', '/publish')],
        f'已创建发布任务 #{pid}（平台={plat}，成片视频#{row["id"]}）。'
        f'可说「准备发布任务#{pid}」获取文案与创作者页链接。',
    )


def tool_prepare_publish_task(task_id: int | str | None = None, question: str = '') -> tuple[list[dict], str]:
    """安全准备发布：文案 + 官方页，不自动点发。"""
    from modules.content_ops.platforms import get_platform

    tid = None
    if task_id:
        try:
            tid = int(str(task_id).lstrip('#'))
        except ValueError:
            tid = None
    if not tid:
        m = re.search(r'#?\s*(\d+)', question or '')
        tid = int(m.group(1)) if m else None

    conn = get_db()
    try:
        if tid:
            task = conn.execute(
                '''SELECT p.*, v.output_path, v.title AS video_title
                   FROM publish_task p
                   LEFT JOIN video_task v ON p.video_task_id=v.id WHERE p.id=%s''',
                (tid,),
            ).fetchone()
        else:
            task = conn.execute(
                '''SELECT p.*, v.output_path, v.title AS video_title
                   FROM publish_task p
                   LEFT JOIN video_task v ON p.video_task_id=v.id
                   WHERE p.status IN ('pending','reviewing','ready')
                   ORDER BY p.id DESC LIMIT 1'''
            ).fetchone()
        if not task:
            return [_cite('准备发布', '/publish')], '没有待发布任务。可先说「创建抖音发布任务」。'
        t = dict(task)
        plat = (t.get('platform') or '').strip()
        meta = get_platform(plat) or {}
        label = meta.get('label') or plat or '平台'
        creator_url = meta.get('creator_url') or ''
        title = (t.get('title') or t.get('video_title') or '').strip()
        desc = (t.get('description') or '').strip()
        clipboard = '\n\n'.join(x for x in (title, desc) if x)
        conn.execute(
            "UPDATE publish_task SET status='reviewing', error_msg=%s WHERE id=%s",
            (
                f'已准备：请打开{label}创作者页粘贴文案上传成片后点发表，再回系统确认已发',
                t['id'],
            ),
        )
        conn.commit()
    finally:
        conn.close()

    lines = [
        f'发布任务 #{t["id"]} 已准备（半自动，不代替你点发表）。',
        f'平台：{label}',
        f'成片：{t.get("output_path") or "（见视频任务）"}',
        '',
        '可复制文案：',
        clipboard or '（任务暂无文案，请到发布中心补全）',
        '',
        f'创作者页：{creator_url or "请打开对应平台创作者中心"}',
        '发表后可说「确认发布任务#id已发」。',
    ]
    return [_cite('准备发布', '/publish')], '\n'.join(lines)


def tool_confirm_published(task_id: int | str | None = None, question: str = '') -> tuple[list[dict], str]:
    tid = None
    if task_id:
        try:
            tid = int(str(task_id).lstrip('#'))
        except ValueError:
            tid = None
    if not tid:
        m = re.search(r'#?\s*(\d+)', question or '')
        tid = int(m.group(1)) if m else None
    if not tid:
        return [_cite('确认已发', '/publish')], '请指定任务编号，例如「确认发布任务#8已发」。'
    conn = get_db()
    try:
        row = conn.execute('SELECT id, status FROM publish_task WHERE id=%s', (tid,)).fetchone()
        if not row:
            return [_cite('确认已发', '/publish')], f'未找到发布任务 #{tid}'
        conn.execute(
            "UPDATE publish_task SET status='done', published_at=COALESCE(published_at, CURRENT_TIMESTAMP) WHERE id=%s",
            (tid,),
        )
        conn.commit()
    finally:
        conn.close()
    return [_cite('确认已发', '/publish')], f'发布任务 #{tid} 已标记为已发表。'


def tool_hotspot_to_script(topic_id: int | str | None = None, question: str = '') -> tuple[list[dict], str]:
    from config import get_ai_config
    from modules.ai.writer import generate_script as gen_script

    tid = None
    if topic_id:
        try:
            tid = int(str(topic_id).lstrip('#'))
        except ValueError:
            tid = None
    conn = get_db()
    try:
        if tid:
            topic = conn.execute('SELECT * FROM hot_topic WHERE id=%s', (tid,)).fetchone()
        else:
            topic = conn.execute(
                'SELECT * FROM hot_topic ORDER BY COALESCE(ai_score,0) DESC, id DESC LIMIT 1'
            ).fetchone()
        if not topic:
            return [_cite('热点出文案', '/hotspots')], '热点库为空，请先刷新热点。'
        topic_dict = dict(topic)
    finally:
        conn.close()

    ai = get_ai_config() or {}
    try:
        script = gen_script(
            topic_dict,
            style='高转发共鸣',
            duration='60秒',
            audience=ai.get('default_audience', ''),
            tone=ai.get('default_tone', 'casual'),
            content_type='traffic',
            age_band=topic_dict.get('age_band') or 'all',
        )
    except Exception as e:
        return [_cite('热点出文案', '/scripts')], f'生成失败：{e}'

    tags = str(script.get('tags', '') or '')
    if '泛流量' not in tags:
        tags = f'泛流量,{tags}' if tags else '泛流量'
    conn = get_db()
    try:
        cur = conn.execute(
            '''INSERT INTO script (topic_id,title,hook,content,ending,cover_text,
               tags,version,status,model_name,tokens_used,content_type,age_band)
               VALUES (%s,%s,%s,%s,%s,%s,%s,1,'draft',%s,%s,'traffic',%s)''',
            (
                topic_dict.get('id'),
                str(script.get('title') or ''),
                str(script.get('hook') or ''),
                str(script.get('content') or ''),
                str(script.get('ending') or ''),
                str(script.get('cover_text') or ''),
                tags,
                str(script.get('model_name') or ''),
                int(script.get('tokens_used') or 0),
                topic_dict.get('age_band') or 'all',
            ),
        )
        sid = cur.lastrowid
        conn.commit()
    except Exception as e:
        return [_cite('热点出文案', '/scripts')], f'保存失败：{e}'
    finally:
        try:
            conn.close()
        except Exception:
            pass

    title = (script.get('title') or topic_dict.get('title') or '')[:50]
    return (
        [_cite('热点出文案', '/scripts')],
        f"已根据热点 #{topic_dict.get('id')} 生成文案 #{sid}《{title}》。可说「把文案#{sid}出片」。",
    )


def tool_workbench_login(platform: str = '', question: str = '') -> tuple[list[dict], str]:
    from modules.publish.publisher import start_creator_login

    plat = (platform or '').strip().lower()
    q = question or ''
    if not plat:
        if '抖音' in q:
            plat = 'douyin'
        elif '小红书' in q:
            plat = 'xiaohongshu'
        elif '视频号' in q:
            plat = 'shipinhao'
    if not plat:
        return [_cite('平台登录', '/workbench')], '请指定平台：抖音 / 小红书 / 视频号。'
    result = start_creator_login(plat)
    if not result.get('ok'):
        return [_cite('平台登录', '/workbench')], result.get('error') or result.get('message') or '打开登录失败'
    return [_cite('平台登录', '/workbench')], result.get('message') or f'已打开 {plat} 登录浏览器，请扫码。'


TOOL_SPECS: list[dict[str, Any]] = [
    {
        'name': 'run_stock_screen',
        'desc': '按技术形态筛选 A 股。适用于：帮我筛股票、MACD金叉、均线多头、涨停后筛选。可传白话策略',
        'args': {
            'text': '白话策略，如「MACD金叉且均线多头」',
            'max_stocks': '扫描上限，默认 150',
            'match_mode': 'or|and|min 可选',
        },
    },
    {
        'name': 'list_stock_screens',
        'desc': '查看最近股票筛选任务历史',
        'args': {'limit': '默认 5'},
    },
    {
        'name': 'get_stock_screen',
        'desc': '查看某次筛选命中结果',
        'args': {'screen_id': '筛选任务 id'},
    },
    {
        'name': 'watchlist_list',
        'desc': '查看自选/持仓列表',
        'args': {'limit': '默认 20'},
    },
    {
        'name': 'watchlist_add',
        'desc': '把股票加入自选',
        'args': {'code': '6位代码', 'name': '可选', 'list_type': 'watch|holding|observe'},
    },
    {
        'name': 'watchlist_refresh',
        'desc': '刷新自选股现价',
        'args': {},
    },
    {
        'name': 'stock_review',
        'desc': '对行情/持仓做 AI 复盘（不构成投资建议）',
        'args': {'text': '复盘内容'},
    },
    {
        'name': 'create_customer',
        'desc': '新建客户档案',
        'args': {'nickname': '称呼', 'phone': '可选', 'wechat': '可选', 'intention': 'low|medium|high'},
    },
    {
        'name': 'update_customer',
        'desc': '修改客户意向或生命周期阶段。适用于：改成高意向、推进到约访/成交',
        'args': {
            'customer': '客户 id 或昵称',
            'intention': 'low|medium|high',
            'stage': 'new|appointment|tracking|proposal|deal|aftercare',
        },
    },
    {
        'name': 'create_reminder',
        'desc': '给客户创建跟进提醒',
        'args': {'customer': '客户 id/昵称', 'title': '提醒标题', 'remind_date': 'YYYY-MM-DD 可选'},
    },
    {
        'name': 'create_lead',
        'desc': '登记一条线索到线索池',
        'args': {'nickname': '称呼', 'phone': '可选', 'wechat': '可选'},
    },
    {
        'name': 'create_publish_task',
        'desc': '用最新成片创建发布任务（抖音/小红书/视频号）',
        'args': {'platform': 'douyin|xiaohongshu|shipinhao', 'video_id': '可选视频任务 id'},
    },
    {
        'name': 'prepare_publish_task',
        'desc': '准备发布：给出可复制文案和官方创作者页（不自动点发）',
        'args': {'task_id': '发布任务 id，可空=最近待发'},
    },
    {
        'name': 'confirm_published',
        'desc': '用户已在官方页发表后，标记发布任务为已发',
        'args': {'task_id': '发布任务 id'},
    },
    {
        'name': 'hotspot_to_script',
        'desc': '根据热点生成口播文案。可指定 topic_id，默认用最新高分热点',
        'args': {'topic_id': '热点 id 可选'},
    },
    {
        'name': 'workbench_login',
        'desc': '打开平台创作者后台登录浏览器（抖音/小红书/视频号扫码）',
        'args': {'platform': 'douyin|xiaohongshu|shipinhao'},
    },
]


def run_named(name: str, args: dict | None, question: str) -> tuple[list[dict], str] | None:
    args = args or {}
    if name == 'run_stock_screen':
        return tool_run_stock_screen(
            text=str(args.get('text') or args.get('strategy') or ''),
            conditions=args.get('conditions'),
            match_mode=args.get('match_mode'),
            min_hits=args.get('min_hits'),
            max_stocks=int(args.get('max_stocks') or 150),
            question=question,
        )
    if name == 'list_stock_screens':
        return tool_list_stock_screens(int(args.get('limit') or 5))
    if name == 'get_stock_screen':
        return tool_get_stock_screen(args.get('screen_id') or args.get('id') or '')
    if name == 'watchlist_list':
        return tool_watchlist_list(int(args.get('limit') or 20))
    if name == 'watchlist_add':
        return tool_watchlist_add(
            code=str(args.get('code') or args.get('stock_code') or ''),
            name=str(args.get('name') or args.get('stock_name') or ''),
            list_type=str(args.get('list_type') or 'watch'),
            buy_price=float(args.get('buy_price') or 0),
            question=question,
        )
    if name == 'watchlist_refresh':
        return tool_watchlist_refresh()
    if name == 'stock_review':
        return tool_stock_review(str(args.get('text') or ''), question=question)
    if name == 'create_customer':
        return tool_create_customer(
            nickname=str(args.get('nickname') or args.get('name') or ''),
            phone=str(args.get('phone') or ''),
            wechat=str(args.get('wechat') or ''),
            intention=str(args.get('intention') or 'medium'),
            question=question,
        )
    if name == 'update_customer':
        return tool_update_customer(
            customer=args.get('customer') or args.get('customer_id'),
            intention=args.get('intention'),
            stage=args.get('stage') or args.get('lifecycle_stage'),
            question=question,
        )
    if name == 'create_reminder':
        return tool_create_reminder(
            customer=args.get('customer') or args.get('customer_id'),
            title=str(args.get('title') or ''),
            remind_date=str(args.get('remind_date') or args.get('date') or ''),
            question=question,
        )
    if name == 'create_lead':
        return tool_create_lead(
            nickname=str(args.get('nickname') or ''),
            phone=str(args.get('phone') or ''),
            wechat=str(args.get('wechat') or ''),
            question=question,
        )
    if name == 'create_publish_task':
        return tool_create_publish_task(
            platform=str(args.get('platform') or ''),
            video_id=args.get('video_id'),
            question=question,
        )
    if name == 'prepare_publish_task':
        return tool_prepare_publish_task(args.get('task_id') or args.get('id'), question=question)
    if name == 'confirm_published':
        return tool_confirm_published(args.get('task_id') or args.get('id'), question=question)
    if name == 'hotspot_to_script':
        return tool_hotspot_to_script(args.get('topic_id') or args.get('id'), question=question)
    if name == 'workbench_login':
        return tool_workbench_login(str(args.get('platform') or ''), question=question)
    return None
