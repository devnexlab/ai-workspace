"""Dashboard route - aggregates real data from database (V1.2 enhanced)."""

from datetime import date, timedelta

from flask import Blueprint, jsonify
from config import get_db as _db

bp = Blueprint('dashboard', __name__)


def _daily_map(conn, sql):
    rows = conn.execute(sql).fetchall()
    out = {}
    for r in rows:
        d = r['d']
        out[d.isoformat() if hasattr(d, 'isoformat') else str(d)] = r['c']
    return out


def _build_trends(conn, days=7):
    hot = _daily_map(conn, """
        SELECT created_at::date AS d, COUNT(*) AS c FROM hot_topic
        WHERE created_at::date >= CURRENT_DATE - INTERVAL '6 days'
        GROUP BY d
    """)
    scripts = _daily_map(conn, """
        SELECT created_at::date AS d, COUNT(*) AS c FROM script
        WHERE created_at::date >= CURRENT_DATE - INTERVAL '6 days'
        GROUP BY d
    """)
    customers = _daily_map(conn, """
        SELECT created_at::date AS d, COUNT(*) AS c FROM customer
        WHERE created_at::date >= CURRENT_DATE - INTERVAL '6 days'
        GROUP BY d
    """)
    publish = _daily_map(conn, """
        SELECT COALESCE(published_at, created_at)::date AS d, COUNT(*) AS c
        FROM publish_task
        WHERE status = 'done'
          AND COALESCE(published_at, created_at)::date >= CURRENT_DATE - INTERVAL '6 days'
        GROUP BY d
    """)
    today = date.today()
    trends = []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        key = d.isoformat()
        trends.append({
            'date': key,
            'label': f'{d.month}/{d.day}',
            'hotTopics': hot.get(key, 0),
            'scripts': scripts.get(key, 0),
            'customers': customers.get(key, 0),
            'publishDone': publish.get(key, 0),
        })
    return trends


