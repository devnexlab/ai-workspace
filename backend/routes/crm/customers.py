"""Customers routes - V1.2 enhanced with full lifecycle, AI analysis, reminders, ownership."""

from flask import Blueprint, request, jsonify
from config import get_db as _db
import json
from datetime import datetime, date, timedelta

bp = Blueprint('customers', __name__)

# V1.2: All editable customer fields
CUSTOMER_FIELDS = [
    'nickname', 'source_video', 'wechat', 'phone', 'tags', 'intention', 'remark',
    'age', 'occupation', 'income', 'family_info', 'region', 'source_channel',
    'personality_type', 'risk_preference', 'consumption_capacity',
    'insurance_needs', 'family_members', 'existing_policies', 'future_plans',
    'lifecycle_stage', 'birthday', 'policy_expiry_date', 'assigned_agent',
    'owner', 'deal_amount', 'policy_type',
]

# Lifecycle stages
LIFECYCLE_STAGES = ['new', 'appointment', 'tracking', 'proposal', 'deal', 'aftercare']
STAGE_LABELS = {
    'new': '新增客户', 'appointment': '约访', 'tracking': '跟踪中',
    'proposal': '方案沟通', 'deal': '成交', 'aftercare': '售后维护',
}
STAGE_COLORS = {
    'new': 'default', 'appointment': 'blue', 'tracking': 'orange',
    'proposal': 'purple', 'deal': 'green', 'aftercare': 'cyan',
}

# Personality types
PERSONALITY_LABELS = {
    'rational': '理性型', 'emotional': '感性型', 'cautious': '谨慎型',
    'decisive': '果断型', 'social': '社交型',
}


@bp.route('/api/customers')
def list_customers():
    conn = _db()
    page = int(request.args.get('page', 1))
    pageSize = int(request.args.get('pageSize', 20))
    intention = request.args.get('intention', '')
    lifecycle = request.args.get('lifecycle', '')
    owner = request.args.get('owner', '')
    q = request.args.get('q', '')

    where = []
    params = []
    if intention:
        where.append('intention=%s')
        params.append(intention)
    if lifecycle:
        where.append('lifecycle_stage=%s')
        params.append(lifecycle)
    if owner:
        where.append('owner=%s')
        params.append(owner)
    if q:
        where.append('(nickname LIKE %s OR wechat LIKE %s OR phone LIKE %s OR tags LIKE %s)')
        params.extend([f'%{q}%' for _ in range(4)])

    where_clause = ('WHERE ' + ' AND '.join(where)) if where else ''
    offset = (page - 1) * pageSize

    total = conn.execute(
        f'SELECT COUNT(*) as c FROM customer {where_clause}', params
    ).fetchone()['c']

    rows = conn.execute(
        f'SELECT * FROM customer {where_clause} ORDER BY created_at DESC LIMIT %s OFFSET %s',
        params + [pageSize, offset]
    ).fetchall()

    # Get lifecycle stage statistics
    stage_stats = {}
    for row in conn.execute(
        'SELECT lifecycle_stage, COUNT(*) as c FROM customer GROUP BY lifecycle_stage'
    ).fetchall():
        stage_stats[row['lifecycle_stage']] = row['c']

    conn.close()

    return jsonify({
        'list': [dict(r) for r in rows],
        'page': page,
        'pageSize': pageSize,
        'total': total,
        'stageStats': stage_stats,
        'stageLabels': STAGE_LABELS,
    })


