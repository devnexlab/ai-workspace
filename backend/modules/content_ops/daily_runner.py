"""
日更编排器：采热点 → 2+1 文案 → 自动建视频任务并出片。

可被 API 一键触发，也可由后台定时调度调用。
"""

from datetime import date, datetime
from config import get_db, get_setting, get_video_config, get_tts_config


def _today_str():
    return date.today().isoformat()


def refresh_intelligence(include_platforms=False, max_keywords=6, count=3):
    """刷新内容情报。默认只拉热榜（快且稳定）；可选再采平台口播。"""
    from modules.content_ops import run_full_intelligence, fetch_all_hotspots
    from routes.content.hot_topics import _insert_items, _dedupe_existing_topics

    if include_platforms:
        items, message = run_full_intelligence(
            include_hotspots=True,
            count_per_keyword=count,
            max_keywords=max_keywords,
        )
    else:
        items, message = fetch_all_hotspots(use_ai_fallback=True)
        from modules.content_ops.pipeline import enrich_and_rank
        items = enrich_and_rank(items)

    inserted, updated = _insert_items(items)
    removed = _dedupe_existing_topics()
    return {
        'message': message,
        'fetched': len(items),
        'inserted': inserted,
        'updated': updated,
        'deduped': removed,
    }


def generate_daily_scripts(traffic_count=None, insurance_count=None):
    """
    生成今日 2+1 文案计划（与 /api/scripts/daily-plan 同逻辑）。
    返回 dict: created / skipped / errors / brand_ending / message
    """
    from modules.ai.writer import generate_script as gen_script, AGE_AUDIENCE
    from routes.content.scripts import AGE_ROTATION, _save_script

    traffic_n = int(
        traffic_count
        if traffic_count is not None
        else (get_setting('system', 'daily_traffic_count', '2') or 2)
    )
    insurance_n = int(
        insurance_count
        if insurance_count is not None
        else (get_setting('system', 'daily_insurance_count', '1') or 1)
    )

    conn = get_db()
    today = _today_str()
    existing = conn.execute(
        '''SELECT content_type, COUNT(*) as c FROM script
           WHERE created_at::date = %s::date
           GROUP BY content_type''',
        (today,)
    ).fetchall()
    existing_map = {r['content_type']: r['c'] for r in existing}

    need_traffic = max(0, traffic_n - existing_map.get('traffic', 0))
    need_insurance = max(0, insurance_n - existing_map.get('insurance', 0))

    topics = conn.execute(
        '''SELECT * FROM hot_topic
           WHERE status != 'ignored'
           ORDER BY engagement_score DESC NULLS LAST, ai_score DESC NULLS LAST,
                    (likes+comments+shares) DESC, created_at DESC
           LIMIT 40'''
    ).fetchall()
    conn.close()
    topics = [dict(t) for t in topics]

    created = []
    errors = []
    used_topic_ids = set()
    start_idx = date.today().toordinal() % len(AGE_ROTATION)

    def pick_topic(prefer_insurance=False):
        for t in topics:
            if t['id'] in used_topic_ids:
                continue
            title = (t.get('title') or '') + (t.get('keyword') or '') + (t.get('analysis') or '')
            has_ins = any(k in title for k in ('保险', '理赔', '保单', '重疾', '医保', '养老', '保障'))
            if prefer_insurance and not has_ins:
                continue
            if not prefer_insurance and has_ins and len(topics) > need_traffic + 2:
                continue
            used_topic_ids.add(t['id'])
            return t
        for t in topics:
            if t['id'] not in used_topic_ids:
                used_topic_ids.add(t['id'])
                return t
        return None

    for i in range(need_traffic):
        age_band = AGE_ROTATION[(start_idx + i) % len(AGE_ROTATION)]
        topic = pick_topic(prefer_insurance=False)
        try:
            if topic:
                script = gen_script(
                    topic, style='高转发共鸣', duration='60秒',
                    content_type='traffic', age_band=age_band,
                    tone='casual',
                    extra_req=f'面向{AGE_AUDIENCE.get(age_band, "")}，强共鸣可转发，不硬广',
                )
                topic_id = topic['id']
            else:
                script = gen_script(
                    f'结合今日社会热点，写一条面向{AGE_AUDIENCE.get(age_band)}的人生共鸣口播，不硬广保险',
                    style='高转发共鸣', duration='60秒',
                    content_type='traffic', age_band=age_band, tone='casual',
                )
                topic_id = None
            conn = get_db()
            sid = _save_script(conn, script, topic_id, 'traffic', age_band)
            conn.commit()
            conn.close()
            created.append({
                'id': sid, 'content_type': 'traffic', 'age_band': age_band,
                'title': script.get('title'), 'topic_id': topic_id,
            })
        except Exception as e:
            errors.append(f'泛流量#{i + 1}: {e}')

    for i in range(need_insurance):
        topic = pick_topic(prefer_insurance=True)
        try:
            if topic:
                script = gen_script(
                    topic, style='保险避坑干货', duration='60秒',
                    content_type='insurance', age_band='all',
                    tone='friendly',
                    extra_req='专业但不吓人，用案例建立信任，引导关注来找我',
                )
                topic_id = topic['id']
            else:
                script = gen_script(
                    '家庭保障常见误区与理赔避坑，面向全年龄段口播',
                    style='保险避坑干货', duration='60秒',
                    content_type='insurance', age_band='all', tone='friendly',
                )
                topic_id = None
            conn = get_db()
            sid = _save_script(conn, script, topic_id, 'insurance', 'all')
            conn.commit()
            conn.close()
            created.append({
                'id': sid, 'content_type': 'insurance', 'age_band': 'all',
                'title': script.get('title'), 'topic_id': topic_id,
            })
        except Exception as e:
            errors.append(f'保险#{i + 1}: {e}')

    ending = get_setting('system', 'fixed_ending', '')
    return {
        'message': f'今日计划完成：新生成 {len(created)} 条（目标泛流量{traffic_n}+保险{insurance_n}）',
        'created': created,
        'skipped': {
            'traffic_already': existing_map.get('traffic', 0),
            'insurance_already': existing_map.get('insurance', 0),
            'need_traffic': need_traffic,
            'need_insurance': need_insurance,
        },
        'brand_ending': ending,
        'errors': errors,
        'traffic_target': traffic_n,
        'insurance_target': insurance_n,
    }


