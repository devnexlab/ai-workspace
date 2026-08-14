"""内容工作台：已发布作品列表、诊断、KPI、批量同步。"""

from __future__ import annotations

from datetime import datetime, timedelta

from modules.publish.publisher import (
    apply_engagement_to_consult,
    get_publish_status,
    sync_publish_engagement,
    _is_content_url,
)

DIAG_META = {
    'consult': {
        'tag': '有咨询',
        'cls': 'ok',
        'tips': ['评论/互动标记为有咨询意向', '建议：及时回复评论或私信跟进'],
    },
    'hot': {
        'tag': '热门',
        'cls': 'hot',
        'tips': ['互动高于账号均值', '可复盘这条的选题与结构，复制到同类内容'],
    },
    'low_eng': {
        'tag': '互动弱',
        'cls': 'warn',
        'tips': ['播放尚可但赞评很少', '建议：加强标题钩子或结尾引导评论'],
    },
    'drop': {
        'tag': '掉量',
        'cls': 'err',
        'tips': ['播放明显低于账号均值', '建议：检查封面、前 3 秒、发布时间'],
    },
    'normal': {
        'tag': '正常',
        'cls': '',
        'tips': ['数据表现正常，可继续观察'],
    },
}


def _num(v, default=0):
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return default


def _eng_score(likes, comments):
    return _num(likes) + _num(comments) * 3


def _parse_dt(val):
    if not val:
        return None
    if isinstance(val, datetime):
        return val
    s = str(val).strip()
    if not s:
        return None
    for fmt in ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(s[:26].replace('T', ' '), fmt if 'T' not in s else fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace('Z', '+00:00')).replace(tzinfo=None)
    except ValueError:
        return None


def _platform_avgs(rows: list[dict]) -> dict[str, dict]:
    buckets: dict[str, list] = {}
    for r in rows:
        plat = (r.get('platform') or '').strip() or '_'
        buckets.setdefault(plat, []).append(r)
    out = {}
    for plat, items in buckets.items():
        n = len(items) or 1
        out[plat] = {
            'plays': sum(_num(x.get('plays')) for x in items) / n,
            'eng': sum(_eng_score(x.get('likes'), x.get('comments')) for x in items) / n,
        }
    return out


def diagnose_row(row: dict, avgs: dict[str, dict] | None = None) -> dict:
    """根据互动与平台均值给出诊断。"""
    likes = _num(row.get('likes'))
    comments = _num(row.get('comments'))
    plays = _num(row.get('plays'))
    eng = _eng_score(likes, comments)
    plat = (row.get('platform') or '').strip() or '_'
    avg = (avgs or {}).get(plat) or {'plays': 0, 'eng': 0}
    avg_plays = float(avg.get('plays') or 0)
    avg_eng = float(avg.get('eng') or 0)

    if row.get('got_consult'):
        key = 'consult'
    elif avg_eng > 0 and eng >= max(avg_eng * 2, 20) and eng >= 15:
        key = 'hot'
    # 低播放量作品不做「掉量/互动弱」误报（样本太小）
    elif plays >= 200 and avg_plays >= 200 and plays < avg_plays * 0.3:
        key = 'drop'
    elif plays >= 800 and eng == 0:
        key = 'low_eng'
    elif plays >= 800 and (eng / max(plays, 1)) < 0.005:
        key = 'low_eng'
    else:
        key = 'normal'

    meta = DIAG_META[key]
    return {
        'diag': key,
        'diag_tag': meta['tag'],
        'diag_cls': meta['cls'],
        'diag_tips': list(meta['tips']),
    }


