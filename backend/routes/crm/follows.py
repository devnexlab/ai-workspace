"""Follow records - 跟进记录 + 智能录入 / 快捷一键。"""

from flask import Blueprint, request, jsonify
from config import get_db as _db
from datetime import date, timedelta
import json
import re

bp = Blueprint('follows', __name__)

LIFECYCLE_STAGES = ['new', 'appointment', 'tracking', 'proposal', 'deal', 'aftercare']
STAGE_LABELS = {
    'new': '新增客户',
    'appointment': '约访',
    'tracking': '跟踪中',
    'proposal': '方案沟通',
    'deal': '成交',
    'aftercare': '售后维护',
}
STAGE_STEP_INDEX = {s: i for i, s in enumerate(LIFECYCLE_STAGES)}

FOLLOW_RESULT_VALUES = [
    'appointment_scheduled', 'interested', 'proposal_sent',
    'deal_closed', 'policy_delivered', 'no_answer', 'postponed', 'general', '',
]

QUICK_TEMPLATES = [
    {'key': 'no_answer', 'label': '未接通', 'method': 'phone', 'follow_result': 'no_answer',
     'content': '电话未接通，稍后再联系。'},
    {'key': 'wechat_left', 'label': '微信留言', 'method': 'wechat', 'follow_result': 'general',
     'content': '已发微信留言，等待客户回复。'},
    {'key': 'appointment', 'label': '已约访', 'method': 'phone', 'follow_result': 'appointment_scheduled',
     'content': '已与客户约好面谈时间。', 'need_next_time': True},
    {'key': 'interested', 'label': '有兴趣', 'method': 'wechat', 'follow_result': 'interested',
     'content': '客户表现出兴趣，继续跟进方案。'},
    {'key': 'proposal', 'label': '已发方案', 'method': 'wechat', 'follow_result': 'proposal_sent',
     'content': '已发送保险方案，等待客户反馈。'},
    {'key': 'offline_done', 'label': '面谈结束', 'method': 'offline', 'follow_result': 'interested',
     'content': '线下见面沟通完毕，客户意向待确认。'},
    {'key': 'deal', 'label': '已成交', 'method': 'offline', 'follow_result': 'deal_closed',
     'content': '客户已签约成交。', 'need_deal': True},
    {'key': 'policy', 'label': '保单送达', 'method': 'phone', 'follow_result': 'policy_delivered',
     'content': '保单已送达并完成讲解。'},
]


@bp.route('/api/follows')
def list_follows():
    conn = _db()
    customer_id = request.args.get('customer_id', '')
    where = ''
    params = []
    if customer_id:
        where = 'WHERE customer_id=%s'
        params.append(int(customer_id))
    rows = conn.execute(
        f'SELECT * FROM follow_record {where} ORDER BY follow_time DESC', params
    ).fetchall()
    conn.close()
    return jsonify({'list': [dict(r) for r in rows]})


@bp.route('/api/follows', methods=['POST'])
def create_follow():
    data = request.get_json(silent=True) or {}
    result, err, code = _create_follow_internal(data)
    if err:
        return jsonify({'error': err}), code
    return jsonify(result)


@bp.route('/api/follows/quick-templates')
def list_quick_templates():
    return jsonify({'list': QUICK_TEMPLATES})


@bp.route('/api/follows/smart-parse', methods=['POST'])
def smart_parse_follow():
    """粘贴微信/口述/通话摘要 → 结构化字段（不入库）。"""
    data = request.get_json(silent=True) or {}
    parsed, err = _smart_parse_text(data)
    if err:
        code = 400 if '请粘贴' in err else 500
        return jsonify({'error': err}), code
    parsed['message'] = '已解析，请确认后保存'
    return jsonify(parsed)


@bp.route('/api/follows/smart', methods=['POST'])
def smart_create_follow():
    """有结构化字段则直接保存；否则先解析原文再保存。"""
    data = request.get_json(silent=True) or {}
    customer_id = data.get('customer_id')
    if not customer_id:
        return jsonify({'error': 'customer_id required'}), 400

    if data.get('content'):
        payload = {
            'customer_id': customer_id,
            'content': data['content'],
            'follow_result': data.get('follow_result') if data.get('follow_result') != 'general' else '',
            'method': data.get('method', 'wechat'),
            'next_time': data.get('next_time', ''),
            'operator': data.get('operator', ''),
            'deal_amount': data.get('deal_amount', ''),
            'policy_type': data.get('policy_type', ''),
            'deal_intention': data.get('deal_intention', ''),
            'follow_stage': data.get('follow_stage', ''),
        }
    else:
        parsed, err = _smart_parse_text({
            'text': data.get('text', ''),
            'customer_id': customer_id,
            'operator': data.get('operator', ''),
        })
        if err:
            return jsonify({'error': err}), 500
        payload = {
            'customer_id': customer_id,
            'content': parsed['content'],
            'follow_result': '' if parsed['follow_result'] == 'general' else parsed['follow_result'],
            'method': parsed['method'],
            'next_time': parsed['next_time'],
            'operator': parsed['operator'] or data.get('operator', ''),
            'deal_amount': parsed.get('deal_amount', ''),
            'policy_type': parsed.get('policy_type', ''),
            'deal_intention': parsed.get('deal_intention', ''),
        }

    result, err, code = _create_follow_internal(payload)
    if err:
        return jsonify({'error': err}), code
    result['parsed'] = payload
    return jsonify(result)


