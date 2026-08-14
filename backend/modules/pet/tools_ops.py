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
    platform: str = '',
) -> tuple[list[dict], str]:
    from modules.pet.jobs import create_job, parse_schedule_from_text

    parsed = parse_schedule_from_text(question) if question else None
    params: dict = {}
    if parsed:
        action = parsed.get('action') or action
        hour = parsed.get('hour') if parsed.get('hour') is not None else hour
        minute = parsed.get('minute', minute)
        interval_hours = parsed.get('interval_hours') if parsed.get('interval_hours') is not None else interval_hours
        title = parsed.get('title') or action
        params = dict(parsed.get('params') or {})
    else:
        title = action
        if hour is None and not interval_hours:
            return (
                [_cite('智仔定时任务', '/')],
                '需要明确时间，例如每天 8 点，或每 2 小时。',
            )

    if action in ('sync_workbench', 'sync_data'):
        action = 'workbench_sync'
    plat = _normalize_workbench_platform(platform or params.get('platform') or '', question)
    if action == 'workbench_sync':
        if plat:
            params['platform'] = plat
        if not (parsed and parsed.get('title')):
            suffix = {'douyin': '抖音', 'xiaohongshu': '小红书', 'shipinhao': '视频号'}.get(plat, '')
            title = f"定时同步内容工作台{('·' + suffix) if suffix else ''}"

    job = create_job(
        action=action,
        title=title,
        hour=hour,
        minute=minute or 0,
        interval_hours=interval_hours,
        params=params,
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


def _normalize_workbench_platform(raw: str = '', question: str = '') -> str:
    """把用户说法映射成 platform key；空=三平台全同步。"""
    text = f'{raw or ""} {question or ""}'.strip().lower()
    if not text:
        return ''
    if any(k in text for k in ('小红书', 'xiaohongshu', 'xhs', '红书')):
        return 'xiaohongshu'
    if any(k in text for k in ('视频号', 'shipinhao', '微信视频')):
        return 'shipinhao'
    if any(k in text for k in ('抖音', 'douyin', 'dy')):
        return 'douyin'
    key = (raw or '').strip().lower()
    if key in ('xiaohongshu', 'shipinhao', 'douyin'):
        return key
    return ''


def tool_sync_workbench(platform: str = '', limit: int = 40, question: str = '') -> tuple[list[dict], str]:
    """从创作者后台同步作品到内容工作台（可指定平台）。"""
    from modules.publish.workbench import batch_sync_workbench

    plat = _normalize_workbench_platform(platform, question)
    limit = max(5, min(80, int(limit or 40)))
    labels = {
        'douyin': '抖音',
        'xiaohongshu': '小红书',
        'shipinhao': '视频号',
        '': '抖音/小红书/视频号',
    }
    label = labels.get(plat, plat or '全平台')

    conn = get_db()
    try:
        result = batch_sync_workbench(conn, platform=plat, limit=limit)
        try:
            conn.commit()
        except Exception:
            pass
    except Exception as e:
        return (
            [_cite('内容工作台·同步', '/workbench', str(e)[:120])],
            f'同步{label}失败：{e}\n若提示未登录，请先到「内容工作台」点对应平台的「登录」并扫码。',
        )
    finally:
        conn.close()

    ok = bool(result.get('ok', True))
    imported = result.get('imported') or {}
    msg = (result.get('message') or result.get('error') or '').strip()
    body_lines = [
        f"{'已完成' if ok else '同步未完成'}：{label} → 内容工作台。",
        f"导入新增 {imported.get('inserted', 0)} · 更新 {imported.get('updated', 0)}"
        f" · 本批合计 {imported.get('total', 0)} · 互动刷新 {result.get('synced', 0)} 条。",
    ]
    if msg:
        body_lines.append(msg)
    if not ok and ('登录' in msg or '未登录' in msg):
        body_lines.append('请先在「内容工作台」完成该平台扫码登录，再让我同步。')
    else:
        body_lines.append('可到「内容工作台」查看卡片与诊断。')
    body = '\n'.join(body_lines)
    return [_cite(f'内容工作台·{label}', '/workbench', body[:160])], body


def tool_compare_workbench(
    platform: str = '',
    limit: int = 8,
    sync_first: bool | None = None,
    question: str = '',
) -> tuple[list[dict], str]:
    """对比内容工作台库里的作品数据（publish_task），不是全网热点榜。"""
    from modules.publish.workbench import batch_sync_workbench, build_workbench

    plat = _normalize_workbench_platform(platform, question)
    limit = max(3, min(20, int(limit or 8)))
    labels = {
        'douyin': '抖音',
        'xiaohongshu': '小红书',
        'shipinhao': '视频号',
        '': '全平台',
    }
    label = labels.get(plat, plat or '全平台')
    q = question or ''

    # 默认：只查内容工作台数据库。仅当用户明确要「先同步后台」时才爬。
    want_sync = sync_first
    if want_sync is None:
        want_sync = any(k in q for k in (
            '同步并对比', '先同步', '同步后再', '从后台同步', '重新同步', '更新后台数据',
        ))

    sync_note = ''
    conn = get_db()
    try:
        where = ["status='done'"]
        params: list = []
        if plat:
            where.append('platform=?')
            params.append(plat)
        local_n = conn.execute(
            f"SELECT COUNT(*) AS c FROM publish_task WHERE {' AND '.join(where)}",
            params,
        ).fetchone()['c']

        if want_sync:
            try:
                sync_res = batch_sync_workbench(conn, platform=plat, limit=max(40, limit * 3))
                conn.commit()
                imp = sync_res.get('imported') or {}
                sync_note = (
                    f"已先从创作者后台同步到内容工作台：新增 {imp.get('inserted', 0)} · "
                    f"更新 {imp.get('updated', 0)} · 合计 {imp.get('total', 0)}。"
                )
                if not sync_res.get('ok', True) and sync_res.get('message'):
                    sync_note += f"\n同步提示：{sync_res.get('message')}"
            except Exception as e:
                sync_note = f'后台同步未完成（{e}），下面仅用库里已有数据对比。'
        elif not local_n:
            return (
                [_cite(f'内容工作台·{label}对比', '/workbench')],
                (
                    f'内容工作台库里还没有「{label}」作品数据，没法对比。\n'
                    f'请先说「同步{label}」把作品入库，或点选项「先同步后台再对比」。'
                ),
            )

        # 核心：从内容工作台（publish_task）取该平台作品再对比
        data = build_workbench(
            conn,
            platform=plat,
            diag='all',
            range_days=0,
            sort='plays',
            sort_dir='desc',
            page=1,
            page_size=max(limit * 3, 50),
        )
    finally:
        conn.close()

    rows = list(data.get('list') or [])
    kpi = data.get('kpi') or {}
    if not rows:
        tip = sync_note + '\n' if sync_note else ''
        return (
            [_cite(f'内容工作台·{label}对比', '/workbench')],
            tip + f'「{label}」暂无作品数据可对比。请先同步到内容工作台。',
        )

    by_plays = sorted(rows, key=lambda x: int(x.get('plays') or 0), reverse=True)
    by_eng = sorted(
        rows,
        key=lambda x: int(x.get('likes') or 0) + int(x.get('comments') or 0) * 2,
        reverse=True,
    )
    warn = [x for x in rows if x.get('diag') in ('drop', 'low_eng')]
    hot = [x for x in rows if x.get('diag') == 'hot']

    def _line(r):
        title = (r.get('title') or r.get('video_title') or '未命名')[:28]
        src = '平台导入' if (r.get('source') or '') == 'platform' else '本系统发布'
        return (
            f"- {title}\n"
            f"  播放 {int(r.get('plays') or 0)} · 点赞 {int(r.get('likes') or 0)} · "
            f"评论 {int(r.get('comments') or 0)} · 转发 {int(r.get('shares') or 0)} · "
            f"收藏 {int(r.get('favorites') or 0)}"
            f" · {r.get('diag_tag') or r.get('diag') or ''} · {src}"
        )

    by_shares = sorted(rows, key=lambda x: int(x.get('shares') or 0), reverse=True)
    lines = [
        f'【{label}作品对比 · 来源：内容工作台数据库】共 {data.get("total") or len(rows)} 条'
        f'（预警 {kpi.get("warn", 0)} · 有咨询倾向 {kpi.get("consult", 0)}）',
    ]
    if sync_note:
        lines.append(sync_note)
    lines.append('')
    lines.append(f'播放 TOP{min(limit, len(by_plays))}：')
    lines.extend(_line(r) for r in by_plays[:limit])
    lines.append('')
    lines.append(f'点赞 TOP{min(min(5, limit), len(by_eng))}：')
    lines.extend(_line(r) for r in by_eng[: min(5, limit)])
    if any(int(r.get('shares') or 0) > 0 for r in by_shares[:5]):
        lines.append('')
        lines.append(f'转发 TOP{min(5, len(by_shares))}：')
        lines.extend(_line(r) for r in by_shares[:5])
    if warn:
        lines.append('')
        lines.append(f'需关注（掉量/互动弱）{min(5, len(warn))} 条：')
        lines.extend(_line(r) for r in warn[:5])
    if hot:
        lines.append('')
        lines.append(f'表现较好 {min(3, len(hot))} 条：')
        lines.extend(_line(r) for r in hot[:3])
    lines.append('')
    lines.append('以上数据来自「内容工作台」入库作品，不是全网热点榜。完整卡片可打开内容工作台查看。')
    body = '\n'.join(lines)
    return [_cite(f'内容工作台·{label}对比', '/workbench', body[:160])], body


def _snapshot_leads() -> dict:
    """线索池快照，供澄清与转化工具使用。"""
    conn = get_db()
    try:
        rows = conn.execute(
            '''SELECT id, nickname, phone, status, source
               FROM lead ORDER BY id DESC LIMIT 50'''
        ).fetchall()
    finally:
        conn.close()
    items = [dict(r) for r in rows]
    convertible = [
        x for x in items
        if (x.get('status') or '') not in ('converted', 'invalid')
    ]
    return {
        'total': len(items),
        'convertible': convertible,
        'convertible_n': len(convertible),
        'converted_n': sum(1 for x in items if x.get('status') == 'converted'),
        'items': items,
    }


def tool_convert_leads(
    lead_ids: list | None = None,
    confirm_all: bool = True,
    question: str = '',
) -> tuple[list[dict], str]:
    """把未转化线索转为客户（复用 CRM convert_lead_to_customer）。"""
    from modules.crm.leads import convert_lead_to_customer, status_label

    snap = _snapshot_leads()
    targets: list[int] = []
    if lead_ids:
        for raw in lead_ids:
            try:
                targets.append(int(raw))
            except (TypeError, ValueError):
                continue
    else:
        targets = [int(x['id']) for x in snap['convertible']]

    if not targets:
        body = (
            f'线索池里目前没有可转化的线索'
            f'（共 {snap["total"]} 条，已转化 {snap["converted_n"]} 条）。'
            '可先到线索池录入，或把待转化线索标为「待首联/跟进中」。'
        )
        return [_cite('线索转客户', '/leads', body[:160])], body

    # 未指定 id 且可转化较多时，若用户未确认全部，先给清单请确认（由路由层通常已 confirm）
    if not lead_ids and not confirm_all and snap['convertible_n'] > 3:
        lines = [
            f'线索池有 {snap["convertible_n"]} 条可转客户，请确认是否全部转化：',
            '',
        ]
        for x in snap['convertible'][:10]:
            lines.append(
                f"- #{x['id']} {x.get('nickname') or '未命名'} · "
                f"{status_label(x.get('status'))}"
            )
        if snap['convertible_n'] > 10:
            lines.append(f'…等共 {snap["convertible_n"]} 条')
        lines.append('')
        lines.append('可以说「全部转成客户」或指定编号，例如「把 #3 #5 转成客户」。')
        return [_cite('线索转客户·待确认', '/leads')], '\n'.join(lines)

    ok, fail = [], []
    for lid in targets:
        try:
            result = convert_lead_to_customer(lid)
            ok.append(result)
        except Exception as e:
            fail.append({'id': lid, 'error': str(e)})

    lines = [f'线索转客户完成：成功 {len(ok)} 条，失败 {len(fail)} 条。']
    for r in ok[:12]:
        if r.get('already'):
            lines.append(f"- 线索 #{r.get('id')} 此前已转化 → 客户 #{r.get('customer_id')}")
        else:
            lines.append(f"- 线索 #{r.get('id')} → 客户 #{r.get('customer_id')}（已进客户列表·约访）")
    for f in fail[:8]:
        lines.append(f"- 线索 #{f.get('id')} 失败：{f.get('error')}")
    lines.append('')
    lines.append('可在「客户列表」查看新客户，或继续说「看看刚转的客户」。')
    body = '\n'.join(lines)
    return [_cite('线索转客户', '/customers', body[:180])], body


def _resolve_customer(name_or_id: str | int | None) -> tuple[dict | None, list[dict], str]:
    """按 id 或昵称解析客户。返回 (唯一客户, 候选列表, 说明)。"""
    conn = get_db()
    try:
        if name_or_id is None or str(name_or_id).strip() == '':
            rows = conn.execute(
                '''SELECT id, nickname, phone, intention, lifecycle_stage
                   FROM customer ORDER BY id DESC LIMIT 8'''
            ).fetchall()
            cands = [dict(r) for r in rows]
            return None, cands, '请指定客户（昵称或编号）'
        raw = str(name_or_id).strip().lstrip('#')
        if raw.isdigit():
            row = conn.execute(
                '''SELECT id, nickname, phone, intention, lifecycle_stage
                   FROM customer WHERE id=?''',
                (int(raw),),
            ).fetchone()
            if row:
                return dict(row), [], ''
            return None, [], f'未找到客户 #{raw}'
        rows = conn.execute(
            '''SELECT id, nickname, phone, intention, lifecycle_stage
               FROM customer
               WHERE nickname ILIKE %s OR phone LIKE %s OR wechat ILIKE %s
               ORDER BY id DESC LIMIT 8''',
            (f'%{raw}%', f'%{raw}%', f'%{raw}%'),
        ).fetchall()
        cands = [dict(r) for r in rows]
        if len(cands) == 1:
            return cands[0], [], ''
        if not cands:
            return None, [], f'未找到昵称/电话含「{raw}」的客户'
        return None, cands, f'找到 {len(cands)} 位相似客户，请指定编号'
    finally:
        conn.close()


def tool_list_crm_followups(limit: int = 8) -> tuple[list[dict], str]:
    """待跟进：久未跟进的客户 + 到期提醒。"""
    limit = max(1, min(20, int(limit or 8)))
    conn = get_db()
    try:
        stale = conn.execute(
            '''SELECT c.id, c.nickname, c.intention, c.lifecycle_stage,
                      MAX(f.created_at) AS last_follow
               FROM customer c
               LEFT JOIN follow_record f ON f.customer_id = c.id
               GROUP BY c.id, c.nickname, c.intention, c.lifecycle_stage
               HAVING MAX(f.created_at) IS NULL
                  OR MAX(f.created_at) < NOW() - INTERVAL '3 days'
               ORDER BY MAX(f.created_at) NULLS FIRST, c.id DESC
               LIMIT %s''',
            (limit,),
        ).fetchall()
        due = conn.execute(
            '''SELECT r.id, r.customer_id, r.title, r.remind_date, r.status,
                      c.nickname
               FROM reminder r
               LEFT JOIN customer c ON c.id = r.customer_id
               WHERE r.customer_id IS NOT NULL
                 AND COALESCE(r.status,'pending') IN ('pending','open','todo','')
                 AND (r.remind_date IS NULL OR r.remind_date <= CURRENT_DATE + 1)
               ORDER BY r.remind_date NULLS FIRST, r.id DESC
               LIMIT %s''',
            (limit,),
        ).fetchall()
    finally:
        conn.close()

    lines = ['【CRM 待办】']
    if stale:
        lines.append(f'久未跟进（≥3天或从未跟进）{len(stale)} 人：')
        for r in stale:
            lf = r['last_follow'] or '从未'
            lines.append(
                f"- 客户 #{r['id']} {r.get('nickname') or '未命名'} · "
                f"意向={r.get('intention') or '-'} · 上次跟进={lf}"
            )
    else:
        lines.append('暂无「久未跟进」客户。')
    if due:
        lines.append('')
        lines.append(f'提醒待处理 {len(due)} 条：')
        for r in due:
            lines.append(
                f"- 提醒 #{r['id']} · 客户 #{r.get('customer_id')} "
                f"{r.get('nickname') or ''} · {r.get('title') or '提醒'} · "
                f"日期={r.get('remind_date') or '—'}"
            )
    lines.append('')
    lines.append('可以说「跟进客户#3：已电话沟通，约周五面谈」让我写入跟进记录。')
    body = '\n'.join(lines)
    return [_cite('CRM待跟进', '/customers', body[:160])], body


def tool_add_customer_follow(
    customer: str | int | None = None,
    content: str = '',
    method: str = 'wechat',
    question: str = '',
) -> tuple[list[dict], str]:
    """给指定客户写一条跟进记录（复用 CRM _create_follow_internal）。"""
    from routes.crm.follows import _create_follow_internal

    cust, cands, hint = _resolve_customer(customer)
    if not cust:
        if cands:
            lines = [hint or '请选择要跟进的客户：', '']
            for c in cands:
                lines.append(
                    f"- #{c['id']} {c.get('nickname') or '未命名'} · "
                    f"{c.get('intention') or '-'} / {c.get('lifecycle_stage') or '-'}"
                )
            lines.append('')
            lines.append('请再说一次，例如：「跟进客户#1：微信已回复，意向中等」。')
            return [_cite('跟进客户·待确认', '/customers')], '\n'.join(lines)
        return [_cite('跟进客户', '/customers')], hint or '未找到客户'

    text = (content or '').strip()
    if not text:
        # 从问句里抽「：」或「跟进内容」后的部分
        q = question or ''
        for sep in ('：', ':', '，内容', ' 内容'):
            if sep in q:
                text = q.split(sep, 1)[-1].strip()
                break
        if not text or text == str(customer):
            text = (question or '智仔代记跟进').strip()[:200]

    payload = {
        'customer_id': cust['id'],
        'content': text[:2000],
        'method': method if method in ('wechat', 'phone', 'offline', 'other') else 'wechat',
        'operator': '智仔',
    }
    result, err, _code = _create_follow_internal(payload)
    if err:
        return [_cite('跟进客户', '/customers')], f'跟进写入失败：{err}'

    body = (
        f"已为客户 #{cust['id']}「{cust.get('nickname') or ''}」写入跟进记录。\n"
        f"方式：{payload['method']} · 内容：{payload['content'][:120]}\n"
        f"可在客户详情查看；也可继续说「列出待跟进客户」。"
    )
    return [_cite(f"跟进·{cust.get('nickname') or cust['id']}", '/customers', body[:160])], body


def tool_generate_script(
    prompt: str = '',
    content_type: str = 'traffic',
    question: str = '',
) -> tuple[list[dict], str]:
    """按主题/提示生成口播文案并入库（复用文案生成逻辑）。"""
    from config import get_ai_config, get_db as _gdb
    from modules.ai.writer import (
        call_llm, build_script_prompt, parse_script_response,
        apply_brand_ending, SYSTEM_PROMPT,
    )
    from routes.content.scripts import _save_script

    topic = (prompt or '').strip()
    if not topic:
        q = (question or '').strip()
        topic = re.sub(
            r'^(帮我|请|立刻|马上)?(写|生成|来)?(一?[条篇]?)?(口播|文案|脚本)?[：:\s]*',
            '',
            q,
        ).strip() or q
    if not topic:
        return [_cite('生成文案', '/scripts')], '请告诉我文案主题，例如「写一条养老金避坑口播」。'

    ai_config = get_ai_config() or {}
    audience = ai_config.get('default_audience', '') or ''
    tone = ai_config.get('default_tone', 'casual') or 'casual'
    ctype = content_type if content_type in ('traffic', 'insurance') else 'traffic'

    try:
        full_prompt = build_script_prompt(
            topic, style='干货分享', duration='60秒',
            audience=audience, tone=tone, extra_req='',
            content_type=ctype, age_band='all',
        )
        result, tokens, model = call_llm(full_prompt, system_prompt=SYSTEM_PROMPT)
        script = parse_script_response(result)
        apply_brand_ending(script)
        script['tokens_used'] = tokens
        script['model_name'] = model
    except Exception as e:
        return [_cite('生成文案', '/scripts')], f'文案生成失败：{e}'

    conn = _gdb()
    try:
        script_id = _save_script(conn, script, None, ctype, 'all')
        conn.commit()
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return [_cite('生成文案', '/scripts')], f'文案已生成但保存失败：{e}'
    finally:
        try:
            conn.close()
        except Exception:
            pass

    title = (script.get('title') or topic)[:60]
    opening = (script.get('hook') or script.get('content') or '')[:80]
    body = (
        f'已生成并保存文案 #{script_id}《{title}》。\n'
        f'开头：{opening or "（见文案库）"}\n'
        f'可说「把这条文案出片」或到文案库查看全文。'
    )
    return [_cite(f'文案#{script_id}', '/scripts', title)], body


# ---------- 工具目录（给模型选）----------

TOOL_SPECS: list[dict[str, Any]] = [
    {
        'name': 'refresh_intel',
        'desc': '只用于刷新「全网热点榜+股票简报」。禁止用于：自己账号的抖音/小红书/视频号作品、播放量、赞评、数据对比',
        'args': {},
    },
    {
        'name': 'refresh_hotspots',
        'desc': '只刷新全网内容热点榜（微博热搜/百度/抖音热榜等公共热搜）。禁止用于：账号作品数据、视频表现对比、调取自己的抖音视频',
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
        'desc': '查看本系统「视频生产」任务进度/合成状态（不是抖音后台作品列表）',
        'args': {'limit': '条数，默认 8'},
    },
    {
        'name': 'list_publish',
        'desc': '查看本系统发布中心概览（待发/已发统计），只读本地库，不爬平台',
        'args': {'limit': '条数，默认 8'},
    },
    {
        'name': 'sync_workbench',
        'desc': '从创作者后台同步「自己的」作品进内容工作台。适用于：同步抖音/视频号/小红书、拉取作品列表。若用户还要对比/分析表现，优先用 compare_workbench',
        'args': {
            'platform': 'douyin | xiaohongshu | shipinhao | 空=三平台都同步',
            'limit': '互动刷新条数，默认 40',
        },
    },
    {
        'name': 'compare_workbench',
        'desc': '从内容工作台数据库读取自己的作品（播放/点赞/评论）做对比。适用于：抖音视频数据对比、作品表现分析。默认只查库；仅当用户明确要求先同步后台时才爬取。不是全网热点榜',
        'args': {
            'platform': 'douyin | xiaohongshu | shipinhao | 空=全平台',
            'limit': '展示条数，默认 8',
            'sync_first': 'bool，仅用户明确要先同步后台时为 true',
        },
    },
    {
        'name': 'prepare_publish',
        'desc': '准备发布最新成片（半自动指引，不代替用户点发表）',
        'args': {},
    },
    {
        'name': 'create_schedule',
        'desc': '创建定时任务（日更/同步工作台数据/股票简报等）',
        'args': {
            'action': 'daily_pipeline | workbench_sync | publish_overview | stock_briefing',
            'hour': '0-23，每天几点',
            'minute': '分钟，默认 0',
            'interval_hours': '每隔几小时，与 hour 二选一',
            'platform': '仅 workbench_sync 可选：douyin/xiaohongshu/shipinhao',
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
    {
        'name': 'convert_leads',
        'desc': '把线索池里的线索转为客户（写入客户列表）。适用于：转客户、线索转客户、批量转化。默认转所有未转化线索；可指定 lead_ids',
        'args': {
            'lead_ids': '可选，线索 id 数组；空则转全部未转化（非 invalid、非 converted）',
            'confirm_all': 'bool，用户已明确要全部转时为 true',
        },
    },
    {
        'name': 'list_crm_followups',
        'desc': '查看待跟进客户与到期提醒。适用于：谁该跟进了、待跟进清单、提醒中心待办',
        'args': {'limit': '条数，默认 8'},
    },
    {
        'name': 'add_customer_follow',
        'desc': '给客户写跟进记录。适用于：跟进客户、记一笔沟通、电话/微信回访。需客户昵称或编号 + 跟进内容',
        'args': {
            'customer': '客户 id 或昵称',
            'content': '跟进内容',
            'method': 'wechat|phone|offline|other，默认 wechat',
        },
    },
    {
        'name': 'generate_script',
        'desc': '按主题生成口播文案并保存到文案库。适用于：写文案、生成口播、根据主题写脚本。出片请再用 produce_script',
        'args': {
            'prompt': '文案主题或要求',
            'content_type': 'traffic|insurance，默认 traffic',
        },
    },
]

# 股票筛选/自选、CRM 写操作、发布准备等扩展工具
from modules.pet import tools_biz as _tools_biz  # noqa: E402

TOOL_SPECS.extend(_tools_biz.TOOL_SPECS)


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
    if name == 'sync_workbench':
        return tool_sync_workbench(
            platform=str(args.get('platform') or ''),
            limit=int(args.get('limit') or 40),
            question=question,
        )
    if name == 'compare_workbench':
        sync_first = args.get('sync_first')
        if sync_first is None or sync_first == '':
            sync_flag = None
        else:
            sync_flag = bool(sync_first)
        return tool_compare_workbench(
            platform=str(args.get('platform') or ''),
            limit=int(args.get('limit') or 8),
            sync_first=sync_flag,
            question=question,
        )
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
            platform=str(args.get('platform') or ''),
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
    if name == 'convert_leads':
        ids = args.get('lead_ids') or args.get('ids') or []
        if isinstance(ids, str):
            ids = [x.strip() for x in ids.split(',') if x.strip()]
        return tool_convert_leads(
            lead_ids=ids or None,
            confirm_all=bool(args.get('confirm_all', True)),
            question=question,
        )
    if name == 'list_crm_followups':
        return tool_list_crm_followups(int(args.get('limit') or 8))
    if name == 'add_customer_follow':
        return tool_add_customer_follow(
            customer=args.get('customer') or args.get('customer_id') or args.get('name'),
            content=str(args.get('content') or ''),
            method=str(args.get('method') or 'wechat'),
            question=question,
        )
    if name == 'generate_script':
        return tool_generate_script(
            prompt=str(args.get('prompt') or args.get('topic') or ''),
            content_type=str(args.get('content_type') or 'traffic'),
            question=question,
        )
    biz = _tools_biz.run_named(name, args, question)
    if biz is not None:
        return biz
    return [], f'未知工具：{name}'


def _parse_plan_json(text: str) -> dict:
    raw = (text or '').strip()
    if not raw:
        return {'is_action': False, 'tools': []}
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

    choices_raw = data.get('choices') or []
    choices = []
    if isinstance(choices_raw, list):
        for i, c in enumerate(choices_raw[:5]):
            if isinstance(c, str) and c.strip():
                choices.append({'id': f'c{i}', 'label': c.strip()[:40], 'message': c.strip()[:120]})
            elif isinstance(c, dict):
                label = str(c.get('label') or c.get('text') or '').strip()
                message = str(c.get('message') or c.get('value') or label).strip()
                if label and message:
                    choices.append({
                        'id': str(c.get('id') or f'c{i}'),
                        'label': label[:40],
                        'message': message[:160],
                    })

    needs_clarify = bool(data.get('needs_clarify')) or bool(choices and not cleaned)
    return {
        'is_action': bool(data.get('is_action')) or bool(cleaned) or needs_clarify,
        'tools': cleaned,
        'reason': data.get('reason') or '',
        'needs_clarify': needs_clarify,
        'clarify_question': str(data.get('question') or data.get('clarify_question') or '').strip(),
        'choices': choices,
    }


def _platform_label(plat: str) -> str:
    return {'douyin': '抖音', 'xiaohongshu': '小红书', 'shipinhao': '视频号'}.get(plat, plat or '平台')


def _snapshot_workbench(platform: str = '') -> dict:
    """读取内容工作台真实数据快照，供智仔像人一样按现状引导。"""
    plat = (platform or '').strip()
    snap = {
        'platform': plat,
        'label': _platform_label(plat) if plat else '全平台',
        'count': 0,
        'plays_sum': 0,
        'likes_sum': 0,
        'comments_sum': 0,
        'shares_sum': 0,
        'favorites_sum': 0,
        'last_synced_at': '',
        'logged_in': None,
        'sample_titles': [],
    }
    conn = get_db()
    try:
        where = ["status='done'"]
        params: list = []
        if plat:
            where.append('platform=?')
            params.append(plat)
        sql = f'''SELECT COUNT(*) AS c,
                         COALESCE(SUM(plays),0) AS plays_sum,
                         COALESCE(SUM(likes),0) AS likes_sum,
                         COALESCE(SUM(comments),0) AS comments_sum,
                         COALESCE(SUM(shares),0) AS shares_sum,
                         COALESCE(SUM(favorites),0) AS favorites_sum,
                         MAX(engagement_synced_at) AS last_synced_at
                  FROM publish_task WHERE {' AND '.join(where)}'''
        row = conn.execute(sql, params).fetchone()
        snap['count'] = int(row['c'] or 0)
        snap['plays_sum'] = int(row['plays_sum'] or 0)
        snap['likes_sum'] = int(row['likes_sum'] or 0)
        snap['comments_sum'] = int(row['comments_sum'] or 0)
        snap['shares_sum'] = int(row['shares_sum'] or 0)
        snap['favorites_sum'] = int(row['favorites_sum'] or 0)
        snap['last_synced_at'] = str(row['last_synced_at'] or '')[:19]
        samples = conn.execute(
            f'''SELECT title, plays, likes, comments, shares, favorites FROM publish_task
                WHERE {' AND '.join(where)}
                ORDER BY COALESCE(plays,0) DESC, id DESC LIMIT 3''',
            params,
        ).fetchall()
        snap['sample_titles'] = [
            {
                'title': (r['title'] or '未命名')[:28],
                'plays': int(r['plays'] or 0),
                'likes': int(r['likes'] or 0),
                'comments': int(r['comments'] or 0),
                'shares': int(r.get('shares') or 0),
                'favorites': int(r.get('favorites') or 0),
            }
            for r in samples
        ]
    except Exception:
        pass
    finally:
        conn.close()

    if plat:
        try:
            from modules.publish.publisher import get_publish_status
            st = get_publish_status(plat) or {}
            snap['logged_in'] = bool(st.get('logged_in'))
        except Exception:
            snap['logged_in'] = None
    return snap


def _snapshot_blurb(snap: dict) -> str:
    label = snap.get('label') or '平台'
    n = int(snap.get('count') or 0)
    if n <= 0:
        login = snap.get('logged_in')
        if login is True:
            return f'内容工作台里目前还没有{label}作品；创作者后台侧看起来已登录。'
        if login is False:
            return f'内容工作台里目前还没有{label}作品；创作者后台可能未登录。'
        return f'内容工作台里目前还没有{label}作品数据。'
    sync = snap.get('last_synced_at') or '未知'
    parts = [
        f'内容工作台里已有 {n} 条{label}作品',
        f'播放合计 {snap.get("plays_sum") or 0}、赞 {snap.get("likes_sum") or 0}、'
        f'评 {snap.get("comments_sum") or 0}、转发 {snap.get("shares_sum") or 0}、'
        f'收藏 {snap.get("favorites_sum") or 0}',
        f'最近同步 {sync}',
    ]
    samples = snap.get('sample_titles') or []
    if samples:
        tops = '；'.join(
            f"「{s['title']}」播{s['plays']}/赞{s['likes']}/转{s.get('shares') or 0}"
            for s in samples[:2]
        )
        parts.append(f'播得较多的如：{tops}')
    return '；'.join(parts) + '。'


def _human_clarify_from_snapshot(question: str, snap: dict) -> dict:
    """按用户真实库存数据，动态生成像人一样的确认问句和选项（非固定模板）。"""
    label = snap.get('label') or '平台'
    plat = snap.get('platform') or ''
    n = int(snap.get('count') or 0)
    q = question or ''
    choices: list[dict] = []

    if n > 0:
        question_text = (
            f'我看了下你的内容工作台：{_snapshot_blurb(snap)}'
            f'你这次更想怎么做？'
        )
        choices.append({
            'id': 'db_compare',
            'label': f'直接对比这 {n} 条{label}作品',
            'message': f'请直接用内容工作台里现有的 {n} 条{label}作品做播放/点赞/评论对比，先不要同步',
        })
        choices.append({
            'id': 'sync_compare',
            'label': f'先同步最新{label}再对比',
            'message': f'请先同步我账号最新的{label}作品到内容工作台，再做播放/点赞/评论对比',
        })
        if any(k in q for k in ('热点', '热搜', '热榜')) or '数据' in q:
            choices.append({
                'id': 'hotspots',
                'label': '其实我想看全网热点',
                'message': '刷新全网热点榜（不是我账号作品）',
            })
    else:
        login = snap.get('logged_in')
        if login is False:
            question_text = (
                f'{_snapshot_blurb(snap)}'
                f'要对比{label}作品，得先登录并同步进工作台。你想先怎么处理？'
            )
            choices.append({
                'id': 'login_hint',
                'label': f'去内容工作台登录{label}',
                'message': f'请提醒我去内容工作台登录{label}，登录后再同步作品',
            })
        else:
            question_text = (
                f'{_snapshot_blurb(snap)}'
                f'要对比的话，我可以先帮你同步入库。你想怎么做？'
            )
        choices.append({
            'id': 'sync_compare',
            'label': f'同步{label}后再对比',
            'message': f'请先同步我的{label}作品到内容工作台，再对比播放/点赞/评论',
        })
        choices.append({
            'id': 'sync_only',
            'label': f'先只同步{label}',
            'message': f'请先同步我的{label}作品到内容工作台，这次先不对比',
        })
        choices.append({
            'id': 'hotspots',
            'label': '其实想看全网热点',
            'message': '刷新全网热点榜（不是我账号作品）',
        })

    return {
        'is_action': True,
        'needs_clarify': True,
        'tools': [],
        'reason': '结合内容工作台真实库存，先确认用户下一步',
        'clarify_question': question_text,
        'choices': choices[:4],
    }


def _maybe_ambiguous_platform_data(question: str) -> str | None:
    """若像「平台作品/数据」含糊请求，返回平台 key；明确同步/热点则返回 None。"""
    q = (question or '').strip()
    if not q:
        return None
    if any(k in q for k in ('热点', '热榜', '热搜', '全网热', '微博热', '百度热', '股票', '北向', 'A股')):
        return None
    plat = _normalize_workbench_platform('', q)
    plat_hit = bool(plat) or any(k in q for k in ('抖音', '小红书', '视频号'))
    vague = any(k in q for k in ('数据', '视频', '作品', '对比', '调取', '拉取', '分析', '表现', '播放', '赞评'))
    clear_sync = ('同步' in q) and plat_hit and not any(k in q for k in ('对比', '分析', '调取', '拉取', '表现'))
    if clear_sync or not (plat_hit and vague):
        return None
    return plat or 'douyin'


def _match_choice_from_history(question: str, history: list[dict] | None) -> dict | None:
    """若用户点选了上一轮选项（或复述选项文案），直接映射工具，避免写死关键词表。"""
    q = (question or '').strip()
    if not q or not history:
        return None
    last_bot = None
    for m in reversed(history):
        if m.get('role') in ('assistant', 'bot'):
            last_bot = m
            break
    if not last_bot:
        return None
    # history 里可能没有 choices；从文案相似度不够时，用语义粗匹配
    meta = last_bot.get('meta') or {}
    choices = meta.get('choices') if isinstance(meta, dict) else None
    # Pet history usually only has role/content; fall through to soft intent
    if isinstance(choices, list):
        for c in choices:
            msg = str((c or {}).get('message') or '').strip()
            label = str((c or {}).get('label') or '').strip()
            if msg and (q == msg or msg in q or q in msg):
                return _plan_from_choice_message(q)
            if label and (q == label or label in q):
                return _plan_from_choice_message(msg or q)

    # 用户复述了很具体的下一步
    if len(q) >= 8 and any(k in q for k in ('内容工作台', '同步', '对比', '热点', '热榜')):
        return _plan_from_choice_message(q)
    return None


def _plan_from_choice_message(message: str) -> dict | None:
    """把自然语言下一步转成工具计划（仍按语义，不靠固定指令菜单）。"""
    q = (message or '').strip()
    if not q:
        return None
    plat = _normalize_workbench_platform('', q)
    if any(k in q for k in ('热点', '热榜', '热搜')) and '作品' not in q:
        return {
            'is_action': True,
            'tools': [{'name': 'refresh_hotspots', 'args': {}}],
            'reason': '用户确认要看全网热点',
            'needs_clarify': False,
            'choices': [],
        }
    if '登录' in q and ('工作台' in q or '提醒' in q):
        label = _platform_label(plat) if plat else '平台'
        return {
            'is_action': True,
            'needs_clarify': True,
            'tools': [],
            'clarify_question': (
                f'好的。请先打开「内容工作台」，点{label}的「登录」并扫码；'
                f'登录成功后直接跟我说「同步{label}」或「同步后再对比」。'
            ),
            'choices': [
                {
                    'id': 'sync_after_login',
                    'label': f'我已登录，同步{label}',
                    'message': f'同步我的{label}作品到内容工作台',
                },
                {
                    'id': 'sync_compare_after_login',
                    'label': f'我已登录，同步并对比',
                    'message': f'先同步我的{label}作品到内容工作台，再对比播放/点赞/评论',
                },
            ],
            'reason': '引导用户完成登录后再同步',
        }
    want_compare = any(k in q for k in ('对比', '分析', '表现'))
    want_sync = ('同步' in q) and not any(k in q for k in ('不要同步', '先不要', '不同步', '无需同步', '先别同步'))
    use_existing = any(k in q for k in ('现有', '已有', '直接对比', '先不要', '不要同步', '不同步'))
    if want_compare and want_sync and not use_existing:
        return {
            'is_action': True,
            'tools': [{'name': 'compare_workbench', 'args': {'platform': plat, 'sync_first': True}}],
            'reason': '用户确认先同步再对比',
            'needs_clarify': False,
            'choices': [],
        }
    if want_compare and (not want_sync or use_existing):
        return {
            'is_action': True,
            'tools': [{'name': 'compare_workbench', 'args': {'platform': plat, 'sync_first': False}}],
            'reason': '用户确认用内容工作台现有数据对比',
            'needs_clarify': False,
            'choices': [],
        }
    if want_sync and not want_compare:
        return {
            'is_action': True,
            'tools': [{'name': 'sync_workbench', 'args': {'platform': plat}}],
            'reason': '用户确认同步作品入库',
            'needs_clarify': False,
            'choices': [],
        }
    return None


def _clarify_platform_data_plan(question: str) -> dict | None:
    """含糊的平台数据请求：按库内真实情况动态引导。"""
    plat = _maybe_ambiguous_platform_data(question)
    if not plat:
        return None
    snap = _snapshot_workbench(plat)
    return _human_clarify_from_snapshot(question, snap)


def _refine_ops_plan(question: str, plan: dict, history: list[dict] | None = None) -> dict:
    """结合真实库存与对话上下文收束计划；避免写死指令表。"""
    q = (question or '').strip()
    if not q:
        return plan

    matched = _match_choice_from_history(q, history)
    if matched:
        return matched

    if plan.get('needs_clarify') and plan.get('choices'):
        if not plan.get('clarify_question'):
            # 用库存补一句更像人话的开场
            plat = _normalize_workbench_platform('', q)
            if plat:
                snap = _snapshot_workbench(plat)
                plan['clarify_question'] = f'{_snapshot_blurb(snap)}你更想先做哪一步？'
            else:
                plan['clarify_question'] = '你更想做哪一步？'
        return plan

    # LLM 已给出明确工具时，若其实是含糊「数据对比」，改成按库存澄清
    clarify = _clarify_platform_data_plan(q)
    if clarify:
        tools = plan.get('tools') or []
        names = {str(t.get('name') or '') for t in tools if isinstance(t, dict)}
        # 仅「同步XX」这种已由 _maybe_ambiguous 排除；其余含糊请求优先澄清
        if not names or names & {'refresh_hotspots', 'refresh_intel', 'run_daily', 'list_videos', 'list_publish'}:
            return clarify
        # 已选 compare/sync 也可用，但若用户没说清是否同步，且库状态特殊，仍可澄清
        if names <= {'compare_workbench', 'sync_workbench'} and '同步' not in q and '对比' in q:
            # 有库存时可直接 compare；无库存则澄清
            plat = _normalize_workbench_platform('', q) or 'douyin'
            snap = _snapshot_workbench(plat)
            if int(snap.get('count') or 0) <= 0:
                return clarify
            # 有数据：不必再问，直接查库对比
            return {
                'is_action': True,
                'tools': [{'name': 'compare_workbench', 'args': {'platform': plat, 'sync_first': False}}],
                'reason': f'工作台已有{snap.get("count")}条，直接对比',
                'needs_clarify': False,
                'choices': [],
            }

    hotspot_ask = any(k in q for k in ('热点', '热榜', '热搜', '全网热'))
    own_data = any(k in q for k in ('作品', '工作台', '账号', '我的视频'))
    names = {str(t.get('name') or '') for t in (plan.get('tools') or []) if isinstance(t, dict)}
    if hotspot_ask and not own_data and names & {'compare_workbench', 'sync_workbench'}:
        return {
            'is_action': True,
            'tools': [{'name': 'refresh_hotspots', 'args': {}}],
            'reason': '用户要全网热点榜',
            'needs_clarify': False,
            'choices': [],
        }
    return plan


def plan_ops_with_llm(question: str, history: list[dict] | None = None) -> dict:
    """让模型判断：直接执行 / 追问澄清 / 普通问答；注入用户真实库存以免空想。"""
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

    plat_guess = _normalize_workbench_platform('', question or '')
    snap = _snapshot_workbench(plat_guess) if plat_guess else _snapshot_workbench('')
    multi = []
    for key in ('douyin', 'xiaohongshu', 'shipinhao'):
        s = _snapshot_workbench(key)
        multi.append(f"{s['label']}{s['count']}条")
    lead_snap = _snapshot_leads()
    lead_names = '、'.join(
        f"#{x['id']}{x.get('nickname') or ''}" for x in lead_snap['convertible'][:5]
    ) or '无'
    try:
        _conn = get_db()
        wl_n = int((_conn.execute('SELECT COUNT(*) AS c FROM stock_watchlist').fetchone() or {}).get('c') or 0)
        _conn.close()
    except Exception:
        wl_n = 0
    inventory = (
        f'当前内容工作台概况：{" / ".join(multi)}。\n'
        f'与用户话最相关平台快照：{_snapshot_blurb(snap)}\n'
        f'线索池：共{lead_snap["total"]}条，可转化{lead_snap["convertible_n"]}条'
        f'（{lead_names}），已转化{lead_snap["converted_n"]}条；自选股 {wl_n} 只。'
    )

    system = (
        '你是运营系统的意图路由器，语气要像真人助理：先看用户现有数据再决定。\n'
        '原则：不要为每句话发明新工具；拿不准就追问，并基于【库存快照】给出贴合现状的选项。\n'
        '三种输出：\n'
        'A) 普通问答：{"is_action":false,"tools":[],"reason":"..."}\n'
        'B) 意图明确：{"is_action":true,"tools":[{"name":"...","args":{}}],"reason":"..."}\n'
        'C) 需澄清：{"is_action":true,"needs_clarify":true,'
        '"question":"结合库存说的一句人话确认",'
        '"choices":[{"label":"短按钮","message":"点选后发给你的完整句子"}],'
        '"tools":[],"reason":"..."}\n'
        '常见做事映射：转客户→convert_leads；跟进/回访→add_customer_follow 或 list_crm_followups；'
        '新建客户→create_customer；改意向/推进阶段→update_customer；建提醒→create_reminder；'
        '登记线索→create_lead；写文案→generate_script；热点出文案→hotspot_to_script；'
        '出片→produce_script；创建发布→create_publish_task；准备发视频→prepare_publish_task 或 prepare_publish；'
        '确认已发→confirm_published；平台登录→workbench_login；日更→run_daily；同步作品→sync_workbench；'
        '筛股票/技术面筛选→run_stock_screen；自选列表→watchlist_list；加自选→watchlist_add；'
        '刷新自选现价→watchlist_refresh；股票复盘→stock_review；筛选历史→list_stock_screens。\n'
        '澄清选项要随库存变化；线索转客户在可转化>0 时可直接执行；'
        '跟进时若未指定客户，先澄清或 list_crm_followups。\n'
        '作品对比默认查内容工作台库；全网热点才用 refresh_hotspots。\n'
        '只输出 JSON。'
    )
    prompt = (
        f'可用工具：\n{catalog}\n\n'
        f'{inventory}\n\n'
        f'对话历史：\n{history_block}\n\n'
        f'用户说：{question}\n\n'
        '请像真人助理一样判断：能直接做就做；不能就基于库存追问。'
    )
    content, _tok, _model = call_llm(
        prompt,
        system_prompt=system,
        temperature=0.2,
        max_tokens=500,
    )
    return _refine_ops_plan(question, _parse_plan_json(content), history=history)


def try_run_ops(
    question: str,
    *,
    history: list[dict] | None = None,
    force: bool = False,
) -> dict | None:
    """
    自然语言驱动运营工具。
    返回 dict: cites/text/step/choices/clarify；普通问答返回 None。
    """
    q = (question or '').strip()
    if not q:
        return None

    try:
        plan = plan_ops_with_llm(q, history)
    except Exception as e:
        if force:
            return {
                'cites': [],
                'text': f'意图理解失败：{e}',
                'step': '运营路由失败',
                'choices': [],
                'clarify': False,
            }
        return None

    # 需要用户选择：不执行工具，返回选项
    if plan.get('needs_clarify') and plan.get('choices'):
        question_text = plan.get('clarify_question') or '你更想做哪一步？'
        lines = [question_text, '', '你可以点选：']
        for i, c in enumerate(plan['choices'], 1):
            lines.append(f"{i}. {c.get('label') or c.get('message')}")
        reason = plan.get('reason') or ''
        text = '\n'.join(lines)
        if reason:
            text = f'（理解：{reason}）\n\n' + text
        return {
            'cites': [_cite('智仔·确认一下', '/', '请选择下一步')],
            'text': text,
            'step': '运营路由 · 请确认意图',
            'choices': plan['choices'],
            'clarify': True,
        }

    tools = plan.get('tools') or []
    if not plan.get('is_action') and not tools:
        if force:
            c1, t1 = tool_list_video_status(5)
            c2, t2 = tool_list_publish_overview(5)
            return {
                'cites': c1 + c2,
                'text': t1 + '\n\n' + t2,
                'step': '运营工具 · 状态快照',
                'choices': [],
                'clarify': False,
            }
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
    return {
        'cites': cites,
        'text': '\n\n'.join(blocks),
        'step': step,
        'choices': [],
        'clarify': False,
    }


# 兼容旧 import 名
def ops_intent(question: str) -> bool:
    """已废弃关键词判断；保留函数避免旧引用报错。实际由 try_run_ops 内 LLM 决定。"""
    return False


def dispatch_ops(question: str) -> tuple[list[dict], str, str]:
    """兼容旧入口：走 LLM 路由。"""
    result = try_run_ops(question, force=True)
    if result:
        return result.get('cites') or [], result.get('text') or '', result.get('step') or '运营工具'
    c1, t1 = tool_list_video_status(5)
    c2, t2 = tool_list_publish_overview(5)
    return c1 + c2, t1 + '\n\n' + t2, '运营工具 · 状态快照'