def apply_sync_result_to_task(conn, task: dict, result: dict) -> dict:
    """把单次 sync_publish_engagement 结果写回 DB，返回更新后的行。"""
    task_id = task['id']
    likes = _num(result.get('likes'))
    comments = _num(result.get('comments'))
    plays = _num(result.get('plays') or result.get('views'))
    shares = _num(result.get('shares'))
    favorites = _num(result.get('favorites'))
    url = (result.get('publish_url') or '').strip()
    got = apply_engagement_to_consult(likes, comments)

    old_url = (task.get('publish_url') or '').strip()
    if url and not _is_content_url(url):
        url = ''
    clear_bad_url = False
    if not url and old_url and not _is_content_url(old_url):
        clear_bad_url = True
    elif old_url and not _is_content_url(old_url) and not url:
        clear_bad_url = True

    fields = [
        'likes=?', 'comments=?', 'plays=?', 'shares=?', 'favorites=?',
        'engagement_synced_at=CURRENT_TIMESTAMP',
    ]
    params: list = [likes, comments, plays, shares, favorites]
    if url:
        fields.append('publish_url=?')
        params.append(url)
    elif clear_bad_url:
        fields.append('publish_url=?')
        params.append('')
    # 平台导入的作品不自动标「有咨询」（赞/评启发式只给本系统发布流用）
    if (task.get('source') or '') != 'platform':
        if got:
            fields.append('got_consult=?')
            params.append(True)
    params.append(task_id)
    conn.execute(f'UPDATE publish_task SET {", ".join(fields)} WHERE id=?', params)
    row = conn.execute('SELECT * FROM publish_task WHERE id=?', (task_id,)).fetchone()
    return dict(row) if row else task


def build_workbench(conn, *, platform='', q='', diag='all', range_days=0,
                    sort='date', sort_dir='desc', page=1, page_size=20) -> dict:
    """组装工作台列表与 KPI。"""
    from modules.content_ops.platforms import list_platforms

    page = max(1, int(page or 1))
    page_size = max(1, min(100, int(page_size or 20)))
    range_days = int(range_days or 0)

    done_rows = conn.execute(
        '''SELECT p.*, v.title AS video_title, v.output_path
           FROM publish_task p
           LEFT JOIN video_task v ON p.video_task_id = v.id
           WHERE p.status = 'done'
           ORDER BY COALESCE(p.published_at, p.created_at) DESC'''
    ).fetchall()
    posts = [dict(r) for r in done_rows]
    avgs = _platform_avgs(posts)

    annotated = []
    now = datetime.now()
    for row in posts:
        d = diagnose_row(row, avgs)
        item = {**row, **d}
        dt = _parse_dt(row.get('published_at')) or _parse_dt(row.get('created_at'))
        item['published_ts'] = dt.isoformat(sep=' ', timespec='seconds') if dt else ''
        item['days_ago'] = (now - dt).days if dt else 9999
        annotated.append(item)

    # KPI（全量 done，不受当前筛选项影响，但平台 count 按全量）
    warn_keys = {'low_eng', 'drop'}
    kpi = {
        'total': len(annotated),
        'warn': sum(1 for x in annotated if x['diag'] in warn_keys),
        'consult': sum(1 for x in annotated if x['diag'] == 'consult' or x.get('got_consult')),
        'pending': conn.execute(
            "SELECT COUNT(*) AS c FROM publish_task WHERE status IN ('pending','reviewing')"
        ).fetchone()['c'],
        'last_synced_at': '',
    }
    synced = [x for x in annotated if x.get('engagement_synced_at')]
    if synced:
        synced.sort(key=lambda x: str(x.get('engagement_synced_at') or ''), reverse=True)
        kpi['last_synced_at'] = str(synced[0].get('engagement_synced_at') or '')

    # 平台条
    plat_counts: dict[str, int] = {}
    for x in annotated:
        k = (x.get('platform') or '').strip()
        if k:
            plat_counts[k] = plat_counts.get(k, 0) + 1

    platforms_out = []
    from config import get_setting
    official_reply = str(
        get_setting('workbench', 'official_auto_reply_shipinhao', 'false')
    ).lower() == 'true'
    for p in list_platforms():
        if not p.get('enable_publish', True):
            continue
        key = p['key']
        st = get_publish_status(key)
        ready = bool(st.get('logged_in'))
        item = {
            'key': key,
            'label': p.get('label') or key,
            'count': plat_counts.get(key, 0),
            'ready': ready,
            'logged_in': ready,
            'has_profile': bool(st.get('has_profile')),
            'has_cookies': bool(st.get('has_cookies')),
            'creator_url': st.get('creator_url') or p.get('creator_url') or '',
            'manage_url': st.get('manage_url') or '',
            'enabled': bool(st.get('enabled')),
        }
        if key == 'shipinhao':
            item['official_auto_reply'] = official_reply
            item['official_auto_reply_hint'] = (
                '请在「视频号助手 → 私信管理」开启「关注后自动回复」；'
                '本系统只记录是否已开启，不会代发私信。'
            )
        platforms_out.append(item)

    # 筛选
    rows = annotated
    if platform:
        rows = [x for x in rows if (x.get('platform') or '') == platform]
    if q:
        qq = q.strip().lower()
        rows = [
            x for x in rows
            if qq in (x.get('title') or '').lower()
            or qq in (x.get('video_title') or '').lower()
        ]
    if range_days > 0:
        rows = [x for x in rows if x.get('days_ago', 9999) <= range_days]
    if diag == 'warn':
        rows = [x for x in rows if x['diag'] in warn_keys]
    elif diag == 'consult':
        rows = [x for x in rows if x['diag'] == 'consult' or x.get('got_consult')]
    elif diag == 'hot':
        rows = [x for x in rows if x['diag'] == 'hot']
    elif diag == 'normal':
        rows = [x for x in rows if x['diag'] == 'normal']

    reverse = (sort_dir or 'desc').lower() != 'asc'
    sort_key = (sort or 'date').lower()

    def _sort_val(item):
        if sort_key == 'plays':
            return _num(item.get('plays'))
        if sort_key == 'likes':
            return _num(item.get('likes'))
        if sort_key == 'comments':
            return _num(item.get('comments'))
        if sort_key == 'shares':
            return _num(item.get('shares'))
        if sort_key == 'favorites':
            return _num(item.get('favorites'))
        # date
        return item.get('published_ts') or ''

    rows = sorted(rows, key=_sort_val, reverse=reverse)
    total = len(rows)
    start = (page - 1) * page_size
    page_rows = rows[start:start + page_size]

    return {
        'list': page_rows,
        'page': page,
        'pageSize': page_size,
        'total': total,
        'kpi': kpi,
        'platforms': platforms_out,
        'prefs': get_workbench_prefs(),
    }