@bp.route('/api/follows/quick', methods=['POST'])
def quick_create_follow():
    """一键快捷跟进。"""
    data = request.get_json(silent=True) or {}
    customer_id = data.get('customer_id')
    template_key = data.get('template')
    if not customer_id or not template_key:
        return jsonify({'error': 'customer_id and template required'}), 400

    tpl = next((t for t in QUICK_TEMPLATES if t['key'] == template_key), None)
    if not tpl:
        return jsonify({'error': 'unknown template'}), 400

    note = (data.get('note') or '').strip()
    content = f"{tpl['content']} {note}".strip() if note else tpl['content']
    fr = tpl['follow_result']
    payload = {
        'customer_id': customer_id,
        'content': content,
        'follow_result': '' if fr == 'general' else fr,
        'method': data.get('method') or tpl['method'],
        'operator': data.get('operator', ''),
        'next_time': data.get('next_time', ''),
        'deal_amount': data.get('deal_amount', ''),
        'policy_type': data.get('policy_type', ''),
    }
    result, err, code = _create_follow_internal(payload)
    if err:
        return jsonify({'error': err}), code
    return jsonify(result)


@bp.route('/api/follows/<int:id>', methods=['DELETE'])
def delete_follow(id):
    conn = _db()
    conn.execute('DELETE FROM follow_record WHERE id=%s', (id,))
    conn.commit()
    conn.close()
    return jsonify({'message': '已删除'})


# ---- helpers ----

def _smart_parse_text(data):
    raw_text = (data.get('text') or '').strip()
    if not raw_text:
        return None, '请粘贴沟通内容或口述纪要'

    customer_ctx = ''
    customer_id = data.get('customer_id')
    if customer_id:
        conn = _db()
        row = conn.execute('SELECT * FROM customer WHERE id=%s', (customer_id,)).fetchone()
        conn.close()
        if row:
            c = dict(row)
            customer_ctx = (
                f"客户姓名：{c.get('nickname','')}\n"
                f"当前阶段：{STAGE_LABELS.get(c.get('lifecycle_stage','new'),'')}\n"
                f"责任人：{c.get('owner') or c.get('assigned_agent') or ''}\n"
                f"性格：{c.get('personality_type') or '未知'}\n"
                f"意向：{c.get('intention') or ''}\n"
            )

    today = date.today().isoformat()
    prompt = f"""你是保险客户跟进助手。根据沟通原文提取结构化跟进信息。

今天日期：{today}
{customer_ctx}
沟通原文（微信聊天 / 通话摘要 / 面谈笔记 / 一句话口述）：
---
{raw_text[:4000]}
---

只返回 JSON：
{{
  "content": "跟进纪要（2-5句）",
  "follow_result": "appointment_scheduled|interested|proposal_sent|deal_closed|policy_delivered|no_answer|postponed|general",
  "method": "wechat|phone|offline|other",
  "next_time": "YYYY-MM-DD HH:mm:ss 或空字符串；明天/后天请换算",
  "operator": "跟进人或空",
  "deal_amount": "",
  "policy_type": "",
  "deal_intention": "",
  "confidence": 80
}}

规则：约见面→appointment_scheduled；有兴趣→interested；已发方案→proposal_sent；
签约成交→deal_closed；保单送达→policy_delivered；未接→no_answer；推迟→postponed；其他→general。
微信→wechat，电话→phone，见面→offline。
"""

    try:
        from modules.ai_writer import call_llm
        resp, _tokens, _model = call_llm(
            prompt,
            system_prompt='你只输出合法 JSON，不要解释。',
            temperature=0.2,
            max_tokens=800,
        )
        match = re.search(r'\{[\s\S]*\}', resp or '')
        if not match:
            return None, 'AI 未能解析出结构化结果'
        parsed = json.loads(match.group())
    except Exception as e:
        return None, f'智能解析失败: {e}'

    result = parsed.get('follow_result') or 'general'
    if result not in FOLLOW_RESULT_VALUES:
        result = 'general'
    method = parsed.get('method') or 'wechat'
    if method not in ('wechat', 'phone', 'offline', 'other'):
        method = 'other'
    next_time = str(parsed.get('next_time') or '').strip()
    if next_time and len(next_time) == 10:
        next_time += ' 10:00:00'

    return {
        'content': (parsed.get('content') or raw_text[:500]).strip(),
        'follow_result': result,
        'method': method,
        'next_time': next_time,
        'operator': (parsed.get('operator') or data.get('operator') or '').strip(),
        'deal_amount': str(parsed.get('deal_amount') or '').strip(),
        'policy_type': str(parsed.get('policy_type') or '').strip(),
        'deal_intention': str(parsed.get('deal_intention') or '').strip(),
        'confidence': int(parsed.get('confidence') or 70),
    }, None


