"""客户管理助手：事件驱动分析、阶段推进、下一步提示。"""

from __future__ import annotations

import json
import re
from datetime import date, timedelta

from config import get_db as _db

from .base import BaseAssistant
from .registry import register

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

PERSONALITY_LABELS = {
    'rational': '理性型', 'emotional': '感性型', 'cautious': '谨慎型',
    'decisive': '果断型', 'social': '社交型',
}

DEFAULT_NEXT_BY_STAGE = {
    'new': [
        '首次电话或微信触达，确认来源与基本需求',
        '补充客户画像（年龄、家庭、已有保单）',
        '约定下一次沟通时间',
    ],
    'appointment': [
        '确认约访时间并提前发提醒',
        '准备需求问卷与沟通提纲',
        '面谈后立刻写跟进记录',
    ],
    'tracking': [
        '针对关注点做一次深度沟通',
        '发送相关案例或产品要点',
        '确认意向与顾虑点',
    ],
    'proposal': [
        '发送/讲解方案，解答疑问',
        '对比已有保障缺口',
        '推动确认投保意向与时间',
    ],
    'deal': [
        '完成签约与缴费确认',
        '安排保单送达与条款讲解',
        '约定售后回访时间',
    ],
    'aftercare': [
        '定期回访满意度与理赔咨询',
        '关注保单到期/续保',
        '适时请转介绍',
    ],
}


class CustomerAssistant(BaseAssistant):
    key = 'customer'
    label = '客户管理助手'
    description = '把客户跟进、阶段推进、话术准备等重复工作交给助手'
    events = ('customer.create', 'customer.follow', 'manual')
    default_enabled = True
    has_board = True

    def run(self, **context) -> dict:
        system_prompt = context.get('system_prompt') or ''
        task = context.get('task') or ''
        customer_id = context.get('customer_id')
        if task.startswith('customer:') and not customer_id:
            try:
                customer_id = int(task.split(':', 1)[1])
            except Exception:
                pass
        if customer_id:
            return run_customer_assistant(
                int(customer_id),
                trigger=context.get('trigger') or 'event',
                extra=context.get('extra') or {},
                system_prompt=system_prompt,
            )
        # 批量刷新前几位待跟进客户
        tasks = self.tasks().get('tasks') or []
        refreshed = []
        for t in tasks[:3]:
            cid = t.get('customer_id')
            if not cid:
                continue
            try:
                refreshed.append(
                    run_customer_assistant(
                        int(cid),
                        trigger=context.get('trigger') or 'board',
                        system_prompt=system_prompt,
                    )
                )
            except Exception:
                continue
        top_actions = []
        for r in refreshed:
            for a in (r.get('next_actions') or [])[:1]:
                if a and a not in top_actions:
                    top_actions.append(a)
        if not top_actions:
            top_actions = ['打开客户详情写跟进', '或点某一客户的「让助手跟进」']
        return {
            'assistant': 'customer',
            'summary': f'已为 {len(refreshed)} 位客户生成跟进建议',
            'next_actions': top_actions[:3],
            'message': '客户跟进建议已更新，请按下一步联系客户并写跟进记录',
        }

    def board(self, **params) -> dict:
        return get_customer_board(limit=int(params.get('limit') or 50))

    def tasks(self, **params) -> dict:
        board = get_customer_board(limit=int(params.get('limit') or 30))
        tasks = []
        for item in board.get('list') or []:
            actions = item.get('next_actions') or []
            tip = '；'.join(actions[:2]) if actions else (item.get('next_step') or '分析后给出跟进动作')
            tasks.append({
                'id': f"customer:{item['customer_id']}",
                'title': f"跟进「{item.get('nickname') or item['customer_id']}」",
                'desc': f"{item.get('stage_label') or item.get('lifecycle_stage') or ''} · {tip}",
                'customer_id': item['customer_id'],
                'runnable': True,
                'task': f"customer:{item['customer_id']}",
                'secondary': {'label': '打开客户', 'path': f"/customers?id={item['customer_id']}"},
            })
        return {
            'assistant': 'customer',
            'intro': '把重复的客户跟进交给助手：点「让助手跟进」获取下一步与话术，再去联系并写跟进。',
            'tasks': tasks,
        }