def get_workbench_prefs() -> dict:
    """工作台安全偏好：官方能力勾选 + 低频作品同步。"""
    from config import get_setting

    try:
        hour = int(get_setting('workbench', 'sync_run_hour', '3') or 3)
    except (TypeError, ValueError):
        hour = 3
    hour = max(0, min(23, hour))
    return {
        'official_auto_reply_shipinhao': str(
            get_setting('workbench', 'official_auto_reply_shipinhao', 'false')
        ).lower() == 'true',
        'sync_auto_enabled': str(
            get_setting('workbench', 'sync_auto_enabled', 'false')
        ).lower() == 'true',
        'sync_run_hour': hour,
        'sync_last_run': get_setting('workbench', 'sync_last_run', '') or '',
        'sync_last_run_date': get_setting('workbench', 'sync_last_run_date', '') or '',
    }


def update_workbench_prefs(data: dict) -> dict:
    from config import update_setting

    if 'official_auto_reply_shipinhao' in data:
        update_setting(
            'workbench',
            'official_auto_reply_shipinhao',
            'true' if data.get('official_auto_reply_shipinhao') else 'false',
        )
    if 'sync_auto_enabled' in data:
        update_setting(
            'workbench',
            'sync_auto_enabled',
            'true' if data.get('sync_auto_enabled') else 'false',
        )
    if 'sync_run_hour' in data:
        try:
            hour = max(0, min(23, int(data['sync_run_hour'])))
        except (TypeError, ValueError) as e:
            raise ValueError('sync_run_hour 须为 0-23') from e
        update_setting('workbench', 'sync_run_hour', str(hour))
    return get_workbench_prefs()