def _create_follow_internal(data):
    if not data.get('customer_id') or not data.get('content'):
        return None, 'customer_id and content required', 400

    conn = _db()
    follow_stage = data.get('follow_stage', '')
    follow_result = data.get('follow_result', '') or ''
    operator = data.get('operator', '')
    method = data.get('method', '')

    customer = conn.execute(
        'SELECT * FROM customer WHERE id=%s', (data['customer_id'],)
    ).fetchone()
    if not customer:
        conn.close()
        return None, 'customer not found', 404

    c = dict(customer)
    current_stage = c.get('lifecycle_stage', 'new')
    if not follow_stage:
        follow_stage = current_stage

    if not operator:
        operator = c.get('owner') or c.get('assigned_agent') or ''
    if operator and not c.get('owner'):
        conn.execute('UPDATE customer SET owner=%s WHERE id=%s', (operator, data['customer_id']))
        c['owner'] = operator

    cur = conn.execute(
        '''INSERT INTO follow_record
           (customer_id, content, next_time, follow_stage, follow_result, operator, method, deal_intention)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)''',
        (data['customer_id'], data['content'], data.get('next_time', ''),
         follow_stage, follow_result, operator, method, data.get('deal_intention', ''))
    )
    new_id = cur.lastrowid

    conn.execute(
        "UPDATE customer SET last_follow_time=to_char(CURRENT_TIMESTAMP, 'YYYY-MM-DD HH24:MI:SS') WHERE id=%s",
        (data['customer_id'],)
    )

    new_stage = None
    if follow_result == 'appointment_scheduled' and current_stage == 'new':
        new_stage = 'appointment'
    elif follow_result == 'interested' and current_stage in ('new', 'appointment'):
        new_stage = 'tracking'
    elif follow_result == 'proposal_sent' and current_stage in ('tracking', 'appointment', 'new'):
        new_stage = 'proposal'
    elif follow_result == 'deal_closed':
        new_stage = 'deal'
        sets = ["deal_date=CURRENT_DATE", "lifecycle_stage='deal'", "stage_entered_at=CURRENT_TIMESTAMP"]
        params = []
        if data.get('deal_amount') not in (None, ''):
            sets.append('deal_amount=%s')
            params.append(data['deal_amount'])
        if data.get('policy_type'):
            sets.append('policy_type=%s')
            params.append(data['policy_type'])
        params.append(data['customer_id'])
        conn.execute(f"UPDATE customer SET {', '.join(sets)} WHERE id=%s", params)
        c['lifecycle_stage'] = 'deal'
    elif follow_result == 'policy_delivered' and current_stage in ('deal', 'aftercare'):
        new_stage = 'aftercare'

    if new_stage and new_stage != 'deal':
        _advance_stage(conn, data['customer_id'], new_stage)
        c['lifecycle_stage'] = new_stage
        _sync_workflow(conn, data['customer_id'], new_stage)
    elif new_stage == 'deal':
        _sync_workflow(conn, data['customer_id'], 'deal')

    _auto_generate_next_reminder(conn, data['customer_id'], data, follow_result, c)
    conn.commit()
    conn.close()
    return {
        'id': new_id,
        'message': '跟进记录已添加',
        'lifecycle_stage': c.get('lifecycle_stage'),
        'stage_label': STAGE_LABELS.get(c.get('lifecycle_stage', ''), ''),
    }, None, 200


def _advance_stage(conn, customer_id, new_stage):
    conn.execute(
        "UPDATE customer SET lifecycle_stage=%s, stage_entered_at=CURRENT_TIMESTAMP WHERE id=%s",
        (new_stage, customer_id)
    )