def run_customer_assistant(customer_id: int, trigger: str = 'event', extra: dict | None = None, system_prompt: str = '') -> dict:
    """分析客户并可选推进阶段；结果写入 customer_analysis。"""
    from .registry import is_assistant_enabled
    if not is_assistant_enabled('customer'):
        return {'skipped': True, 'reason': 'customer assistant disabled'}

    conn = _db()
    row = conn.execute('SELECT * FROM customer WHERE id=%s', (customer_id,)).fetchone()
    if not row:
        conn.close()
        return {'error': 'customer not found'}

    follows = conn.execute(
        'SELECT * FROM follow_record WHERE customer_id=%s ORDER BY follow_time DESC LIMIT 8',
        (customer_id,),
    ).fetchall()
    conn.close()

    customer = dict(row)
    follow_list = [dict(f) for f in follows]
    advice = _analyze(customer, follow_list, trigger, extra or {}, system_prompt=system_prompt)

    current = customer.get('lifecycle_stage') or 'new'
    suggested = advice.get('suggested_stage') or current
    if suggested not in LIFECYCLE_STAGES:
        suggested = current

    advanced = False
    new_stage = current
    if advice.get('should_advance') and _can_advance(current, suggested):
        new_stage = suggested
        advanced = True

    next_actions = advice.get('next_actions') or DEFAULT_NEXT_BY_STAGE.get(new_stage, [])[:3]
    if isinstance(next_actions, str):
        next_actions = [next_actions]
    next_actions = [str(a).strip() for a in next_actions if str(a).strip()][:3]
    if not next_actions:
        next_actions = DEFAULT_NEXT_BY_STAGE.get(new_stage, ['继续跟进并记录结果'])[:2]

    summary = (advice.get('summary') or '').strip() or f"当前处于{STAGE_LABELS.get(new_stage, new_stage)}"
    talk_tips = (advice.get('talk_tips') or '').strip()
    best_time = (advice.get('best_time') or '').strip()
    next_step_text = '；'.join(next_actions)

    payload = {
        'source': 'customer_assistant',
        'assistant': 'customer',
        'trigger': trigger,
        'summary': summary,
        'suggested_stage': suggested,
        'should_advance': bool(advice.get('should_advance')),
        'advanced': advanced,
        'lifecycle_stage': new_stage,
        'stage_label': STAGE_LABELS.get(new_stage, new_stage),
        'next_actions': next_actions,
        'talk_tips': talk_tips,
        'best_time': best_time,
        'next_step': next_step_text,
        'deal_probability': int(advice.get('deal_probability') or 50),
        'focus_points': (advice.get('focus_points') or talk_tips or summary)[:300],
        'risk_assessment': (advice.get('risk_assessment') or '')[:300],
        'recommended_products': (advice.get('recommended_products') or '')[:300],
    }

    conn = _db()
    try:
        if advanced:
            _advance_stage(conn, customer_id, new_stage)
            _sync_workflow(conn, customer_id, new_stage)
            if new_stage == 'deal':
                conn.execute(
                    "UPDATE customer SET deal_date=COALESCE(deal_date, CURRENT_DATE) WHERE id=%s",
                    (customer_id,),
                )

        conn.execute(
            '''INSERT INTO customer_analysis
               (customer_id, deal_probability, focus_points, risk_assessment,
                recommended_products, next_step, ai_analysis)
               VALUES (%s, %s, %s, %s, %s, %s, %s)''',
            (
                customer_id,
                payload['deal_probability'],
                payload['focus_points'],
                payload['risk_assessment'],
                payload['recommended_products'],
                next_step_text,
                json.dumps(payload, ensure_ascii=False),
            ),
        )

        _write_assistant_reminder(conn, customer, new_stage, next_actions, best_time, talk_tips)
        conn.commit()
    finally:
        conn.close()

    return payload


