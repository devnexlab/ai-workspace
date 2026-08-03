"""AI Agent / 多助手中心：登记、系统提示词与任务执行。

配置只需填写系统提示词（纯文本）。
执行时用该提示词驱动对应业务任务（客户跟进 / 采写拍 / 发布）。
"""

from flask import Blueprint, request, jsonify
from config import get_db as _db
import json

bp = Blueprint('agents', __name__)

AGENT_TYPES = {
    'customer': {
        'label': '客户管理',
        'desc': '把客户跟进、阶段推进、话术准备等重复工作交给助手',
    },
    'operations': {
        'label': '运营管理',
        'desc': '采热点、写文案、做视频等日常运营重复操作',
    },
    'publish': {
        'label': '发布管理',
        'desc': '创建发布、失败重试、多平台发布等重复操作',
    },
}


def _normalize_type(agent_type: str) -> str:
    if agent_type == 'content':
        return 'operations'
    return agent_type or 'customer'


@bp.route('/api/assistants')
def list_ai_assistants_api():
    from modules.assistants import list_ai_assistants
    return jsonify({'list': list_ai_assistants()})


@bp.route('/api/assistants/<key>/tasks')
def assistant_tasks(key):
    """AI助手页：可执行工作流任务（无统计看板）。"""
    from modules.assistants import get_assistant
    key = _normalize_type(key)
    assistant = get_assistant(key)
    if not assistant:
        return jsonify({'error': f'unknown assistant: {key}'}), 404
    if hasattr(assistant, 'tasks'):
        return jsonify(assistant.tasks())
    board = assistant.board() or {}
    return jsonify({'assistant': key, 'tasks': board.get('tasks') or [], 'intro': board.get('intro') or ''})


@bp.route('/api/assistants/<key>/run', methods=['POST'])
def run_builtin_assistant(key):
    from modules.assistants import run_assistant
    key = _normalize_type(key)
    data = request.get_json(silent=True) or {}
    result = run_assistant(key, **data)
    if result.get('error') and 'unknown' in str(result.get('error')):
        return jsonify(result), 404
    return jsonify(result)


@bp.route('/api/assistants/<key>/board')
def assistant_board(key):
    """兼容旧接口：转为 tasks 结构。"""
    from modules.assistants import get_assistant
    key = _normalize_type(key)
    assistant = get_assistant(key)
    if not assistant:
        return jsonify({'error': f'unknown assistant: {key}'}), 404
    if hasattr(assistant, 'tasks'):
        return jsonify(assistant.tasks())
    board = assistant.board()
    if board is None:
        return jsonify({'error': f'{key} has no board'}), 404
    return jsonify(board)


@bp.route('/api/agents')
def list_agents():
    from modules.assistants import ensure_default_agents
    from modules.assistants.prompts import extract_system_prompt, DEFAULT_SYSTEM_PROMPTS
    ensure_default_agents()
    conn = _db()
    rows = conn.execute('SELECT * FROM ai_agent ORDER BY created_at DESC').fetchall()
    conn.close()
    out = []
    for r in rows:
        agent = dict(r)
        agent['agent_type'] = _normalize_type(agent.get('agent_type'))
        agent['system_prompt'] = extract_system_prompt(agent)
        if not (agent.get('system_prompt') or '').strip():
            agent['system_prompt'] = DEFAULT_SYSTEM_PROMPTS.get(agent['agent_type'], '')
        out.append(agent)
    return jsonify({'list': out})


@bp.route('/api/agents/types')
def list_types():
    from modules.assistants.prompts import DEFAULT_SYSTEM_PROMPTS
    types = []
    for key, meta in AGENT_TYPES.items():
        types.append({
            'key': key,
            'label': meta['label'],
            'desc': meta['desc'],
            'default_system_prompt': DEFAULT_SYSTEM_PROMPTS.get(key, ''),
            'registered': True,
            'enabled': True,
        })
    return jsonify({'types': types})


@bp.route('/api/agents', methods=['POST'])
def create_agent():
    from modules.assistants.prompts import DEFAULT_SYSTEM_PROMPTS
    data = request.get_json(silent=True) or {}
    agent_type = _normalize_type(data.get('agent_type', 'customer'))
    if agent_type not in AGENT_TYPES:
        return jsonify({'error': f'仅支持类型: {", ".join(AGENT_TYPES.keys())}'}), 400

    type_meta = AGENT_TYPES[agent_type]
    name = (data.get('name') or f"{type_meta['label']}助手").strip()
    desc = (data.get('description') or type_meta['desc']).strip()
    system_prompt = (data.get('system_prompt') or DEFAULT_SYSTEM_PROMPTS.get(agent_type, '')).strip()

    conn = _db()
    cur = conn.execute(
        '''INSERT INTO ai_agent (name, agent_type, description, config_json, system_prompt, status)
           VALUES (%s, %s, %s, %s, %s, 'idle')''',
        (name, agent_type, desc, '{}', system_prompt)
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'id': new_id, 'message': f'已创建，可在「AI助手」中使用：{name}'})


