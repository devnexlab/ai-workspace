"""线索池：进线收集与初筛，转客户后进入客户列表。"""

from __future__ import annotations

SOURCE_OPTIONS = [
    {'value': 'wechat_oa', 'label': '服务号预约'},
    {'value': 'douyin', 'label': '抖音私信'},
    {'value': 'xiaohongshu', 'label': '小红书'},
    {'value': 'channels', 'label': '视频号'},
    {'value': 'manual', 'label': '手工登记'},
]

SOURCE_LABELS = {x['value']: x['label'] for x in SOURCE_OPTIONS}

STATUS_OPTIONS = [
    {'value': 'pending_contact', 'label': '待首联'},
    {'value': 'following', 'label': '跟进中'},
    {'value': 'converted', 'label': '已转化'},
    {'value': 'invalid', 'label': '无效'},
]

STATUS_LABELS = {x['value']: x['label'] for x in STATUS_OPTIONS}

LEAD_FIELDS = [
    'nickname', 'phone', 'wechat', 'source', 'related_content',
    'preferred_time', 'remark', 'status',
]


def source_label(key: str) -> str:
    return SOURCE_LABELS.get(key or '', key or '未知')


def status_label(key: str) -> str:
    return STATUS_LABELS.get(key or '', key or '未知')


def serialize_lead(row) -> dict:
    item = dict(row)
    item['source_label'] = source_label(item.get('source'))
    item['status_label'] = status_label(item.get('status'))
    return item


def create_lead_row(data: dict, *, notify: bool = False) -> dict:
    """创建线索。服务号公开留资与后台录入共用。"""
    nickname = (data.get('nickname') or data.get('name') or '').strip()
    phone = (data.get('phone') or '').strip()
    wechat = (data.get('wechat') or '').strip()
    remark = (data.get('remark') or '').strip()
    preferred = (data.get('preferred_time') or '').strip()
    related = (data.get('related_content') or '').strip()
    source = (data.get('source') or 'manual').strip() or 'manual'
    status = (data.get('status') or 'pending_contact').strip() or 'pending_contact'

    if source not in SOURCE_LABELS:
        source = 'manual'
    if status not in STATUS_LABELS:
        status = 'pending_contact'
    if not nickname:
        raise ValueError('请填写称呼')
    if not phone and not wechat:
        raise ValueError('请至少填写手机或微信号之一')

    from config import get_db

    conn = get_db()
    try:
        cur = conn.execute(
            '''INSERT INTO lead
               (nickname, phone, wechat, source, related_content, preferred_time, remark, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (nickname, phone, wechat, source, related, preferred, remark, status),
        )
        lead_id = cur.lastrowid
        conn.commit()
    finally:
        conn.close()

    if notify:
        try:
            from modules.crm.wechat_notify import send_wechat
            title = f'新线索：{nickname}'
            content = (
                f'来源：{source_label(source)}\n'
                f'称呼：{nickname}\n'
                f'手机：{phone or "-"}\n'
                f'微信：{wechat or "-"}\n'
                f'期望时间：{preferred or "-"}\n'
                f'备注：{remark or "-"}'
            )
            send_wechat(title, content, force=True)
        except Exception as e:
            print(f'[leads] notify failed: {e}')

    return {
        'id': lead_id,
        'nickname': nickname,
        'message': '已提交，我们会尽快联系你',
    }


def convert_lead_to_customer(lead_id: int) -> dict:
    """线索 → 客户（约访），并回写 lead.customer_id / status。"""
    from config import get_db

    conn = get_db()
    try:
        row = conn.execute('SELECT * FROM lead WHERE id=?', (lead_id,)).fetchone()
        if not row:
            raise ValueError('线索不存在')
        lead = dict(row)
        if lead.get('status') == 'converted' and lead.get('customer_id'):
            return {
                'id': lead_id,
                'customer_id': lead['customer_id'],
                'message': '该线索已转化',
                'already': True,
            }
        if lead.get('status') == 'invalid':
            raise ValueError('无效线索不能转为客户')

        channel = source_label(lead.get('source'))
        tags = channel
        remark_parts = []
        if lead.get('preferred_time'):
            remark_parts.append(f'期望联系时间：{lead["preferred_time"]}')
        if lead.get('related_content'):
            remark_parts.append(f'关联内容：{lead["related_content"]}')
        if lead.get('remark'):
            remark_parts.append(lead['remark'])
        remark_parts.append(f'【来自线索池 #{lead_id}】')
        full_remark = '\n'.join(remark_parts)

        cur = conn.execute(
            '''INSERT INTO customer
               (nickname, phone, wechat, source_channel, tags, intention,
                lifecycle_stage, remark)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (
                lead.get('nickname') or '',
                lead.get('phone') or '',
                lead.get('wechat') or '',
                channel,
                tags,
                'medium',
                'appointment',
                full_remark,
            ),
        )
        customer_id = cur.lastrowid

        # 尽量创建客户工作流（与客户创建接口一致）
        try:
            import json
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
                   VALUES (?, 'customer', ?, 'running', 0, ?)''',
                (
                    f'{lead.get("nickname") or customer_id} - 客户跟进流程',
                    json.dumps(steps, ensure_ascii=False),
                    customer_id,
                ),
            )
        except Exception:
            pass

        conn.execute(
            '''UPDATE lead SET status='converted', customer_id=?, updated_at=CURRENT_TIMESTAMP
               WHERE id=?''',
            (customer_id, lead_id),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        'id': lead_id,
        'customer_id': customer_id,
        'message': '已转为客户',
    }