def _sync_workflow(conn, customer_id, stage):
    step = STAGE_STEP_INDEX.get(stage)
    if step is None:
        return
    wf = conn.execute(
        "SELECT id FROM workflow WHERE customer_id=%s AND workflow_type='customer' ORDER BY id DESC LIMIT 1",
        (customer_id,)
    ).fetchone()
    if not wf:
        return
    status = 'completed' if stage == 'aftercare' else 'running'
    conn.execute(
        'UPDATE workflow SET current_step=%s, status=%s WHERE id=%s',
        (step, status, wf['id'])
    )


def _insert_reminder_if_new(conn, customer_id, reminder):
    exists = conn.execute(
        '''SELECT id FROM reminder
           WHERE customer_id=%s AND type=%s AND remind_date=%s AND title=%s AND status='pending'
           LIMIT 1''',
        (customer_id, reminder['type'], reminder['remind_date'], reminder['title'])
    ).fetchone()
    if exists:
        return False
    conn.execute(
        '''INSERT INTO reminder (customer_id, type, title, content, remind_date, status, priority, suggested_action)
           VALUES (%s, %s, %s, %s, %s, 'pending', %s, %s)''',
        (customer_id, reminder['type'], reminder['title'], reminder['content'],
         reminder['remind_date'], reminder.get('priority', 'normal'),
         reminder.get('suggested_action', ''))
    )
    return True


def _auto_generate_next_reminder(conn, customer_id, follow_data, follow_result, customer):
    if not customer:
        return
    today = date.today()
    personality = customer.get('personality_type', '')
    nickname = customer.get('nickname', '')
    next_time_str = (follow_data.get('next_time') or '').strip()

    if next_time_str:
        _insert_reminder_if_new(conn, customer_id, {
            'type': 'follow_up',
            'title': f'{nickname} 约定跟进',
            'content': f'约定跟进时间：{next_time_str}。责任人：{follow_data.get("operator") or customer.get("owner") or "未指定"}',
            'remind_date': next_time_str[:10],
            'priority': 'high',
            'suggested_action': _personality_action(personality, customer.get('lifecycle_stage', 'tracking')),
        })

    reminder = None
    if follow_result == 'appointment_scheduled':
        remind_date = next_time_str[:10] if next_time_str else (today + timedelta(days=1)).isoformat()
        reminder = {
            'type': 'appointment', 'title': f'{nickname} 约访提醒',
            'content': f'客户已约访，请准时联系。责任人：{follow_data.get("operator") or customer.get("owner") or "未指定"}',
            'remind_date': remind_date, 'priority': 'high',
            'suggested_action': '提前准备客户资料，根据性格类型调整沟通话术',
        }
    elif follow_result == 'interested' and not next_time_str:
        reminder = {
            'type': 'follow_up', 'title': f'{nickname} 跟进提醒',
            'content': f'客户表现出兴趣，建议2天内跟进。性格：{personality or "未知"}',
            'remind_date': (today + timedelta(days=2)).isoformat(), 'priority': 'high',
            'suggested_action': _personality_action(personality, 'tracking'),
        }
    elif follow_result == 'proposal_sent' and not next_time_str:
        reminder = {
            'type': 'proposal', 'title': f'{nickname} 方案跟进',
            'content': '方案已发送，等待客户反馈',
            'remind_date': (today + timedelta(days=3)).isoformat(), 'priority': 'normal',
            'suggested_action': _personality_action(personality, 'proposal'),
        }
    elif follow_result == 'deal_closed':
        reminder = {
            'type': 'aftercare', 'title': f'{nickname} 成交后回访',
            'content': '成交后7天回访，确认保单生效',
            'remind_date': (today + timedelta(days=7)).isoformat(), 'priority': 'high',
            'suggested_action': _personality_action(personality, 'aftercare') or '致电确认保单',
        }
    elif follow_result == 'policy_delivered':
        reminder = {
            'type': 'aftercare', 'title': f'{nickname} 季度回访',
            'content': '保单已送达，90天后季度回访',
            'remind_date': (today + timedelta(days=90)).isoformat(), 'priority': 'normal',
            'suggested_action': _personality_action(personality, 'aftercare'),
        }
    elif follow_result in ('no_answer', 'postponed') and not next_time_str:
        reminder = {
            'type': 'follow_up', 'title': f'{nickname} 再次联系',
            'content': '上次未接通/推迟，3天后再次尝试',
            'remind_date': (today + timedelta(days=3)).isoformat(), 'priority': 'normal',
            'suggested_action': '换个时间段尝试，或发微信文字留言',
        }

    if reminder:
        _insert_reminder_if_new(conn, customer_id, reminder)


def _personality_action(personality, stage):
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
