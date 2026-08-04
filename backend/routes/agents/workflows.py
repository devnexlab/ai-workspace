"""Workflow System routes - automate business processes (V1.2 new module)."""

from flask import Blueprint, request, jsonify
from config import get_db as _db
import json

bp = Blueprint('workflows', __name__)

# Workflow templates based on PRD
WORKFLOW_TEMPLATES = {
    'customer': {
        'name': '客户跟进流程',
        'steps': [
            {'step': 1, 'name': '新增客户', 'desc': '录入客户基本信息和画像'},
            {'step': 2, 'name': 'AI分析', 'desc': 'AI分析成交概率和推荐产品'},
            {'step': 3, 'name': '提醒联系', 'desc': '生成跟进提醒'},
            {'step': 4, 'name': '沟通', 'desc': '执行沟通并记录'},
            {'step': 5, 'name': '成交', 'desc': '完成交易'},
            {'step': 6, 'name': '售后', 'desc': '售后维护和持续经营'},
        ],
    },
    'content': {
        'name': '内容运营流程',
        'steps': [
            {'step': 1, 'name': '热点采集', 'desc': '全网采集爆款内容'},
            {'step': 2, 'name': '热点分析', 'desc': 'AI分析热点改编价值'},
            {'step': 3, 'name': '爆款筛选', 'desc': '筛选适合的热点'},
            {'step': 4, 'name': '生成文案', 'desc': 'AI生成约60秒口播文案'},
            {'step': 5, 'name': 'AI评分', 'desc': '预测播放/点赞/评论/转发'},
            {'step': 6, 'name': '人工确认', 'desc': '人工审核文案'},
            {'step': 7, 'name': '自动发布', 'desc': '多平台发布'},
            {'step': 8, 'name': '统计数据', 'desc': '跟踪发布效果'},
            {'step': 9, 'name': 'AI优化', 'desc': 'AI分析并优化策略'},
        ],
    },
    'stock': {
        'name': '股票研究流程',
        'steps': [
            {'step': 1, 'name': '市场收盘', 'desc': '等待收盘数据'},
            {'step': 2, 'name': '同步行情', 'desc': '同步当日行情数据'},
            {'step': 3, 'name': '技术指标计算', 'desc': '计算MACD/KDJ/RSI等指标'},
            {'step': 4, 'name': '条件筛选', 'desc': '按策略条件筛选股票'},
            {'step': 5, 'name': 'AI评分', 'desc': 'AI对候选股评分'},
            {'step': 6, 'name': '加入观察池', 'desc': '高分股票加入观察池'},
            {'step': 7, 'name': '生成日报', 'desc': 'AI生成研究日报'},
        ],
    },
}


@bp.route('/api/workflows')
def list_workflows():
    conn = _db()
    rows = conn.execute(
        'SELECT * FROM workflow ORDER BY created_at DESC'
    ).fetchall()
    conn.close()
    return jsonify({'list': [dict(r) for r in rows]})


@bp.route('/api/workflows/templates')
def list_templates():
    return jsonify({'templates': WORKFLOW_TEMPLATES})


@bp.route('/api/workflows', methods=['POST'])
def create_workflow():
    data = request.get_json(silent=True) or {}
    wf_type = data.get('workflow_type', 'customer')
    template = WORKFLOW_TEMPLATES.get(wf_type, {})

    name = data.get('name', template.get('name', '新工作流'))
    steps = data.get('steps', template.get('steps', []))

    conn = _db()
    cur = conn.execute(
        '''INSERT INTO workflow (name, workflow_type, steps_json, status, current_step, related_id)
           VALUES (%s, %s, %s, 'draft', 0, %s)''',
        (name, wf_type, json.dumps(steps, ensure_ascii=False),
         data.get('related_id'))
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'id': new_id, 'message': '工作流已创建'})


@bp.route('/api/workflows/<int:id>', methods=['GET'])
def get_workflow(id):
    conn = _db()
    row = conn.execute('SELECT * FROM workflow WHERE id=%s', (id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'not found'}), 404
    result = dict(row)
    if result.get('steps_json'):
        try:
            result['steps'] = json.loads(result['steps_json'])
        except Exception:
            result['steps'] = []
    else:
        result['steps'] = []
    return jsonify(result)


@bp.route('/api/workflows/<int:id>', methods=['PUT'])
def update_workflow(id):
    data = request.get_json(silent=True) or {}
    conn = _db()
    fields = []
    params = []
    for k in ['name', 'workflow_type', 'status', 'current_step', 'related_id']:
        if k in data:
            fields.append(f'{k}=%s')
            params.append(data[k])
    if 'steps' in data:
        fields.append('steps_json=%s')
        params.append(json.dumps(data['steps'], ensure_ascii=False))
    if fields:
        params.append(id)
        conn.execute(f'UPDATE workflow SET {",".join(fields)} WHERE id=%s', params)
        conn.commit()
    conn.close()
    return jsonify({'message': '工作流已更新'})


@bp.route('/api/workflows/<int:id>', methods=['DELETE'])
def delete_workflow(id):
    conn = _db()
    conn.execute('DELETE FROM workflow WHERE id=%s', (id,))
    conn.commit()
    conn.close()
    return jsonify({'message': '工作流已删除'})


@bp.route('/api/workflows/<int:id>/advance', methods=['POST'])
def advance_workflow(id):
    """Advance workflow to next step."""
    conn = _db()
    row = conn.execute('SELECT * FROM workflow WHERE id=%s', (id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'not found'}), 404

    wf = dict(row)
    steps = json.loads(wf.get('steps_json') or '[]')
    current = wf.get('current_step', 0)

    if current >= len(steps) - 1:
        # Already at last step, mark as completed
        conn.execute("UPDATE workflow SET status='completed', current_step=%s WHERE id=%s",
                     (current, id))
        conn.commit()
        conn.close()
        return jsonify({'message': '工作流已完成', 'completed': True})

    next_step = current + 1
    new_status = 'running' if next_step > 0 else 'draft'
    conn.execute("UPDATE workflow SET current_step=%s, status=%s WHERE id=%s",
                 (next_step, new_status, id))
    conn.commit()
    conn.close()

    return jsonify({
        'message': f'已推进到步骤 {next_step + 1}',
        'current_step': next_step,
        'step_name': steps[next_step].get('name', '') if next_step < len(steps) else '',
        'completed': False,
    })
