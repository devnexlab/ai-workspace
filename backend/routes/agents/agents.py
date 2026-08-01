"""AI Agent Center routes - manage all AI capabilities (V1.2 new module)."""

from flask import Blueprint, request, jsonify
from config import get_db as _db
import json

bp = Blueprint('agents', __name__)

# Agent type definitions
AGENT_TYPES = {
    'content': {'label': '内容生成Agent', 'desc': '自动生成口播文案、保险知识文案'},
    'hotspot': {'label': '热点分析Agent', 'desc': '分析热点事件，判断改编价值'},
    'customer': {'label': '客户分析Agent', 'desc': '分析客户成交概率、推荐产品'},
    'stock': {'label': '股票分析Agent', 'desc': '技术指标分析、策略复盘'},
    'knowledge': {'label': '知识整理Agent', 'desc': '分类、标签、知识图谱'},
    'reminder': {'label': '提醒Agent', 'desc': '客户跟进提醒、保单到期提醒'},
    'daily_report': {'label': '日报Agent', 'desc': '每日数据汇总、运营日报'},
    'data_collector': {'label': '数据采集Agent', 'desc': '全网爆款采集、热点监控'},
}


@bp.route('/api/agents')
def list_agents():
    conn = _db()
    rows = conn.execute(
        'SELECT * FROM ai_agent ORDER BY created_at DESC'
    ).fetchall()
    conn.close()
    return jsonify({'list': [dict(r) for r in rows]})


@bp.route('/api/agents/types')
def list_types():
    return jsonify({'types': [{'key': k, 'label': v['label'], 'desc': v['desc']} for k, v in AGENT_TYPES.items()]})


@bp.route('/api/agents', methods=['POST'])
def create_agent():
    data = request.get_json(silent=True) or {}
    conn = _db()
    cur = conn.execute(
        '''INSERT INTO ai_agent (name, agent_type, description, config_json, status)
           VALUES (%s, %s, %s, %s, 'idle')''',
        (data.get('name', ''), data.get('agent_type', 'content'),
         data.get('description', ''),
         json.dumps(data.get('config', {}), ensure_ascii=False))
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'id': new_id, 'message': 'Agent已创建'})


@bp.route('/api/agents/<int:id>', methods=['PUT'])
def update_agent(id):
    data = request.get_json(silent=True) or {}
    conn = _db()
    fields = []
    params = []
    for k in ['name', 'agent_type', 'description', 'config_json', 'status']:
        if k in data:
            fields.append(f'{k}=%s')
            val = data[k]
            if k == 'config_json' and isinstance(val, dict):
                val = json.dumps(val, ensure_ascii=False)
            params.append(val)
    if fields:
        params.append(id)
        conn.execute(f'UPDATE ai_agent SET {",".join(fields)} WHERE id=%s', params)
        conn.commit()
    conn.close()
    return jsonify({'message': 'Agent已更新'})


@bp.route('/api/agents/<int:id>', methods=['DELETE'])
def delete_agent(id):
    conn = _db()
    conn.execute('DELETE FROM ai_agent WHERE id=%s', (id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Agent已删除'})


@bp.route('/api/agents/<int:id>/run', methods=['POST'])
def run_agent(id):
    """Execute an agent's task. The agent type determines what it does."""
    from modules.ai_writer import call_llm
    conn = _db()
    row = conn.execute('SELECT * FROM ai_agent WHERE id=%s', (id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'not found'}), 404

    agent = dict(row)
    agent_type = agent.get('agent_type', 'content')

    # Update status to running
    conn.execute("UPDATE ai_agent SET status='running' WHERE id=%s", (id,))
    conn.commit()
    conn.close()

    try:
        # Build prompt based on agent type
        type_info = AGENT_TYPES.get(agent_type, {'label': '通用', 'desc': ''})
        config = json.loads(agent.get('config_json') or '{}')

        if agent_type == 'daily_report':
            # Generate daily report from database stats
            conn2 = _db()
            stats = {
                'customers': conn2.execute('SELECT COUNT(*) as c FROM customer').fetchone()['c'],
                'high_intent': conn2.execute("SELECT COUNT(*) as c FROM customer WHERE intention='high'").fetchone()['c'],
                'scripts': conn2.execute('SELECT COUNT(*) as c FROM script').fetchone()['c'],
                'videos_done': conn2.execute("SELECT COUNT(*) as c FROM video_task WHERE export_status='done'").fetchone()['c'],
                'hot_topics': conn2.execute('SELECT COUNT(*) as c FROM hot_topic').fetchone()['c'],
                'pending_reminders': conn2.execute("SELECT COUNT(*) as c FROM reminder WHERE status='pending'").fetchone()['c'],
            }
            conn2.close()
            prompt = f"""请生成今日运营日报：

数据概览：
- 客户总数：{stats['customers']}
- 高意向客户：{stats['high_intent']}
- 文案总数：{stats['scripts']}
- 已完成视频：{stats['videos_done']}
- 采集热点：{stats['hot_topics']}
- 待处理提醒：{stats['pending_reminders']}

请生成包含以下内容的日报：
1. 今日数据摘要
2. 重点事项提醒
3. 明日工作建议"""
        else:
            prompt = config.get('prompt', f"执行{type_info['label']}任务：{type_info['desc']}\n\n请给出具体的执行建议和方案。")

        resp, _tokens, _model = call_llm(prompt, system_prompt=f"你是{type_info['label']}，{type_info['desc']}")

        # Update agent status and last_run
        conn = _db()
        conn.execute(
            "UPDATE ai_agent SET status='idle', last_run=CURRENT_TIMESTAMP WHERE id=%s",
            (id,)
        )
        conn.commit()
        conn.close()

        return jsonify({'result': resp, 'message': f'{type_info["label"]}执行完成'})
    except Exception as e:
        conn = _db()
        conn.execute("UPDATE ai_agent SET status='error' WHERE id=%s", (id,))
        conn.commit()
        conn.close()
        return jsonify({'error': str(e)}), 500