@bp.route('/api/customers/<int:id>')
def get_customer(id):
    conn = _db()
    row = conn.execute('SELECT * FROM customer WHERE id=%s', (id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'not found'}), 404

    follows = conn.execute(
        'SELECT * FROM follow_record WHERE customer_id=%s ORDER BY follow_time DESC', (id,)
    ).fetchall()

    analysis = conn.execute(
        'SELECT * FROM customer_analysis WHERE customer_id=%s ORDER BY created_at DESC LIMIT 1', (id,)
    ).fetchone()

    reminders = conn.execute(
        'SELECT * FROM reminder WHERE customer_id=%s ORDER BY remind_date ASC', (id,)
    ).fetchall()

    # Get related workflow
    workflow = conn.execute(
        'SELECT * FROM workflow WHERE customer_id=%s ORDER BY created_at DESC LIMIT 1', (id,)
    ).fetchone()

    conn.close()
    result = dict(row)
    result['follow_records'] = [dict(f) for f in follows]
    result['ai_analysis'] = dict(analysis) if analysis else None
    result['reminders'] = [dict(r) for r in reminders]
    result['workflow'] = dict(workflow) if workflow else None
    return jsonify(result)


@bp.route('/api/customers', methods=['POST'])
def create_customer():
    data = request.get_json(silent=True) or {}
    conn = _db()
    fields = [f for f in CUSTOMER_FIELDS if f in data]
    if not fields:
        conn.close()
        return jsonify({'error': 'no fields'}), 400

    # Ensure lifecycle_stage defaults to 'new'
    if 'lifecycle_stage' not in fields:
        fields.append('lifecycle_stage')
        data['lifecycle_stage'] = 'new'

    placeholders = ', '.join(['%s'] * len(fields))
    field_names = ', '.join(fields)
    values = [data[f] for f in fields]

    cur = conn.execute(
        f'INSERT INTO customer ({field_names}) VALUES ({placeholders})',
        values
    )
    new_id = cur.lastrowid

    # Auto-create a customer workflow
    _create_customer_workflow(conn, new_id, data.get('nickname', ''))

    conn.commit()
    conn.close()

    assistant = {}
    try:
        from modules.assistants import run_assistant
        assistant = run_assistant('customer', customer_id=new_id, trigger='create') or {}
    except Exception as e:
        assistant = {'error': str(e)}

    return jsonify({
        'id': new_id,
        'message': '客户已添加，客户管理助手已给出下一步',
        'assistant': assistant,
    })


@bp.route('/api/customers/<int:id>', methods=['PUT'])
def update_customer(id):
    data = request.get_json(silent=True) or {}
    conn = _db()
    fields = []
    params = []
    for k in CUSTOMER_FIELDS:
        if k in data:
            fields.append(f'{k}=%s')
            params.append(data[k])

    # If lifecycle_stage is changing, update stage_entered_at
    if 'lifecycle_stage' in data:
        fields.append('stage_entered_at=CURRENT_TIMESTAMP')

    if fields:
        params.append(id)
        conn.execute(f'UPDATE customer SET {",".join(fields)} WHERE id=%s', params)
        conn.commit()
    conn.close()
    return jsonify({'message': '已更新'})


@bp.route('/api/customers/<int:id>', methods=['DELETE'])
def delete_customer(id):
    conn = _db()
    conn.execute('DELETE FROM customer WHERE id=%s', (id,))
    conn.execute('DELETE FROM follow_record WHERE customer_id=%s', (id,))
    conn.execute('DELETE FROM reminder WHERE customer_id=%s', (id,))
    conn.execute('DELETE FROM customer_analysis WHERE customer_id=%s', (id,))
    conn.execute('DELETE FROM workflow WHERE customer_id=%s', (id,))
    conn.commit()
    conn.close()
    return jsonify({'message': '已删除'})


# ---- Lifecycle Management ----

@bp.route('/api/customers/lifecycle-stages')
def get_lifecycle_stages():
    """Return lifecycle stage definitions."""
    return jsonify({
        'stages': LIFECYCLE_STAGES,
        'labels': STAGE_LABELS,
        'colors': STAGE_COLORS,
        'personalities': PERSONALITY_LABELS,
    })


@bp.route('/api/customers/owners')
def list_owners():
    """责任人列表，用于筛选「谁负责」。"""
    conn = _db()
    rows = conn.execute(
        """SELECT DISTINCT owner FROM customer
           WHERE owner IS NOT NULL AND owner != ''
           ORDER BY owner"""
    ).fetchall()
    conn.close()
    return jsonify({'list': [r['owner'] for r in rows]})