def _video_defaults():
    from routes.video.videos import get_last_video_prefs
    prefs = get_last_video_prefs()
    return {
        'resolution': prefs.get('resolution') or '1080x1920',
        'fps': prefs.get('fps') or '30',
        'render_quality': prefs.get('render_quality') or 'high',
        'fade_transition': prefs.get('fade_transition') or 'true',
        'title_overlay': prefs.get('title_overlay') or 'true',
        'video_engine': prefs.get('video_engine') or 'moviepy',
        'voice': prefs.get('voice') or '',
        'voice_rate': prefs.get('voice_rate') or '',
        'video_style': prefs.get('video_style') or 'default',
        'material_ids': prefs.get('material_ids') or '',
        'narration_prompt': prefs.get('narration_prompt') or '',
    }


def enqueue_videos_for_scripts(script_ids, start_produce=True):
    """
    为文案创建视频任务；若已有关联任务则复用。
    start_produce=True 时后台启动 step=all。
    """
    from routes.video.videos import _run_video_step_background
    import threading

    defaults = _video_defaults()
    results = []
    conn = get_db()

    for sid in script_ids:
        script = conn.execute('SELECT * FROM script WHERE id=?', (sid,)).fetchone()
        if not script:
            results.append({'script_id': sid, 'error': '文案不存在'})
            continue
        script = dict(script)

        existing = conn.execute(
            '''SELECT * FROM video_task WHERE script_id=?
               ORDER BY id DESC LIMIT 1''',
            (sid,)
        ).fetchone()

        if existing and existing['export_status'] == 'done':
            conn.execute('UPDATE script SET status=? WHERE id=?', ('used', sid))
            conn.commit()
            results.append({
                'script_id': sid,
                'video_id': existing['id'],
                'status': 'already_done',
                'title': existing.get('title') or script.get('title'),
            })
            continue

        if existing and existing['export_status'] in ('pending', 'processing'):
            video_id = existing['id']
            task_dict = dict(existing)
            created_new = False
        else:
            cur = conn.execute(
                '''INSERT INTO video_task (script_id,title,video_style,material_ids,
                   resolution,fps,render_quality,fade_transition,title_overlay,video_engine,
                   narration_prompt,voice,voice_rate,
                   voice_status,subtitle_status,video_status,export_status)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (
                    sid, script.get('title') or f'脚本#{sid}',
                    defaults.get('video_style') or 'default',
                    defaults.get('material_ids') or '',
                    defaults['resolution'], defaults['fps'],
                    defaults['render_quality'], defaults['fade_transition'],
                    defaults['title_overlay'], defaults['video_engine'],
                    defaults.get('narration_prompt') or '',
                    defaults['voice'], defaults['voice_rate'],
                    'pending', 'pending', 'pending', 'pending',
                )
            )
            conn.commit()
            video_id = cur.lastrowid
            task_dict = dict(conn.execute(
                'SELECT * FROM video_task WHERE id=?', (video_id,)
            ).fetchone())
            created_new = True

        # 文案标记为已出片（仍可再次点出片做新成片）
        conn.execute('UPDATE script SET status=? WHERE id=?', ('used', sid))
        conn.commit()

        started = False
        if start_produce and task_dict.get('export_status') != 'done':
            # 标记 processing，避免重复点
            conn.execute(
                '''UPDATE video_task SET voice_status=?, subtitle_status=?,
                   video_status=?, export_status=?, error_msg=? WHERE id=?''',
                ('processing', 'processing', 'processing', 'processing', '', video_id)
            )
            conn.commit()
            thread = threading.Thread(
                target=_run_video_step_background,
                args=(video_id, 'all', script, task_dict),
                daemon=True,
            )
            thread.start()
            started = True

        results.append({
            'script_id': sid,
            'video_id': video_id,
            'title': script.get('title'),
            'created': created_new,
            'started': started,
            'status': 'producing' if started else task_dict.get('export_status'),
        })

    conn.close()
    return results


def run_daily_pipeline(
    refresh=True,
    include_platforms=False,
    produce_video=True,
    traffic_count=None,
    insurance_count=None,
):
    """
    完整日更：采 → 写 → 片。
    """
    steps = {}
    logs = []

    if refresh:
        try:
            steps['refresh'] = refresh_intelligence(include_platforms=include_platforms)
            logs.append(
                f"情报：抓取{steps['refresh']['fetched']} / 入库{steps['refresh']['inserted']}"
            )
        except Exception as e:
            steps['refresh'] = {'error': str(e)}
            logs.append(f'情报失败: {e}')

    plan = generate_daily_scripts(
        traffic_count=traffic_count,
        insurance_count=insurance_count,
    )
    steps['plan'] = plan
    logs.append(plan['message'])
    if plan.get('errors'):
        logs.append('文案错误: ' + '；'.join(plan['errors'][:3]))

    # 今日应出片的文案：本次新建 + 今日已有但还没出片的
    script_ids = [c['id'] for c in plan.get('created') or []]
    conn = get_db()
    today = _today_str()
    today_scripts = conn.execute(
        '''SELECT s.id FROM script s
           WHERE s.created_at::date = %s::date
           AND NOT EXISTS (
             SELECT 1 FROM video_task v
             WHERE v.script_id = s.id AND v.export_status = 'done'
           )
           ORDER BY s.id''',
        (today,)
    ).fetchall()
    conn.close()
    for row in today_scripts:
        if row['id'] not in script_ids:
            script_ids.append(row['id'])

    videos = []
    if produce_video and script_ids:
        try:
            videos = enqueue_videos_for_scripts(script_ids, start_produce=True)
            started_n = sum(1 for v in videos if v.get('started'))
            logs.append(f'出片：处理 {len(videos)} 个任务，启动 {started_n} 个')
        except Exception as e:
            logs.append(f'出片失败: {e}')
            videos = [{'error': str(e)}]
    elif not produce_video:
        logs.append('已跳过出片')
    else:
        logs.append('无可出片文案')

    steps['videos'] = videos

    # 记录今日已跑过（供定时器去重）
    try:
        from config import update_setting
        update_setting('system', 'daily_last_run', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        update_setting('system', 'daily_last_run_date', _today_str())
    except Exception:
        pass

    return {
        'ok': True,
        'message': ' | '.join(logs),
        'steps': steps,
        'script_ids': script_ids,
        'video_ids': [v.get('video_id') for v in videos if v.get('video_id')],
        'ran_at': datetime.now().isoformat(timespec='seconds'),
    }