def get_customer_board(limit: int = 50) -> dict:
    """进行中客户看板：阶段 + 客户管理助手提示。"""
    conn = _db()
    rows = conn.execute(
        '''SELECT c.id, c.nickname, c.phone, c.wechat, c.intention, c.owner,
                  c.assigned_agent, c.lifecycle_stage, c.last_follow_time, c.created_at,
                  c.personality_type, c.stage_entered_at
           FROM customer c
           WHERE COALESCE(c.lifecycle_stage, 'new') <> 'aftercare'
           ORDER BY COALESCE(c.last_follow_time, c.created_at::text) DESC
           LIMIT %s''',
        (limit,),
    ).fetchall()

    board = []
    for r in rows:
        c = dict(r)
        analysis = conn.execute(
            '''SELECT next_step, ai_analysis, deal_probability, created_at
               FROM customer_analysis WHERE customer_id=%s
               ORDER BY created_at DESC LIMIT 1''',
            (c['id'],),
        ).fetchone()
        tip = _parse_analysis(dict(analysis) if analysis else None)
        stage = c.get('lifecycle_stage') or 'new'
        board.append({
            'customer_id': c['id'],
            'nickname': c.get('nickname') or f"客户#{c['id']}",
            'owner': c.get('owner') or c.get('assigned_agent') or '',
            'intention': c.get('intention') or '',
            'lifecycle_stage': stage,
            'stage_label': STAGE_LABELS.get(stage, stage),
            'last_follow_time': c.get('last_follow_time') or '',
            'created_at': str(c.get('created_at') or ''),
            'summary': tip.get('summary') or '',
            'next_actions': tip.get('next_actions') or [],
            'next_step': tip.get('next_step') or (analysis['next_step'] if analysis else ''),
            'talk_tips': tip.get('talk_tips') or '',
            'best_time': tip.get('best_time') or '',
            'deal_probability': tip.get('deal_probability')
            if tip.get('deal_probability') is not None
            else (analysis['deal_probability'] if analysis else None),
            'assistant_at': str(analysis['created_at']) if analysis else '',
            'has_assistant': bool(analysis),
            'assistant': 'customer',
        })
    conn.close()
    return {
        'assistant': 'customer',
        'list': board,
        'stageLabels': STAGE_LABELS,
        'stages': LIFECYCLE_STAGES,
    }


# 兼容旧命名
get_assistant_board = get_customer_board


def _parse_analysis(analysis: dict | None) -> dict:
    if not analysis:
        return {}
    raw = analysis.get('ai_analysis') or ''
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except Exception:
            pass
    return {
        'next_step': analysis.get('next_step') or '',
        'next_actions': [analysis['next_step']] if analysis.get('next_step') else [],
        'deal_probability': analysis.get('deal_probability'),
    }


def _analyze(customer: dict, follows: list, trigger: str, extra: dict, system_prompt: str = '') -> dict:
    stage = customer.get('lifecycle_stage') or 'new'
    fallback = {
        'suggested_stage': stage,
        'should_advance': False,
        'next_actions': DEFAULT_NEXT_BY_STAGE.get(stage, [])[:3],
        'talk_tips': '',
        'best_time': '工作日白天',
        'summary': f"{STAGE_LABELS.get(stage, stage)}：按清单推进",
        'deal_probability': 40 if stage in ('new', 'appointment') else 55,
        'focus_points': customer.get('insurance_needs') or '',
        'risk_assessment': '',
        'recommended_products': '',
    }

    follow_texts = '\n'.join(
        f"- [{f.get('follow_time') or ''}][{f.get('follow_result') or ''}] {f.get('content') or ''}"
        for f in follows
    ) or '暂无跟进'
    extra_note = ''
    if extra.get('latest_follow'):
        extra_note = f"\n刚发生的跟进：{extra['latest_follow']}"
    if trigger == 'create':
        extra_note += '\n触发：刚新增客户，请给出首次触达动作。'

    prompt = f"""你是保险顾问的「客户管理助手」。根据客户画像与跟进记录，判断是否应推进生命周期阶段，并给出可执行的下一步。

生命周期阶段只能是：{', '.join(LIFECYCLE_STAGES)}
中文：{json.dumps(STAGE_LABELS, ensure_ascii=False)}
规则：should_advance=true 时 suggested_stage 必须严格比当前阶段更靠后；不要跳过不合理阶段；证据不足则不推进。

客户：
姓名：{customer.get('nickname') or ''}
年龄：{customer.get('age') or ''}
职业：{customer.get('occupation') or ''}
意向：{customer.get('intention') or ''}
性格：{PERSONALITY_LABELS.get(customer.get('personality_type') or '', customer.get('personality_type') or '未知')}
需求：{customer.get('insurance_needs') or ''}
已有保单：{customer.get('existing_policies') or ''}
当前阶段：{stage}（{STAGE_LABELS.get(stage, '')}）
责任人：{customer.get('owner') or customer.get('assigned_agent') or ''}
备注：{customer.get('remark') or ''}
{extra_note}

最近跟进：
{follow_texts}

只输出 JSON：
{{
  "suggested_stage": "阶段英文key",
  "should_advance": false,
  "next_actions": ["具体动作1", "具体动作2"],
  "talk_tips": "话术要点",
  "best_time": "建议联系时间",
  "summary": "一句话进展",
  "deal_probability": 0,
  "focus_points": "关注点",
  "risk_assessment": "风险",
  "recommended_products": "产品建议"
}}"""

    try:
        from modules.ai_writer import call_llm
        from .prompts import DEFAULT_SYSTEM_PROMPTS
        sys_p = (system_prompt or '').strip() or DEFAULT_SYSTEM_PROMPTS['customer']
        if 'JSON' not in sys_p and 'json' not in sys_p:
            sys_p = sys_p + ' 只输出合法 JSON，不要解释。'
        resp, _tokens, _model = call_llm(
            prompt,
            system_prompt=sys_p,
            temperature=0.2,
            max_tokens=900,
        )
        match = re.search(r'\{[\s\S]*\}', resp or '')
        if not match:
            return fallback
        data = json.loads(match.group())
        if not isinstance(data, dict):
            return fallback
        for k, v in fallback.items():
            if k not in data or data[k] in (None, ''):
                data[k] = v
        return data
    except Exception:
        return fallback


