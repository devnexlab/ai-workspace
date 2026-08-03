"""Dashboard route - aggregates real data from database (V1.2 enhanced)."""

from flask import Blueprint, jsonify
from config import get_db as _db

bp = Blueprint('dashboard', __name__)


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
        },
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
    })
