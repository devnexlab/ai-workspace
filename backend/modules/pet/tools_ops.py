# -*- coding: utf-8 -*-
"""智仔工具 · 运营操作。

客户随便说话即可：由大模型理解意图并选择工具，不再靠堆关键词指令。
"""

from __future__ import annotations

import json
import re
from typing import Any

from config import get_db, update_setting


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


def _extract_keyword(question: str, hint: str = '') -> str:
    q = (hint or question or '').strip()
    q = re.sub(r'[「」『』“”\'\"]+', '', q)
    q = re.sub(
        r'(一键|帮我|请|立刻|马上|然后|并|的|吧|呀|出片|做成视频|生成视频|合成视频|制作视频|视频任务)',
        ' ',
        q,
    )
    return re.sub(r'\s+', ' ', q).strip()[:40]


# ---------- 具体工具 ----------

def tool_list_video_status(limit: int = 8) -> tuple[list[dict], str]:
    conn = get_db()
    try:
        rows = conn.execute(
            '''SELECT id, title, voice_status, subtitle_status, video_status, export_status,
                      duration, compose_elapsed_sec, error_msg, created_at
               FROM video_task ORDER BY id DESC LIMIT %s''',
            (int(limit) or 8,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return [_cite('视频任务', '/videos', '暂无任务')], '当前没有视频任务。'

    lines = []
    for r in rows:
        st = r['export_status'] or 'pending'
        title = (r['title'] or f'任务#{r["id"]}')[:36]
        err = (r['error_msg'] or '').strip()
        extra = f' · {err[:40]}' if err and st == 'failed' else ''
        lines.append(f"- #{r['id']} [{st}] {title}{extra}")

    body = '最近视频任务：\n' + '\n'.join(lines)
    return [_cite('视频任务列表', '/videos', f'{len(rows)} 条')], body


def tool_list_publish_overview(limit: int = 8) -> tuple[list[dict], str]:
    conn = get_db()
    try:
        stats = conn.execute(
            '''SELECT
                 COUNT(*) FILTER (WHERE status='done') AS done_n,
                 COUNT(*) FILTER (WHERE status IN ('pending','scheduled','queued','ready')) AS pending_n,
                 COUNT(*) FILTER (WHERE COALESCE(got_consult,false)=true) AS consult_n,
                 COALESCE(SUM(likes),0) AS likes_n,
                 COALESCE(SUM(comments),0) AS comments_n
               FROM publish_task'''
        ).fetchone()
        rows = conn.execute(
            '''SELECT id, title, platform, status, likes, comments, got_consult, published_at
               FROM publish_task ORDER BY id DESC LIMIT %s''',
            (int(limit) or 8,),
        ).fetchall()
    finally:
        conn.close()

    lines = [
        f"发布概览：已发 {stats['done_n'] or 0} · 待发 {stats['pending_n'] or 0} · "
        f"有咨询 {stats['consult_n'] or 0} · 赞合计 {stats['likes_n'] or 0} · 评合计 {stats['comments_n'] or 0}",
        '',
        '最近任务：',
    ]
    if not rows:
        lines.append('（暂无发布任务）')
    else:
        for r in rows:
            flag = ' ·有咨询' if r.get('got_consult') else ''
            lines.append(
                f"- #{r['id']} [{r['platform']}/{r['status']}] "
                f"{(r['title'] or '')[:28]} 赞{r['likes'] or 0}/评{r['comments'] or 0}{flag}"
            )
    lines.append('\n平台深度同步需创作者后台登录；发布建议半自动确认。')
    return [_cite('发布中心', '/publish')], '\n'.join(lines)


def tool_run_daily(produce_video: bool = True) -> tuple[list[dict], str]:
    from modules.content_ops.daily_runner import run_daily_pipeline

    result = run_daily_pipeline(
        refresh=True,
        include_platforms=False,
        produce_video=bool(produce_video),
    )
    msg = result.get('message') or '日更完成'
    vids = result.get('video_ids') or []
    body = f"日更已触发。\n{msg}"
    if vids:
        body += f"\n视频任务 ID：{', '.join(str(v) for v in vids)}"
    body += '\n可到「视频生产」查看进度。'
    return [_cite('日更流水线', '/scripts', msg)], body


def tool_produce_script(keyword: str = '', question: str = '') -> tuple[list[dict], str]:
    from modules.content_ops.daily_runner import enqueue_videos_for_scripts

    kw = (keyword or '').strip() or _extract_keyword(question)
    conn = get_db()
    try:
        if kw:
            row = conn.execute(
                '''SELECT id, title, status FROM script
                   WHERE title ILIKE %s OR content ILIKE %s
                   ORDER BY id DESC LIMIT 1''',
                (f'%{kw}%', f'%{kw}%'),
            ).fetchone()
        else:
            row = conn.execute(
                '''SELECT id, title, status FROM script ORDER BY id DESC LIMIT 1'''
            ).fetchone()
    finally:
        conn.close()

    if not row:
        hint = f'「{kw}」' if kw else ''
        return (
            [_cite('文案出片', '/scripts', '未找到文案')],
            f'没找到匹配文案{hint}。请先在文案管理生成，或换个关键词。',
        )

    results = enqueue_videos_for_scripts([row['id']], start_produce=True)
    item = results[0] if results else {}
    if item.get('error'):
        return [_cite('文案出片', '/videos')], f"出片失败：{item['error']}"

    vid = item.get('video_id')
    status = item.get('status')
    body = (
        f"已为文案 #{row['id']}「{row['title']}」处理视频任务 #{vid}（{status}）。\n"
        f"{'已在后台启动配音→字幕→合成。' if item.get('started') else '任务已存在或已完成，可去视频中心查看。'}"
    )
    return [_cite(f'视频任务 #{vid}', '/videos', row['title'] or '')], body


def tool_prepare_latest_publish() -> tuple[list[dict], str]:
    conn = get_db()
    try:
        video = conn.execute(
            '''SELECT id, title, output_path, video_path, export_status
               FROM video_task WHERE export_status='done'
               ORDER BY id DESC LIMIT 1'''
        ).fetchone()
        pending = conn.execute(
            '''SELECT id, title, platform, status FROM publish_task
               WHERE status IN ('pending','ready','scheduled','queued')
               ORDER BY id DESC LIMIT 5'''
        ).fetchall()
    finally:
        conn.close()

    if not video:
        return (
            [_cite('准备发布', '/publish')],
            '还没有已完成的成片。可先跑日更出片，或去视频中心完成合成。',
        )

    lines = [
        f"最新成片：#{video['id']}「{video['title'] or ''}」",
        '建议流程（防封号，默认半自动）：',
        '1. 打开「发布中心」→ 新建发布任务，选平台并关联该成片',
        '2. 点「准备发布」：复制文案并打开创作者后台',
        '3. 你在官方页面确认后点发表',
        '',
    ]
    if pending:
        lines.append('待发布队列：')
        for p in pending:
            lines.append(f"- #{p['id']} [{p['platform']}/{p['status']}] {(p['title'] or '')[:28]}")
    else:
        lines.append('当前没有待发布任务，请先在发布中心创建一条。')

    return [_cite(f'成片 #{video["id"]}', '/publish', video['title'] or '')], '\n'.join(lines)


def tool_enable_daily_schedule(hour: int | None = 8) -> tuple[list[dict], str]:
    h = 8 if hour is None else max(0, min(23, int(hour)))
    update_setting('system', 'daily_auto_enabled', 'true')
    update_setting('system', 'daily_run_hour', str(h))
    body = f'已开启系统日更定时：每天 {h:02d}:00 自动「采热点→写文案→出片」。'
    return [_cite('日更定时', '/settings', f'{h}:00')], body


def tool_disable_daily_schedule() -> tuple[list[dict], str]:
    update_setting('system', 'daily_auto_enabled', 'false')
    from modules.pet.jobs import pause_jobs_by_action
    n = pause_jobs_by_action('daily_pipeline')
    body = f'已关闭系统日更开关。同时暂停了 {n} 条智仔「日更」定时任务。'
    return [_cite('日更定时', '/settings')], body


def tool_list_schedules() -> tuple[list[dict], str]:
    from modules.pet.jobs import list_jobs
    jobs = list_jobs(include_paused=True)
    if not jobs:
        return [_cite('智仔定时任务', '/')], '还没有智仔定时任务。'
    lines = ['智仔定时任务：']
    for j in jobs:
        st = '开' if j.get('enabled') else '停'
        lines.append(
            f"- #{j['id']} [{st}] {j.get('title') or j.get('action')} · {j.get('schedule_label')}"
        )
    return [_cite('智仔定时任务', '/', f'{len(jobs)} 条')], '\n'.join(lines)


def tool_pause_schedules( which: str = 'all') -> tuple[list[dict], str]:
    from modules.pet.jobs import pause_all_jobs, pause_jobs_by_action
    if which in ('daily', 'daily_pipeline', '日更'):
        n = pause_jobs_by_action('daily_pipeline')
        update_setting('system', 'daily_auto_enabled', 'false')
        return [_cite('智仔定时任务', '/')], f'已暂停日更相关定时 {n} 条，并关闭系统日更开关。'
    n = pause_all_jobs()
    return [_cite('智仔定时任务', '/')], f'已暂停 {n} 条智仔定时任务。'


def tool_create_schedule(
    question: str = '',
    action: str = 'daily_pipeline',
    hour: int | None = None,
    minute: int = 0,
    interval_hours: int | None = None,
) -> tuple[list[dict], str]:
    from modules.pet.jobs import create_job, parse_schedule_from_text

    parsed = parse_schedule_from_text(question) if question else None
    if parsed:
        action = parsed.get('action') or action
        hour = parsed.get('hour') if parsed.get('hour') is not None else hour
        minute = parsed.get('minute', minute)
        interval_hours = parsed.get('interval_hours') if parsed.get('interval_hours') is not None else interval_hours
        title = parsed.get('title') or action
    else:
        title = action
        if hour is None and not interval_hours:
            return (
                [_cite('智仔定时任务', '/')],
                '需要明确时间，例如每天 8 点，或每 2 小时。',
            )

    job = create_job(
        action=action,
        title=title,
        hour=hour,
        minute=minute or 0,
        interval_hours=interval_hours,
        params={},
    )
    if action == 'daily_pipeline' and hour is not None:
        update_setting('system', 'daily_auto_enabled', 'true')
        update_setting('system', 'daily_run_hour', str(hour))

    body = (
        f"已创建定时任务 #{job['id']}：{job['title']}\n"
        f"计划：{job['schedule_label']}"
    )
    return [_cite(f"定时 #{job['id']}", '/', job['schedule_label'])], body


def tool_refresh_hotspots() -> tuple[list[dict], str]:
    from modules.content_ops import fetch_all_hotspots
    from modules.content_ops.pipeline import enrich_and_rank
    from routes.content.hot_topics import _insert_items, _dedupe_existing_topics

    items, message = fetch_all_hotspots(use_ai_fallback=True)
    items = enrich_and_rank(items)
    inserted, updated = _insert_items(items)
    removed = _dedupe_existing_topics()
    body = (
        f"热点已刷新。\n{message}\n"
        f"入库新增 {inserted} · 更新 {updated} · 去重 {removed}。\n"
        f"请到「内容情报」刷新页面查看。"
    )
    return [_cite('内容情报·热点', '/hot-topics', message)], body


def tool_refresh_stock_briefing(with_llm: bool = True) -> tuple[list[dict], str]:
    from modules.stocks import news as sn

    news_row = sn.refresh_news_to_page()
    brief = sn.build_stock_briefing(force=True, use_llm=bool(with_llm))
    n = len((news_row or {}).get('news') or brief.get('news') or [])
    body = (
        f"股票情报已刷新（{brief.get('brief_date') or '今日'}）。\n"
        f"财经新闻 {n} 条；简报已{'生成' if (brief.get('brief_md') or '').strip() else '写入'}。\n"
        f"请到「热点情报 · 股票情报」查看。"
    )
    return [_cite('股票情报', '/hot-topics', body[:80])], body


def tool_refresh_intel() -> tuple[list[dict], str]:
    c1, t1 = tool_refresh_hotspots()
    c2, t2 = tool_refresh_stock_briefing(with_llm=True)
    return c1 + c2, t1 + '\n\n' + t2


# ---------- 工具目录（给模型选）----------

TOOL_SPECS: list[dict[str, Any]] = [
    {
        'name': 'refresh_intel',
        'desc': '同时刷新全网热点 + 股票财经简报（用户要最新情报/热点和股票一起更新时用）',
        'args': {},
    },
    {
        'name': 'refresh_hotspots',
        'desc': '只刷新内容热点榜（微博/百度/抖音热等）',
        'args': {},
    },
    {
        'name': 'refresh_stock_briefing',
        'desc': '只刷新股票财经新闻与今日简报',
        'args': {'with_llm': 'bool，默认 true'},
    },
    {
        'name': 'run_daily',
        'desc': '立刻跑日更流水线：采热点→写文案→出片',
        'args': {'produce_video': 'bool，默认 true；用户说不出片则为 false'},
    },
    {
        'name': 'produce_script',
        'desc': '按关键词给某条文案出片（配音字幕合成）',
        'args': {'keyword': '文案标题关键词，可空则用最新文案'},
    },
    {
        'name': 'list_videos',
        'desc': '查看最近视频任务进度/状态',
        'args': {'limit': '条数，默认 8'},
    },
    {
        'name': 'list_publish',
        'desc': '查看发布概览、待发、咨询与赞评',
        'args': {'limit': '条数，默认 8'},
    },
    {
        'name': 'prepare_publish',
        'desc': '准备发布最新成片（半自动指引，不代替用户点发表）',
        'args': {},
    },
    {
        'name': 'create_schedule',
        'desc': '创建定时任务（日更/同步发布数据/股票简报等）',
        'args': {
            'action': 'daily_pipeline | publish_overview | stock_briefing',
            'hour': '0-23，每天几点',
            'minute': '分钟，默认 0',
            'interval_hours': '每隔几小时，与 hour 二选一',
        },
    },
    {
        'name': 'list_schedules',
        'desc': '列出智仔定时任务',
        'args': {},
    },
    {
        'name': 'pause_schedules',
        'desc': '暂停定时任务',
        'args': {'which': 'all 或 daily'},
    },
    {
        'name': 'enable_daily_auto',
        'desc': '开启系统每日自动日更',
        'args': {'hour': '默认 8'},
    },
    {
        'name': 'disable_daily_auto',
        'desc': '关闭系统每日自动日更并暂停相关定时',
        'args': {},
    },
]


def _run_named_tool(name: str, args: dict | None, question: str) -> tuple[list[dict], str]:
    args = args or {}
    if name == 'refresh_intel':
        return tool_refresh_intel()
    if name == 'refresh_hotspots':
        return tool_refresh_hotspots()
    if name == 'refresh_stock_briefing':
        return tool_refresh_stock_briefing(bool(args.get('with_llm', True)))
    if name == 'run_daily':
        return tool_run_daily(bool(args.get('produce_video', True)))
    if name == 'produce_script':
        return tool_produce_script(
            keyword=str(args.get('keyword') or ''),
            question=question,
        )
    if name == 'list_videos':
        return tool_list_video_status(int(args.get('limit') or 8))
    if name == 'list_publish':
        return tool_list_publish_overview(int(args.get('limit') or 8))
    if name == 'prepare_publish':
        return tool_prepare_latest_publish()
    if name == 'create_schedule':
        hour = args.get('hour')
        iv = args.get('interval_hours')
        return tool_create_schedule(
            question=question,
            action=str(args.get('action') or 'daily_pipeline'),
            hour=int(hour) if hour is not None and str(hour) != '' else None,
            minute=int(args.get('minute') or 0),
            interval_hours=int(iv) if iv is not None and str(iv) != '' else None,
        )
    if name == 'list_schedules':
        return tool_list_schedules()
    if name == 'pause_schedules':
        return tool_pause_schedules(str(args.get('which') or 'all'))
    if name == 'enable_daily_auto':
        h = args.get('hour')
        return tool_enable_daily_schedule(int(h) if h is not None else 8)
    if name == 'disable_daily_auto':
        return tool_disable_daily_schedule()
    return [], f'未知工具：{name}'


def _parse_plan_json(text: str) -> dict:
    raw = (text or '').strip()
    if not raw:
        return {'is_action': False, 'tools': []}
    # 容忍 markdown 代码块
    m = re.search(r'\{[\s\S]*\}', raw)
    if not m:
        return {'is_action': False, 'tools': []}
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {'is_action': False, 'tools': []}
    if not isinstance(data, dict):
        return {'is_action': False, 'tools': []}
    tools = data.get('tools') or []
    if not isinstance(tools, list):
        tools = []
    cleaned = []
    for t in tools:
        if isinstance(t, str):
            cleaned.append({'name': t, 'args': {}})
        elif isinstance(t, dict) and t.get('name'):
            cleaned.append({'name': str(t['name']), 'args': t.get('args') or {}})
    return {
        'is_action': bool(data.get('is_action')) or bool(cleaned),
        'tools': cleaned,
        'reason': data.get('reason') or '',
    }


def plan_ops_with_llm(question: str, history: list[dict] | None = None) -> dict:
    """让模型判断是否要操作系统，以及调用哪些工具。"""
    from modules.ai.writer import call_llm

    catalog = '\n'.join(
        f"- {t['name']}: {t['desc']} | args={json.dumps(t['args'], ensure_ascii=False)}"
        for t in TOOL_SPECS
    )
    hist_lines = []
    for m in (history or [])[-6:]:
        role = '用户' if m.get('role') == 'user' else '助手'
        hist_lines.append(f"{role}: {(m.get('content') or '')[:300]}")
    history_block = '\n'.join(hist_lines) if hist_lines else '（无）'

    system = (
        '你是运营系统的意图路由器。根据用户话判断要不要调用系统工具。'
        '普通问答（知识、保险概念、闲聊、只要解释）→ is_action=false，tools=[]。'
        '要执行/刷新/出片/查看任务状态/定时/发布准备等 → is_action=true，并选择工具。'
        '可多选工具（如同时刷热点和股票简报用 refresh_intel，或分别选两个）。'
        '只输出 JSON，不要其它文字。格式：'
        '{"is_action":true/false,"reason":"简述","tools":[{"name":"工具名","args":{}}]}'
    )
    prompt = (
        f'可用工具：\n{catalog}\n\n'
        f'对话历史：\n{history_block}\n\n'
        f'用户说：{question}\n\n'
        '请输出 JSON。'
    )
    content, _tok, _model = call_llm(
        prompt,
        system_prompt=system,
        temperature=0.1,
        max_tokens=400,
    )
    return _parse_plan_json(content)


def try_run_ops(
    question: str,
    *,
    history: list[dict] | None = None,
    force: bool = False,
) -> tuple[list[dict], str, str] | None:
    """
    自然语言驱动运营工具。
    返回 (cites, text, step_label)；若判定为普通问答则返回 None。
    force=True 时（偏运营模式）尽量执行，即使模型犹豫也按工具结果走。
    """
    q = (question or '').strip()
    if not q:
        return None

    try:
        plan = plan_ops_with_llm(q, history)
    except Exception as e:
        if force:
            return [], f'意图理解失败：{e}', '运营路由失败'
        return None

    tools = plan.get('tools') or []
    if not plan.get('is_action') and not tools:
        if force:
            # 偏运营模式：给状态快照
            c1, t1 = tool_list_video_status(5)
            c2, t2 = tool_list_publish_overview(5)
            return c1 + c2, t1 + '\n\n' + t2, '运营工具 · 状态快照'
        return None

    if not tools:
        return None

    known = {t['name'] for t in TOOL_SPECS}
    cites: list[dict] = []
    blocks: list[str] = []
    names: list[str] = []
    for item in tools:
        name = item.get('name') or ''
        if name not in known:
            continue
        try:
            c, text = _run_named_tool(name, item.get('args') or {}, q)
            cites.extend(c)
            blocks.append(text)
            names.append(name)
        except Exception as e:
            blocks.append(f'工具 {name} 执行失败：{e}')
            names.append(name)

    if not blocks:
        return None

    reason = plan.get('reason') or ''
    step = '运营工具 · ' + ('+'.join(names) if names else '执行')
    if reason:
        blocks.insert(0, f'（理解：{reason}）')
    return cites, '\n\n'.join(blocks), step


# 兼容旧 import 名
def ops_intent(question: str) -> bool:
    """已废弃关键词判断；保留函数避免旧引用报错。实际由 try_run_ops 内 LLM 决定。"""
    return False


def dispatch_ops(question: str) -> tuple[list[dict], str, str]:
    """兼容旧入口：走 LLM 路由。"""
    result = try_run_ops(question, force=True)
    if result:
        return result
    c1, t1 = tool_list_video_status(5)
    c2, t2 = tool_list_publish_overview(5)
    return c1 + c2, t1 + '\n\n' + t2, '运营工具 · 状态快照'