@bp.route('/api/customers/<int:id>/lifecycle', methods=['POST'])
def advance_lifecycle(id):
    """Advance or set customer lifecycle stage."""
    data = request.get_json(silent=True) or {}
    target_stage = data.get('stage', '')

    conn = _db()
    row = conn.execute('SELECT * FROM customer WHERE id=%s', (id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'not found'}), 404

    if target_stage and target_stage in LIFECYCLE_STAGES:
        conn.execute(
            "UPDATE customer SET lifecycle_stage=%s, stage_entered_at=CURRENT_TIMESTAMP WHERE id=%s",
            (target_stage, id)
        )
        if target_stage == 'deal':
            sets = ["deal_date=CURRENT_DATE"]
            params = []
            if data.get('deal_amount') not in (None, ''):
                sets.append('deal_amount=%s')
                params.append(data['deal_amount'])
            if data.get('policy_type'):
                sets.append('policy_type=%s')
                params.append(data['policy_type'])
            params.append(id)
            conn.execute(f"UPDATE customer SET {', '.join(sets)} WHERE id=%s", params)

        # 同步客户工作流步骤
        step_index = {s: i for i, s in enumerate(LIFECYCLE_STAGES)}.get(target_stage, 0)
        status = 'completed' if target_stage == 'aftercare' else 'running'
        conn.execute(
            """UPDATE workflow SET current_step=%s, status=%s
               WHERE customer_id=%s AND workflow_type='customer'""",
            (step_index, status, id)
        )
        conn.commit()
        conn.close()
        return jsonify({
            'message': f'阶段已更新为: {STAGE_LABELS.get(target_stage, target_stage)}',
            'stage': target_stage,
            'stage_label': STAGE_LABELS.get(target_stage, ''),
        })

    conn.close()
    return jsonify({'error': 'invalid stage'}), 400


# ---- 客户管理助手（多助手框架中的 customer） ----

@bp.route('/api/crm/assistant/board')
def assistant_board():
    """客户管理助手看板：阶段 + 下一步。"""
    from modules.assistants import get_assistant
    limit = int(request.args.get('limit', 50))
    assistant = get_assistant('customer')
    if not assistant:
        return jsonify({'list': [], 'error': 'customer assistant missing'}), 500
    return jsonify(assistant.board(limit=limit))


@bp.route('/api/customers/<int:id>/assistant', methods=['POST'])
def run_customer_assistant_route(id):
    """手动让客户管理助手再分析一次。"""
    from modules.assistants import run_assistant as dispatch
    result = dispatch('customer', customer_id=id, trigger='manual')
    if result.get('error'):
        return jsonify(result), 404 if 'not found' in result['error'] else 500
    return jsonify(result)


# ---- AI Customer Analysis ----