@bp.route('/api/dashboard')
def get_dashboard():
    conn = _db()

    # --- V1.1 Stats ---
    hot_count = conn.execute('SELECT COUNT(*) as c FROM hot_topic').fetchone()['c']
    hot_today = conn.execute(
        "SELECT COUNT(*) as c FROM hot_topic WHERE created_at::date = CURRENT_DATE"
    ).fetchone()['c']

    script_count = conn.execute('SELECT COUNT(*) as c FROM script').fetchone()['c']
    script_draft = conn.execute(
        "SELECT COUNT(*) as c FROM script WHERE status = 'draft'"
    ).fetchone()['c']

    video_total = conn.execute('SELECT COUNT(*) as c FROM video_task').fetchone()['c']
    video_done = conn.execute(
        "SELECT COUNT(*) as c FROM video_task WHERE export_status = 'done'"
    ).fetchone()['c']
    video_pending = video_total - video_done

    customer_count = conn.execute('SELECT COUNT(*) as c FROM customer').fetchone()['c']
    customer_new = conn.execute(
        "SELECT COUNT(*) as c FROM customer WHERE created_at::date = CURRENT_DATE"
    ).fetchone()['c']
    customer_high = conn.execute(
        "SELECT COUNT(*) as c FROM customer WHERE intention = 'high'"
    ).fetchone()['c']

    publish_total = conn.execute('SELECT COUNT(*) as c FROM publish_task').fetchone()['c']
    publish_done = conn.execute(
        "SELECT COUNT(*) as c FROM publish_task WHERE status = 'done'"
    ).fetchone()['c']
    publish_pending = publish_total - publish_done

    # --- V1.2 New Stats ---
    knowledge_count = conn.execute('SELECT COUNT(*) as c FROM knowledge_item').fetchone()['c']
    knowledge_today = conn.execute(
        "SELECT COUNT(*) as c FROM knowledge_item WHERE created_at::date = CURRENT_DATE"
    ).fetchone()['c']

    stock_count = conn.execute('SELECT COUNT(*) as c FROM stock_watchlist').fetchone()['c']
    stock_holding = conn.execute(
        "SELECT COUNT(*) as c FROM stock_watchlist WHERE list_type = 'holding'"
    ).fetchone()['c']

    agent_count = conn.execute('SELECT COUNT(*) as c FROM ai_agent').fetchone()['c']
    agent_active = conn.execute(
        "SELECT COUNT(*) as c FROM ai_agent WHERE status = 'active'"
    ).fetchone()['c']

    workflow_count = conn.execute('SELECT COUNT(*) as c FROM workflow').fetchone()['c']
    workflow_active = conn.execute(
        "SELECT COUNT(*) as c FROM workflow WHERE status = 'running'"
    ).fetchone()['c']

    pending_reminders = conn.execute(
        "SELECT COUNT(*) as c FROM reminder WHERE status = 'pending' AND remind_date <= CURRENT_DATE"
    ).fetchone()['c']

    # --- Platform distribution ---
    platform_dist = conn.execute(
        'SELECT platform, COUNT(*) as count FROM hot_topic GROUP BY platform'
    ).fetchall()

    # --- Recent topics ---
    recent_topics = conn.execute(
        'SELECT id, title, platform, likes, ai_score FROM hot_topic ORDER BY created_at DESC LIMIT 5'
    ).fetchall()

    # --- Recent scripts ---
    recent_scripts = conn.execute(
        'SELECT id, title, version, status FROM script ORDER BY created_at DESC LIMIT 5'
    ).fetchall()

    # --- Pending video tasks ---
    pending_videos = conn.execute(
        "SELECT id, title, voice_status, subtitle_status, video_status, export_status "
        "FROM video_task WHERE export_status != 'done' ORDER BY created_at DESC LIMIT 10"
    ).fetchall()

    # --- Pending publish tasks ---
    pending_publish = conn.execute(
        "SELECT p.id, p.platform, p.status, p.scheduled_time, v.title as video_title "
        "FROM publish_task p LEFT JOIN video_task v ON p.video_task_id = v.id "
        "WHERE p.status NOT IN ('done','failed') ORDER BY p.created_at DESC LIMIT 10"
    ).fetchall()

    # --- Draft scripts waiting to produce ---
    pending_scripts = conn.execute(
        "SELECT id, title, content_type, status, created_at FROM script "
        "WHERE COALESCE(status, 'draft') NOT IN ('used') "
        "ORDER BY created_at DESC LIMIT 10"
    ).fetchall()

    # --- Recent customers ---
    recent_customers = conn.execute(
        'SELECT id, nickname, source_channel, intention, lifecycle_stage FROM customer ORDER BY created_at DESC LIMIT 5'
    ).fetchall()

    # --- Customers needing follow-up ---
    follow_customers = conn.execute(
        "SELECT id, nickname, intention, last_follow_time FROM customer "
        "WHERE intention IN ('high','medium') "
        "AND (last_follow_time IS NULL OR last_follow_time = '' "
        "OR last_follow_time::date < CURRENT_DATE - INTERVAL '3 days') "
        "ORDER BY intention DESC, last_follow_time ASC LIMIT 10"
    ).fetchall()

    # --- Recent knowledge items ---
    recent_knowledge = conn.execute(
        'SELECT id, title, category, source_type FROM knowledge_item ORDER BY created_at DESC LIMIT 5'
    ).fetchall()

    # --- Pending reminders ---
    upcoming_reminders = conn.execute(
        "SELECT r.id, r.title, r.type, r.remind_date, c.nickname as customer_name "
        "FROM reminder r LEFT JOIN customer c ON r.customer_id = c.id "
        "WHERE r.status = 'pending' ORDER BY r.remind_date ASC LIMIT 5"
    ).fetchall()

    # --- 今日工作台（当前待办切片）---
    wb_scripts = conn.execute(
        "SELECT id, title, content_type, status FROM script "
        "WHERE COALESCE(status, 'draft') NOT IN ('used') "
        "ORDER BY created_at DESC LIMIT 5"
    ).fetchall()
    wb_videos = conn.execute(
        "SELECT id, title, voice_status, subtitle_status, video_status, export_status, error_msg "
        "FROM video_task WHERE export_status != 'done' "
        "ORDER BY CASE WHEN voice_status='failed' OR subtitle_status='failed' "
        "OR video_status='failed' OR export_status='failed' THEN 0 ELSE 1 END, "
        "created_at DESC LIMIT 5"
    ).fetchall()
    wb_publish = conn.execute(
        "SELECT p.id, p.platform, p.status, v.title as video_title, p.error_msg "
        "FROM publish_task p LEFT JOIN video_task v ON p.video_task_id = v.id "
        "WHERE p.status IN ('pending','reviewing') ORDER BY p.created_at DESC LIMIT 5"
    ).fetchall()
    wb_reminders = conn.execute(
        "SELECT r.id, r.title, r.type, r.remind_date, c.nickname as customer_name "
        "FROM reminder r LEFT JOIN customer c ON r.customer_id = c.id "
        "WHERE r.status = 'pending' AND r.remind_date <= CURRENT_DATE "
        "ORDER BY r.remind_date ASC LIMIT 5"
    ).fetchall()

    overdue_reminders = conn.execute(
        "SELECT COUNT(*) as c FROM reminder WHERE status='pending' AND remind_date < CURRENT_DATE"
    ).fetchone()['c']
    failed_videos = conn.execute(
        "SELECT COUNT(*) as c FROM video_task WHERE "
        "voice_status='failed' OR subtitle_status='failed' OR video_status='failed' OR export_status='failed'"
    ).fetchone()['c']

    # --- Charts: trends & distributions ---
    trends = _build_trends(conn)
    script_status_dist = conn.execute(
        "SELECT COALESCE(status, 'draft') AS status, COUNT(*) AS count "
        "FROM script GROUP BY COALESCE(status, 'draft') ORDER BY count DESC"
    ).fetchall()
    customer_intention_dist = conn.execute(
        "SELECT COALESCE(intention, 'low') AS intention, COUNT(*) AS count "
        "FROM customer GROUP BY COALESCE(intention, 'low') ORDER BY count DESC"
    ).fetchall()

    conn.close()

    return jsonify({
        'stats': {
            'hotTopics': hot_count,
            'hotTopicsToday': hot_today,
            'scripts': script_count,
            'scriptsDraft': script_draft,
            'videosPending': video_pending,
            'videosDone': video_done,
            'customers': customer_count,
            'customersNew': customer_new,
            'customersHigh': customer_high,
            'publishPending': publish_pending,
            'publishDone': publish_done,
            # V1.2
            'knowledgeItems': knowledge_count,
            'knowledgeToday': knowledge_today,
            'stockCount': stock_count,
            'stockHolding': stock_holding,
            'agents': agent_count,
            'agentsActive': agent_active,
            'workflows': workflow_count,
            'workflowsActive': workflow_active,
            'pendingReminders': pending_reminders,
            'overdueReminders': overdue_reminders,
            'failedVideos': failed_videos,
        },
        'pipeline': [
            {'key': 'scriptsDraft', 'label': '草稿文案', 'value': script_draft},
            {'key': 'videosPending', 'label': '待做视频', 'value': video_pending},
            {'key': 'publishPending', 'label': '待发布', 'value': publish_pending},
            {'key': 'publishDone', 'label': '已发布', 'value': publish_done},
        ],
        'trends': trends,
        'scriptStatusDist': [dict(r) for r in script_status_dist],
        'customerIntentionDist': [dict(r) for r in customer_intention_dist],
        'recentTopics': [dict(r) for r in recent_topics],
        'recentScripts': [dict(r) for r in recent_scripts],
        'pendingVideos': [dict(r) for r in pending_videos],
        'pendingPublish': [dict(r) for r in pending_publish],
        'pendingScripts': [dict(r) for r in pending_scripts],
        'recentCustomers': [dict(r) for r in recent_customers],
        'followCustomers': [dict(r) for r in follow_customers],
        'platformDist': [dict(r) for r in platform_dist],
        # V1.2
        'recentKnowledge': [dict(r) for r in recent_knowledge],
        'upcomingReminders': [dict(r) for r in upcoming_reminders],
        'todayWorkbench': {
            'scripts': [dict(r) for r in wb_scripts],
            'videos': [dict(r) for r in wb_videos],
            'publish': [dict(r) for r in wb_publish],
            'reminders': [dict(r) for r in wb_reminders],
            'followCustomers': [dict(r) for r in follow_customers][:5],
            'counts': {
                'scripts': script_draft,
                'videos': video_pending,
                'failedVideos': failed_videos,
                'publish': publish_pending,
                'reminders': pending_reminders,
                'overdueReminders': overdue_reminders,
                'follow': len(follow_customers),
            },
        },
    })