def _normalize_published_at(val) -> str | None:
    """把平台抓到的发布时间规范成可入库字符串；无效则 None（避免写成同步时间）。"""
    if not val:
        return None
    if isinstance(val, datetime):
        return val.strftime('%Y-%m-%d %H:%M:%S')
    s = str(val).strip()
    if not s:
        return None
    for fmt in (
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d %H:%M',
        '%Y-%m-%d',
    ):
        try:
            return datetime.strptime(s[:19], fmt).strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            continue
    dt = _parse_dt(s)
    if dt:
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    return None


def import_platform_posts(conn, platform: str, items: list[dict]) -> dict:
    """把创作者后台抓到的作品写入 publish_task（幂等：同平台同标题或同链接则更新）。"""
    from modules.publish.publisher import _is_junk_platform_title

    platform = (platform or '').strip()
    # 清掉历史误抓的状态文案假标题
    junk_titles = (
        '部分人不可见', '公开', '仅自己可见', '好友可见', '已发布', '未通过', '审核中', '审核失败',
        '草稿', '定时发布', '视频', '图文', '笔记', '置顶',
    )
    placeholders = ','.join(['?'] * len(junk_titles))
    deleted = conn.execute(
        f'''DELETE FROM publish_task
            WHERE platform=? AND source='platform' AND title IN ({placeholders})''',
        (platform, *junk_titles),
    ).rowcount
    try:
        deleted = int(deleted or 0)
    except Exception:
        deleted = 0

    inserted = 0
    updated = 0
    for it in items:
        title = (it.get('title') or '').strip()
        if not title or _is_junk_platform_title(title):
            continue
        url = (it.get('url') or '').strip()
        cover_url = (it.get('cover_url') or '').strip()
        likes = _num(it.get('likes'))
        comments = _num(it.get('comments'))
        plays = _num(it.get('plays') or it.get('views'))
        shares = _num(it.get('shares'))
        favorites = _num(it.get('favorites'))
        published_at = _normalize_published_at(it.get('published_at'))

        existing = None
        if url:
            existing = conn.execute(
                "SELECT id FROM publish_task WHERE platform=? AND publish_url=? LIMIT 1",
                (platform, url),
            ).fetchone()
        if not existing and cover_url:
            existing = conn.execute(
                "SELECT id FROM publish_task WHERE platform=? AND cover_url=? LIMIT 1",
                (platform, cover_url),
            ).fetchone()
        if not existing:
            existing = conn.execute(
                """SELECT id FROM publish_task
                   WHERE platform=? AND title=? AND status='done'
                   ORDER BY id DESC LIMIT 1""",
                (platform, title),
            ).fetchone()

        if existing:
            fields = [
                'title=?', 'likes=?', 'comments=?', 'plays=?', 'shares=?', 'favorites=?',
                'got_consult=FALSE',
                'engagement_synced_at=CURRENT_TIMESTAMP',
                "source=COALESCE(NULLIF(source,''), 'platform')",
                "status='done'",
            ]
            params: list = [title, likes, comments, plays, shares, favorites]
            if url:
                fields.append('publish_url=?')
                params.append(url)
            if cover_url:
                fields.append('cover_url=?')
                params.append(cover_url)
            if published_at:
                fields.append('published_at=?')
                params.append(published_at)
            params.append(existing['id'])
            conn.execute(
                f'UPDATE publish_task SET {", ".join(fields)} WHERE id=?',
                params,
            )
            updated += 1
        else:
            conn.execute(
                '''INSERT INTO publish_task
                   (title, platform, status, publish_url, cover_url, likes, comments, plays,
                    shares, favorites, got_consult, source, published_at, engagement_synced_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?, CURRENT_TIMESTAMP)''',
                (
                    title, platform, 'done', url, cover_url, likes, comments, plays,
                    shares, favorites, False, 'platform', published_at,
                ),
            )
            inserted += 1
    return {
        'inserted': inserted,
        'updated': updated,
        'deleted_junk': deleted,
        'total': inserted + updated,
    }