@bp.route('/api/agents/<int:id>', methods=['PUT'])
def update_agent(id):
    data = request.get_json(silent=True) or {}
    conn = _db()
    fields = []
    params = []
    mapping = {
        'name': 'name',
        'agent_type': 'agent_type',
        'description': 'description',
        'system_prompt': 'system_prompt',
        'status': 'status',
    }
    for key, col in mapping.items():
        if key not in data:
            continue
        val = data[key]
        if key == 'agent_type':
            val = _normalize_type(val)
            if val not in AGENT_TYPES:
                conn.close()
                return jsonify({'error': f'仅支持类型: {", ".join(AGENT_TYPES.keys())}'}), 400
        fields.append(f'{col}=%s')
        params.append(val)
    # 兼容旧前端若仍传 config_json：忽略 JSON，若含 prompt 则写入 system_prompt
    if 'config_json' in data and 'system_prompt' not in data:
        raw = data['config_json']
        prompt = ''
        if isinstance(raw, dict):
            prompt = (raw.get('system_prompt') or raw.get('prompt') or '').strip()
        elif isinstance(raw, str) and raw.strip().startswith('{'):
            try:
                cfg = json.loads(raw)
                prompt = (cfg.get('system_prompt') or cfg.get('prompt') or '').strip()
            except Exception:
                prompt = raw.strip()
        elif isinstance(raw, str):
            prompt = raw.strip()
        if prompt:
            fields.append('system_prompt=%s')
            params.append(prompt)
    if fields:
        params.append(id)
        conn.execute(f'UPDATE ai_agent SET {",".join(fields)} WHERE id=%s', params)
        conn.commit()
    conn.close()
    return jsonify({'message': '助手已更新'})


@bp.route('/api/agents/<int:id>', methods=['DELETE'])
def delete_agent(id):
    conn = _db()
    conn.execute('DELETE FROM ai_agent WHERE id=%s', (id,))
    conn.commit()
    conn.close()
    return jsonify({'message': '助手已删除'})


@bp.route('/api/agents/<int:id>/run', methods=['POST'])
def run_agent(id):
    """按系统提示词执行该助手对应的业务任务。"""
    from modules.assistants import get_assistant, run_assistant
    from modules.assistants.prompts import extract_system_prompt

    conn = _db()
    row = conn.execute('SELECT * FROM ai_agent WHERE id=%s', (id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'not found'}), 404

    agent = dict(row)
    agent_type = _normalize_type(agent.get('agent_type', 'customer'))
    system_prompt = extract_system_prompt(agent, agent_type)
    conn.execute("UPDATE ai_agent SET status='running' WHERE id=%s", (id,))
    conn.commit()
    conn.close()

    payload = request.get_json(silent=True) or {}
    type_info = AGENT_TYPES.get(agent_type, {'label': '通用', 'desc': ''})

    try:
        if not get_assistant(agent_type):
            raise Exception(f'未注册助手类型: {agent_type}')

        result = run_assistant(
            agent_type,
            trigger=payload.get('trigger') or 'manual',
            task=payload.get('task') or '',
            system_prompt=system_prompt,
            customer_id=payload.get('customer_id'),
            extra=payload,
        )

        # 可读输出（给 Agent 中心结果弹窗 / AI助手）
        output = _format_run_output(result)
        conn = _db()
        conn.execute(
            '''UPDATE ai_agent
               SET status='idle', last_run=CURRENT_TIMESTAMP, last_result=%s
               WHERE id=%s''',
            (output[:4000], id),
        )
        conn.commit()
        conn.close()

        return jsonify({
            'result': result,
            'output': output,
            'message': f'{type_info["label"]}助手已执行',
            'assistant': agent_type,
            'system_prompt_used': system_prompt[:200],
        })
    except Exception as e:
        conn = _db()
        conn.execute("UPDATE ai_agent SET status='error' WHERE id=%s", (id,))
        conn.commit()
        conn.close()
        return jsonify({'error': str(e)}), 500


def _format_run_output(result) -> str:
    if result is None:
        return '无输出'
    if isinstance(result, str):
        return result
    if not isinstance(result, dict):
        return str(result)
    if result.get('skipped'):
        return result.get('reason') or '已跳过'
    if result.get('error'):
        return f"失败：{result['error']}"
    lines = []
    if result.get('summary'):
        lines.append(str(result['summary']))
    actions = result.get('next_actions') or []
    if actions:
        lines.append('下一步：')
        for i, a in enumerate(actions, 1):
            lines.append(f'{i}. {a}')
    if result.get('talk_tips'):
        lines.append(f"要点：{result['talk_tips']}")
    if result.get('message'):
        lines.append(str(result['message']))
    if result.get('output'):
        lines.append(str(result['output']))
    return '\n'.join(lines) if lines else json.dumps(result, ensure_ascii=False, indent=2)[:2000]