@bp.route('/api/customers/<int:id>/analyze', methods=['POST'])
def analyze_customer(id):
    """AI analyzes customer: deal probability, focus points, recommended products, etc."""
    from modules.ai_writer import call_llm
    conn = _db()
    row = conn.execute('SELECT * FROM customer WHERE id=%s', (id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'not found'}), 404

    follows = conn.execute(
        'SELECT * FROM follow_record WHERE customer_id=%s ORDER BY follow_time DESC LIMIT 10', (id,)
    ).fetchall()
    conn.close()

    customer = dict(row)
    follow_texts = '; '.join([f"[{f['follow_time']}] {f['content']}" for f in follows]) or '暂无'

    personality_label = PERSONALITY_LABELS.get(customer.get('personality_type', ''), '未知')
    stage_label = STAGE_LABELS.get(customer.get('lifecycle_stage', 'new'), '新增')

    prompt = f"""请分析以下保险客户信息，给出专业评估：

客户基本信息：
姓名：{customer.get('nickname','')}
年龄：{customer.get('age','')}
职业：{customer.get('occupation','')}
收入：{customer.get('income','')}
地区：{customer.get('region','')}
性格类型：{personality_label}
风险偏好：{customer.get('risk_preference','')}
消费能力：{customer.get('consumption_capacity','')}
保险需求：{customer.get('insurance_needs','')}
已有保单：{customer.get('existing_policies','')}
当前意向：{customer.get('intention','')}
生命周期阶段：{stage_label}

跟进记录：{follow_texts}

请以JSON格式返回分析结果：
{{
  "deal_probability": 0-100的数字,
  "focus_points": "客户最关注的点",
  "risk_assessment": "客户风险评估",
  "recommended_products": "适合推荐的产品",
  "next_step": "下一步建议",
  "personality_strategy": "针对该性格类型的沟通策略建议"
}}"""

    try:
        resp, _tokens, _model = call_llm(prompt, system_prompt="你是专业的保险客户分析师。")
        import re
        json_match = re.search(r'\{[\s\S]*\}', resp)
        if json_match:
            analysis_data = json.loads(json_match.group())
        else:
            analysis_data = {
                'deal_probability': 50,
                'focus_points': resp[:200],
                'risk_assessment': '无法解析',
                'recommended_products': '',
                'next_step': '',
                'personality_strategy': '',
            }

        conn = _db()
        conn.execute(
            '''INSERT INTO customer_analysis
               (customer_id, deal_probability, focus_points, risk_assessment, recommended_products, next_step, ai_analysis)
               VALUES (%s, %s, %s, %s, %s, %s, %s)''',
            (id, analysis_data.get('deal_probability', 50),
             analysis_data.get('focus_points', ''),
             analysis_data.get('risk_assessment', ''),
             analysis_data.get('recommended_products', ''),
             analysis_data.get('next_step', ''),
             json.dumps(analysis_data, ensure_ascii=False))
        )
        conn.commit()
        conn.close()
        return jsonify({'analysis': analysis_data, 'message': 'AI分析完成'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ---- Personality-based Strategy ----

@bp.route('/api/customers/<int:id>/strategy')
def get_personality_strategy(id):
    """Return personality-based follow-up strategy for the customer."""
    conn = _db()
    row = conn.execute('SELECT * FROM customer WHERE id=%s', (id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'not found'}), 404

    customer = dict(row)
    conn.close()

    personality = customer.get('personality_type', '')
    stage = customer.get('lifecycle_stage', 'new')

    strategies = {
        'rational': {
            'label': '理性型',
            'desc': '注重数据和逻辑，决策基于理性分析',
            'approach': '用数据说话，准备详细的对比表格、收益计算、概率分析。避免过多情感化语言。',
            'do': ['准备产品对比表（保费/保额/免责）', '展示理赔数据和公司评级', '提供ROI计算', '给出清晰的优缺点分析'],
            'dont': ['不要用情感故事打动', '不要催促决策', '不要模糊关键数据'],
            'best_time': '工作日上午，客户精力充沛时',
            'follow_up_freq': '每3-5天一次，每次提供新信息',
        },
        'emotional': {
            'label': '感性型',
            'desc': '注重感受和家庭，决策受情感驱动',
            'approach': '讲故事，分享真实理赔案例，强调家庭安全感和责任。用温暖的语言建立情感连接。',
            'do': ['分享真实的理赔案例', '强调保障对家人的意义', '关心客户家庭状况', '用故事和数据结合'],
            'dont': ['不要只堆数据', '不要冷冰冰地介绍条款', '不要忽视客户的情感需求'],
            'best_time': '晚间或周末，客户放松时',
            'follow_up_freq': '每2-3天一次，保持温度',
        },
        'cautious': {
            'label': '谨慎型',
            'desc': '注重安全性和确定性，决策谨慎缓慢',
            'approach': '强调产品安全性和公司实力，详细解读条款，提供充分的犹豫期保障说明。',
            'do': ['详细解读每一条款', '强调犹豫期和退保规则', '推荐保守型方案', '提供公司实力和资质证明'],
            'dont': ['不要催促决策', '不要推荐高风险产品', '不要简化重要信息'],
            'best_time': '工作日下午，客户有充足时间思考',
            'follow_up_freq': '每周一次，给足思考时间',
        },
        'decisive': {
            'label': '果断型',
            'desc': '决策快速，注重效率，不喜欢拖泥带水',
            'approach': '直接给出推荐方案和理由，避免过多选项。一句话说清核心优势。',
            'do': ['直接推荐最优方案', '给出明确的行动建议', '用一句话总结核心优势', '准备快速签约流程'],
            'dont': ['不要给太多选项', '不要长篇大论', '不要反复确认'],
            'best_time': '工作日任何时间，客户高效时段',
            'follow_up_freq': '快速推进，1-2天一次',
        },
        'social': {
            'label': '社交型',
            'desc': '注重人际关系，喜欢社交互动',
            'approach': '多聊生活话题，建立朋友关系，利用从众心理和社会认同。',
            'do': ['先聊生活再谈业务', '分享其他客户的好评', '寻找共同兴趣', '邀请参加线下活动'],
            'dont': ['不要一上来就推销', '不要忽视寒暄环节', '不要过于正式'],
            'best_time': '周末或非工作时间，轻松氛围',
            'follow_up_freq': '灵活，保持社交互动',
        },
    }

    strategy = strategies.get(personality, {
        'label': '未知',
        'desc': '请先设置客户性格类型',
        'approach': '根据客户实际情况灵活调整',
        'do': ['多了解客户需求', '观察客户反应'],
        'dont': ['不要急于推销'],
        'best_time': '工作时间',
        'follow_up_freq': '根据客户反馈调整',
    })

    strategy['personality'] = personality
    strategy['stage'] = stage
    strategy['stage_label'] = STAGE_LABELS.get(stage, '')
    strategy['customer_name'] = customer.get('nickname', '')

    return jsonify(strategy)


# ---- Reminder System ----

@bp.route('/api/customers/<int:id>/reminders')
def list_reminders(id):
    conn = _db()
    rows = conn.execute(
        'SELECT * FROM reminder WHERE customer_id=%s ORDER BY remind_date ASC', (id,)
    ).fetchall()
    conn.close()
    return jsonify({'list': [dict(r) for r in rows]})


@bp.route('/api/customers/<int:id>/reminders', methods=['POST'])
def create_reminder(id):
    data = request.get_json(silent=True) or {}
    conn = _db()
    cur = conn.execute(
        '''INSERT INTO reminder (customer_id, type, title, content, remind_date, status, priority, suggested_action)
           VALUES (%s, %s, %s, %s, %s, 'pending', %s, %s)''',
        (id, data.get('type', 'general'), data.get('title', ''),
         data.get('content', ''), data.get('remind_date', ''),
         data.get('priority', 'normal'), data.get('suggested_action', ''))
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'id': new_id, 'message': '提醒已创建'})


@bp.route('/api/reminders/<int:rid>', methods=['PUT'])
def update_reminder(rid):
    """更新提醒：完成 / 延期(snooze) / 改优先级。"""
    data = request.get_json(silent=True) or {}
    conn = _db()
    fields = []
    params = []
    if 'status' in data:
        fields.append('status=%s')
        params.append(data['status'])
    if 'remind_date' in data:
        fields.append('remind_date=%s')
        params.append(data['remind_date'])
    if 'priority' in data:
        fields.append('priority=%s')
        params.append(data['priority'])
    if 'suggested_action' in data:
        fields.append('suggested_action=%s')
        params.append(data['suggested_action'])
    # snooze_days: 延期 N 天并保持 pending
    if data.get('snooze_days'):
        try:
            days = int(data['snooze_days'])
            fields.append('remind_date=%s')
            params.append((date.today() + timedelta(days=days)).isoformat())
            if 'status' not in data:
                fields.append('status=%s')
                params.append('pending')
        except (TypeError, ValueError):
            pass
    if not fields:
        conn.close()
        return jsonify({'error': 'no fields'}), 400
    params.append(rid)
    conn.execute(f'UPDATE reminder SET {",".join(fields)} WHERE id=%s', params)
    conn.commit()
    conn.close()
    return jsonify({'message': '提醒已更新'})


@bp.route('/api/reminders', methods=['GET'])
def list_all_reminders():
    """List reminders；可按 status / owner / due(到期) 筛选。"""
    conn = _db()
    status = request.args.get('status', 'pending')
    owner = request.args.get('owner', '')
    due = request.args.get('due', '')  # today | overdue | upcoming

    where = ['r.status = %s']
    params = [status]
    if owner:
        where.append('c.owner = %s')
        params.append(owner)
    if due == 'today':
        where.append('r.remind_date = %s')
        params.append(date.today().isoformat())
    elif due == 'overdue':
        where.append('r.remind_date < %s')
        params.append(date.today().isoformat())
    elif due == 'upcoming':
        where.append('r.remind_date >= %s AND r.remind_date <= %s')
        params.append(date.today().isoformat())
        params.append((date.today() + timedelta(days=7)).isoformat())

    where_clause = ' AND '.join(where)
    rows = conn.execute(
        f"""SELECT r.*, c.nickname as customer_name, c.phone as customer_phone,
                  c.personality_type, c.owner, c.lifecycle_stage, c.wechat
           FROM reminder r LEFT JOIN customer c ON r.customer_id = c.id
           WHERE {where_clause}
           ORDER BY
             CASE r.priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 ELSE 2 END,
             r.remind_date ASC""",
        params
    ).fetchall()
    conn.close()
    return jsonify({'list': [dict(r) for r in rows], 'total': len(rows)})


@bp.route('/api/reminders/scan', methods=['POST'])
def scan_all_reminders():
    """扫描全部在途客户，批量生成智能提醒（供定时/手动刷新）。"""
    conn = _db()
    customers = conn.execute('SELECT id FROM customer').fetchall()
    conn.close()

    total = 0
    details = []
    for row in customers:
        result = _generate_reminders_for_customer(row['id'])
        if result.get('count'):
            total += result['count']
            details.append({'customer_id': row['id'], 'count': result['count']})

    return jsonify({
        'message': f'已扫描，新生成 {total} 条提醒',
        'count': total,
        'details': details,
    })


def _insert_reminder_dedup(conn, customer_id, r):
    exists = conn.execute(
        '''SELECT id FROM reminder
           WHERE customer_id=%s AND type=%s AND remind_date=%s AND title=%s AND status='pending'
           LIMIT 1''',
        (customer_id, r['type'], r['remind_date'], r['title'])
    ).fetchone()
    if exists:
        return False
    conn.execute(
        '''INSERT INTO reminder (customer_id, type, title, content, remind_date, status, priority, suggested_action)
           VALUES (%s, %s, %s, %s, %s, 'pending', %s, %s)''',
        (customer_id, r['type'], r['title'], r['content'], r['remind_date'],
         r.get('priority', 'normal'), r.get('suggested_action', ''))
    )
    return True


def _generate_reminders_for_customer(id):
    """核心：按客户阶段/沉默天数/生日/保单/性格生成提醒（带去重）。"""
    conn = _db()
    row = conn.execute('SELECT * FROM customer WHERE id=%s', (id,)).fetchone()
    if not row:
        conn.close()
        return {'error': 'not found', 'count': 0}

    customer = dict(row)
    reminders = []
    today = date.today()
    personality = customer.get('personality_type', '')
    stage = customer.get('lifecycle_stage', 'new')
    owner_tip = f'责任人：{customer.get("owner") or "未指定"}'

    if customer.get('last_follow_time'):
        try:
            last_date = datetime.strptime(str(customer['last_follow_time'])[:10], '%Y-%m-%d').date()
            days = (today - last_date).days
            threshold = {'new': 2, 'appointment': 1, 'tracking': 3, 'proposal': 2, 'deal': 7, 'aftercare': 30}
            limit = threshold.get(stage, 7)
            if days >= limit:
                priority = 'urgent' if days >= limit * 2 else 'high'
                reminders.append({
                    'type': 'silent',
                    'title': f'{customer["nickname"]}已{days}天未联系（{STAGE_LABELS.get(stage, "")}阶段）',
                    'content': f'{owner_tip}。当前阶段建议{limit}天内联系，已超时{days - limit}天',
                    'remind_date': today.isoformat(),
                    'priority': priority,
                    'suggested_action': _personality_action(personality, stage),
                })
        except Exception:
            pass
    elif stage == 'new':
        reminders.append({
            'type': 'follow_up',
            'title': f'新客户{customer["nickname"]}尚未联系',
            'content': f'{owner_tip}。新客户应在24小时内首次联系',
            'remind_date': today.isoformat(),
            'priority': 'urgent',
            'suggested_action': '尽快首次联系，了解基本需求',
        })

    if customer.get('birthday'):
        try:
            bd = datetime.strptime(str(customer['birthday'])[:10], '%Y-%m-%d').date()
            bd_this_year = bd.replace(year=today.year)
            if bd_this_year < today:
                bd_this_year = bd.replace(year=today.year + 1)
            days_to_birthday = (bd_this_year - today).days
            if days_to_birthday <= 30:
                reminders.append({
                    'type': 'birthday',
                    'title': f'{customer["nickname"]}生日即将到来（{days_to_birthday}天后）',
                    'content': f'{owner_tip}。生日：{customer["birthday"]}，提前准备祝福',
                    'remind_date': (today + timedelta(days=max(0, days_to_birthday - 7))).isoformat(),
                    'priority': 'high' if days_to_birthday <= 7 else 'normal',
                    'suggested_action': '发送生日祝福，可附赠小礼物，强化客户关系',
                })
        except Exception:
            pass

    if customer.get('policy_expiry_date'):
        try:
            exp = datetime.strptime(str(customer['policy_expiry_date'])[:10], '%Y-%m-%d').date()
            days_to_exp = (exp - today).days
            if 0 <= days_to_exp <= 60:
                reminders.append({
                    'type': 'policy_expiry',
                    'title': f'{customer["nickname"]}保单即将到期（{days_to_exp}天后）',
                    'content': f'{owner_tip}。到期日：{customer["policy_expiry_date"]}，建议提前续保',
                    'remind_date': (today + timedelta(days=max(0, days_to_exp - 14))).isoformat(),
                    'priority': 'urgent' if days_to_exp <= 14 else 'high',
                    'suggested_action': '准备续保方案，可推荐升级产品或附加险',
                })
        except Exception:
            pass

    if stage == 'deal':
        deal_date = customer.get('deal_date')
        if deal_date:
            try:
                dd = datetime.strptime(str(deal_date)[:10], '%Y-%m-%d').date()
                days_since_deal = (today - dd).days
                if 5 <= days_since_deal <= 10:
                    reminders.append({
                        'type': 'aftercare',
                        'title': f'{customer["nickname"]}成交后回访（成交{days_since_deal}天）',
                        'content': f'{owner_tip}。成交后回访，确认保单生效，按性格策略维护',
                        'remind_date': today.isoformat(),
                        'priority': 'high',
                        'suggested_action': _personality_action(personality, 'aftercare'),
                    })
            except Exception:
                pass
    elif stage == 'aftercare':
        stage_entered = customer.get('stage_entered_at')
        if stage_entered:
            try:
                se = datetime.strptime(str(stage_entered)[:10], '%Y-%m-%d').date()
                days_in_aftercare = (today - se).days
                if days_in_aftercare > 0 and days_in_aftercare % 90 < 7 and days_in_aftercare >= 85:
                    reminders.append({
                        'type': 'aftercare',
                        'title': f'{customer["nickname"]}季度回访',
                        'content': f'{owner_tip}。进入售后已近90天，进行季度回访',
                        'remind_date': today.isoformat(),
                        'priority': 'normal',
                        'suggested_action': _personality_action(personality, 'aftercare')
                            or '了解使用体验，发掘家庭其他保障需求，请求转介绍',
                    })
            except Exception:
                pass

    if customer.get('intention') == 'high' and stage in ('new', 'appointment'):
        reminders.append({
            'type': 'high_intent',
            'title': f'高意向客户{customer["nickname"]}需要推进',
            'content': f'{owner_tip}。意向高但处于{STAGE_LABELS.get(stage, "")}阶段，建议尽快推进',
            'remind_date': today.isoformat(),
            'priority': 'urgent',
            'suggested_action': _personality_action(personality, stage) or '立即联系，制定沟通策略',
        })

    inserted = []
    for r in reminders:
        if _insert_reminder_dedup(conn, id, r):
            inserted.append(r)
    conn.commit()
    conn.close()

    return {
        'reminders': inserted,
        'count': len(inserted),
        'message': f'生成了{len(inserted)}条智能提醒',
        'customer_stage': stage,
        'personality': personality,
    }


@bp.route('/api/customers/<int:id>/auto-remind', methods=['POST'])
def auto_generate_reminders(id):
    """Generate smart reminders based on customer data, lifecycle stage, and personality."""
    result = _generate_reminders_for_customer(id)
    if result.get('error'):
        return jsonify(result), 404
    return jsonify(result)


def _personality_action(personality, stage):
    """Return suggested action based on personality and stage."""
    strategies = {
        'rational': {
            'tracking': '准备数据对比表，展示ROI和保障范围对比',
            'proposal': '用表格列出不同方案的保费/保额/免责条款对比',
            'aftercare': '定期发送理赔数据和市场分析报告',
        },
        'emotional': {
            'tracking': '讲故事，分享真实理赔案例，强调家庭安全感',
            'proposal': '重点讲解保障对家人的意义，用情感化语言',
            'aftercare': '节日问候，关心家庭成员近况',
        },
        'cautious': {
            'tracking': '强调产品安全性和公司实力，提供详细条款解读',
            'proposal': '推荐保守型方案，详细说明犹豫期和退保规则',
            'aftercare': '定期确认保单状态，及时解答任何疑虑',
        },
        'decisive': {
            'tracking': '直接给出推荐方案和理由，避免过多选项',
            'proposal': '一句话总结核心优势，给出明确建议',
            'aftercare': '简洁高效地沟通，不过多打扰',
        },
        'social': {
            'tracking': '多聊生活话题，建立朋友关系，寻找共同点',
            'proposal': '分享其他客户的好评和推荐，制造从众效应',
            'aftercare': '邀请参加线下活动，请求转介绍',
        },
    }
    return strategies.get(personality, {}).get(stage, '根据客户情况灵活调整沟通策略')


def _create_customer_workflow(conn, customer_id, customer_name):
    """Auto-create a customer follow-up workflow."""
    steps = [
        {'step': 1, 'name': '新增客户', 'desc': '录入客户基本信息和画像', 'stage': 'new'},
        {'step': 2, 'name': '约访', 'desc': '首次联系，预约沟通时间', 'stage': 'appointment'},
        {'step': 3, 'name': '跟踪跟进', 'desc': '持续沟通，了解需求，建立信任', 'stage': 'tracking'},
        {'step': 4, 'name': '方案沟通', 'desc': '推荐保险方案，解答疑问', 'stage': 'proposal'},
        {'step': 5, 'name': '成交', 'desc': '完成签约和付款', 'stage': 'deal'},
        {'step': 6, 'name': '售后维护', 'desc': '保单送达、回访、续保提醒、转介绍', 'stage': 'aftercare'},
    ]
    conn.execute(
        '''INSERT INTO workflow (name, workflow_type, steps_json, status, current_step, customer_id)
           VALUES (%s, 'customer', %s, 'running', 0, %s)''',
        (f'{customer_name} - 客户跟进流程', json.dumps(steps, ensure_ascii=False), customer_id)
    )