def batch_sync_workbench(conn, *, platform='', limit=5) -> dict:
    """
    同步工作台数据：
    1) 从创作者后台导入笔记/作品列表（指定平台或三平台全部）
    2) 对本地已发布任务刷新互动（默认最多 limit 条）
    """
    from modules.publish.publisher import MANAGE_URLS, scrape_platform_library

    limit = max(1, min(80, int(limit or 5)))
    imported = {'inserted': 0, 'updated': 0, 'total': 0, 'deleted_junk': 0}
    import_errors: list[str] = []

    platforms = [platform] if platform else [k for k in ('shipinhao', 'douyin', 'xiaohongshu') if k in MANAGE_URLS]
    any_import_ok = False
    for plat in platforms:
        if not plat:
            continue
        scraped = scrape_platform_library(
            plat,
            max_items=max(300 if plat == 'shipinhao' else (200 if plat == 'douyin' else 80), limit),
        )
        if scraped.get('ok'):
            part = import_platform_posts(conn, plat, scraped.get('items') or [])
            imported['inserted'] += part.get('inserted', 0)
            imported['updated'] += part.get('updated', 0)
            imported['deleted_junk'] += part.get('deleted_junk', 0)
            imported['total'] += part.get('total', 0)
            any_import_ok = True
            conn.commit()
        else:
            err = scraped.get('error') or f'{plat} 导入失败'
            import_errors.append(err)

    if platforms and not any_import_ok and imported['total'] == 0:
        # 全部导入失败且本地无对应作品
        where = ["status='done'"]
        params: list = []
        if platform:
            where.append('platform=?')
            params.append(platform)
        local_n = conn.execute(
            f"SELECT COUNT(*) AS c FROM publish_task WHERE {' AND '.join(where)}",
            params,
        ).fetchone()['c']
        if not local_n:
            msg = '；'.join(import_errors) or '同步失败'
            return {
                'message': msg,
                'ok': False,
                'synced': 0,
                'total': 0,
                'imported': imported,
                'error': msg,
                'results': [],
            }

    where = ["status='done'"]
    params = []
    if platform:
        where.append('platform=?')
        params.append(platform)
    where_sql = ' AND '.join(where)
    rows = conn.execute(
        f'''SELECT * FROM publish_task
            WHERE {where_sql}
            ORDER BY engagement_synced_at NULLS FIRST,
                     COALESCE(published_at, created_at) DESC
            LIMIT ?''',
        params + [limit],
    ).fetchall()
    tasks = [dict(r) for r in rows]
    results = []
    ok_n = 0
    for task in tasks:
        if task.get('source') == 'platform' and task.get('engagement_synced_at') and imported.get('total'):
            ok_n += 1
            results.append({
                'id': task['id'],
                'ok': True,
                'likes': task.get('likes'),
                'comments': task.get('comments'),
                'plays': task.get('plays'),
                'skipped_detail_sync': True,
            })
            continue
        try:
            raw = sync_publish_engagement(task)
            if not raw.get('ok'):
                results.append({
                    'id': task['id'],
                    'ok': False,
                    'error': raw.get('error') or '同步失败',
                })
                continue
            updated = apply_sync_result_to_task(conn, task, raw)
            ok_n += 1
            results.append({
                'id': task['id'],
                'ok': True,
                'likes': updated.get('likes'),
                'comments': updated.get('comments'),
                'plays': updated.get('plays'),
            })
        except Exception as e:
            results.append({'id': task['id'], 'ok': False, 'error': str(e)})
    conn.commit()

    parts = []
    if imported.get('total'):
        parts.append(
            f"导入/更新 {imported['total']} 条（新 {imported['inserted']} / 更新 {imported['updated']}）"
        )
    if imported.get('deleted_junk'):
        parts.append(f"已清理误抓 {imported['deleted_junk']} 条")
    if import_errors:
        parts.append('部分平台：' + '；'.join(import_errors[:3]))
    parts.append(f'互动刷新 {ok_n}/{len(tasks)} 条')
    return {
        'ok': True,
        'message': '；'.join(parts),
        'synced': ok_n,
        'total': len(tasks),
        'imported': imported,
        'import_error': '；'.join(import_errors) if import_errors else None,
        'results': results,
    }