def _can_advance(current: str, suggested: str) -> bool:
    ci = STAGE_STEP_INDEX.get(current, 0)
    si = STAGE_STEP_INDEX.get(suggested, 0)
    return si > ci


def _advance_stage(conn, customer_id: int, new_stage: str):
    conn.execute(
        "UPDATE customer SET lifecycle_stage=%s, stage_entered_at=CURRENT_TIMESTAMP WHERE id=%s",
        (new_stage, customer_id),
    )


def _sync_workflow(conn, customer_id: int, stage: str):
    step = STAGE_STEP_INDEX.get(stage)
    if step is None:
        return
    wf = conn.execute(
        "SELECT id FROM workflow WHERE customer_id=%s AND workflow_type='customer' ORDER BY id DESC LIMIT 1",
        (customer_id,),
    ).fetchone()
    if not wf:
        steps = [
            {'step': i + 1, 'name': STAGE_LABELS[s], 'desc': '', 'stage': s}
            for i, s in enumerate(LIFECYCLE_STAGES)
        ]
        name_row = conn.execute('SELECT nickname FROM customer WHERE id=%s', (customer_id,)).fetchone()
        nickname = (name_row['nickname'] if name_row else '') or f'客户{customer_id}'
        conn.execute(
            '''INSERT INTO workflow (name, workflow_type, steps_json, status, current_step, customer_id)
               VALUES (%s, 'customer', %s, 'running', %s, %s)''',
            (f'{nickname} - 客户跟进流程', json.dumps(steps, ensure_ascii=False), step, customer_id),
        )
        return
    status = 'completed' if stage == 'aftercare' else 'running'
    conn.execute(
        'UPDATE workflow SET current_step=%s, status=%s WHERE id=%s',
        (step, status, wf['id']),
    )


def _write_assistant_reminder(conn, customer: dict, stage: str, next_actions: list, best_time: str, talk_tips: str):
    nickname = customer.get('nickname') or '客户'
    action = next_actions[0] if next_actions else '继续跟进'
    remind_date = (date.today() + timedelta(days=1)).isoformat()
    title = f'{nickname} · 客户管理助手'
    content = action
    if best_time:
        content += f'（建议时间：{best_time}）'
    suggested = talk_tips or action
    exists = conn.execute(
        '''SELECT id FROM reminder
           WHERE customer_id=%s AND type=%s AND remind_date=%s AND title=%s AND status='pending'
           LIMIT 1''',
        (customer['id'], 'assistant_next', remind_date, title),
    ).fetchone()
    if exists:
        conn.execute(
            '''UPDATE reminder SET content=%s, suggested_action=%s, priority=%s WHERE id=%s''',
            (content, suggested, 'high', exists['id']),
        )
        return
    conn.execute(
        '''INSERT INTO reminder (customer_id, type, title, content, remind_date, status, priority, suggested_action)
           VALUES (%s, %s, %s, %s, %s, 'pending', %s, %s)''',
        (customer['id'], 'assistant_next', title, content, remind_date, 'high', suggested),
    )


register(CustomerAssistant())
