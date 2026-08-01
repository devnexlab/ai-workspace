"""
向数据库写入客户管理全场景 Mock 数据，覆盖：
- 全部生命周期：new / appointment / tracking / proposal / deal / aftercare
- 全部性格类型、意向等级
- 跟进记录、待办/逾期提醒、AI 分析、工作流
"""

import json
import sys
import os
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import get_db

TODAY = date.today()


def _iso(d):
    return d.isoformat() if hasattr(d, 'isoformat') else str(d)


def seed():
    conn = get_db()

    # 清理旧 mock（按昵称前缀，避免污染真实数据）
    old = conn.execute(
        "SELECT id FROM customer WHERE nickname LIKE %s OR remark LIKE %s",
        ('【演示】%', '%MOCK_CRM%')
    ).fetchall()
    for row in old:
        cid = row['id']
        conn.execute('DELETE FROM follow_record WHERE customer_id=%s', (cid,))
        conn.execute('DELETE FROM reminder WHERE customer_id=%s', (cid,))
        conn.execute('DELETE FROM customer_analysis WHERE customer_id=%s', (cid,))
        conn.execute('DELETE FROM workflow WHERE customer_id=%s', (cid,))
        conn.execute('DELETE FROM customer WHERE id=%s', (cid,))
    if old:
        print(f'[Mock] 已清理旧演示数据 {len(old)} 条')

    customers = [
        # 1 新增 - 高意向未联系
        {
            'nickname': '【演示】王小美',
            'owner': '张三',
            'assigned_agent': '张三',
            'personality_type': 'emotional',
            'intention': 'high',
            'lifecycle_stage': 'new',
            'wechat': 'wangxm88',
            'phone': '13800001111',
            'tags': '高意向,视频号留资',
            'source_channel': '视频号',
            'source_video': '重疾险科普第3集',
            'age': 32,
            'occupation': '小学教师',
            'income': '15-20万',
            'region': '杭州',
            'family_info': '已婚，一孩3岁',
            'insurance_needs': '重疾+医疗',
            'remark': 'MOCK_CRM 新客户，尚未首次联系',
            'last_follow_time': '',
            'stage_entered_at': TODAY - timedelta(days=1),
        },
        # 2 约访 - 已约明天
        {
            'nickname': '【演示】李强',
            'owner': '张三',
            'assigned_agent': '李四',
            'personality_type': 'decisive',
            'intention': 'high',
            'lifecycle_stage': 'appointment',
            'wechat': 'liqiang_hz',
            'phone': '13900002222',
            'tags': '约访,企业主',
            'source_channel': '转介绍',
            'age': 41,
            'occupation': '贸易公司老板',
            'income': '50万+',
            'region': '杭州',
            'family_info': '已婚，两孩',
            'risk_preference': '偏进取',
            'insurance_needs': '高额重疾+寿险',
            'remark': 'MOCK_CRM 已约访，明天面谈',
            'last_follow_time': f'{_iso(TODAY - timedelta(days=1))} 15:20:00',
            'birthday': (TODAY + timedelta(days=12)).replace(year=1985),
            'stage_entered_at': TODAY - timedelta(days=1),
        },
        # 3 跟踪中 - 沉默超时
        {
            'nickname': '【演示】赵敏',
            'owner': '李四',
            'assigned_agent': '李四',
            'personality_type': 'cautious',
            'intention': 'medium',
            'lifecycle_stage': 'tracking',
            'wechat': 'zhaomin_ok',
            'phone': '13700003333',
            'tags': '跟踪,谨慎型',
            'source_channel': '小红书',
            'age': 36,
            'occupation': '会计',
            'income': '20-30万',
            'region': '宁波',
            'family_info': '已婚未育',
            'risk_preference': '保守',
            'insurance_needs': '医疗+意外',
            'remark': 'MOCK_CRM 跟踪中，已沉默多日需提醒',
            'last_follow_time': f'{_iso(TODAY - timedelta(days=8))} 10:00:00',
            'stage_entered_at': TODAY - timedelta(days=10),
        },
        # 4 方案沟通 - 理性型
        {
            'nickname': '【演示】陈志远',
            'owner': '张三',
            'assigned_agent': '张三',
            'personality_type': 'rational',
            'intention': 'high',
            'lifecycle_stage': 'proposal',
            'wechat': 'chenzy_fin',
            'phone': '13600004444',
            'tags': '方案已发,理性型',
            'source_channel': '短视频评论',
            'age': 45,
            'occupation': '互联网产品经理',
            'income': '40-50万',
            'region': '上海',
            'family_info': '已婚，一孩8岁',
            'risk_preference': '稳健',
            'consumption_capacity': '强',
            'insurance_needs': '重疾+定寿+年金对比',
            'remark': 'MOCK_CRM 已发三套方案，等数据反馈',
            'last_follow_time': f'{_iso(TODAY - timedelta(days=2))} 19:30:00',
            'stage_entered_at': TODAY - timedelta(days=3),
        },
        # 5 成交 - 待7天回访
        {
            'nickname': '【演示】周阿姨',
            'owner': '王五',
            'assigned_agent': '王五',
            'personality_type': 'social',
            'intention': 'high',
            'lifecycle_stage': 'deal',
            'wechat': 'zhou_ayi',
            'phone': '13500005555',
            'tags': '已成交,待回访',
            'source_channel': '社区活动',
            'age': 52,
            'occupation': '退休',
            'income': '养老金+理财',
            'region': '杭州',
            'family_info': '老伴健在，两子女成家',
            'insurance_needs': '防癌险',
            'deal_date': TODAY - timedelta(days=6),
            'deal_amount': '8600',
            'policy_type': '防癌险（年缴）',
            'policy_expiry_date': TODAY + timedelta(days=359),
            'remark': 'MOCK_CRM 成交约6天，需回访确认保单',
            'last_follow_time': f'{_iso(TODAY - timedelta(days=6))} 11:00:00',
            'stage_entered_at': TODAY - timedelta(days=6),
        },
        # 6 售后维护 - 季度回访 + 保单临期
        {
            'nickname': '【演示】孙建国',
            'owner': '王五',
            'assigned_agent': '张三',
            'personality_type': 'rational',
            'intention': 'medium',
            'lifecycle_stage': 'aftercare',
            'wechat': 'sunjg1968',
            'phone': '13400006666',
            'tags': '售后,续保,转介绍潜力',
            'source_channel': '老客户',
            'age': 48,
            'occupation': '工程师',
            'income': '30万',
            'region': '嘉兴',
            'family_info': '已婚，一孩高中',
            'existing_policies': '重疾险A、医疗险B',
            'deal_date': TODAY - timedelta(days=200),
            'deal_amount': '15200',
            'policy_type': '重疾险+医疗险',
            'policy_expiry_date': TODAY + timedelta(days=25),
            'birthday': (TODAY + timedelta(days=5)).replace(year=1978),
            'remark': 'MOCK_CRM 售后客户，保单临期+生日将近',
            'last_follow_time': f'{_iso(TODAY - timedelta(days=40))} 16:00:00',
            'stage_entered_at': TODAY - timedelta(days=88),
        },
        # 7 中意向跟踪 - 感性型
        {
            'nickname': '【演示】吴芳',
            'owner': '李四',
            'assigned_agent': '李四',
            'personality_type': 'emotional',
            'intention': 'medium',
            'lifecycle_stage': 'tracking',
            'wechat': 'wufang_home',
            'phone': '13300007777',
            'tags': '宝妈,感性型',
            'source_channel': '抖音',
            'age': 29,
            'occupation': '全职妈妈',
            'income': '家庭年入40万',
            'region': '杭州',
            'family_info': '二胎备孕中',
            'insurance_needs': '母婴+少儿重疾',
            'remark': 'MOCK_CRM 关注家庭故事案例',
            'last_follow_time': f'{_iso(TODAY - timedelta(days=2))} 21:10:00',
            'stage_entered_at': TODAY - timedelta(days=5),
        },
        # 8 低意向新增 - 未分配责任人（看缺省态）
        {
            'nickname': '【演示】匿名访客',
            'owner': '',
            'assigned_agent': '',
            'personality_type': '',
            'intention': 'low',
            'lifecycle_stage': 'new',
            'wechat': '',
            'phone': '13200008888',
            'tags': '待分配',
            'source_channel': '直播间',
            'remark': 'MOCK_CRM 低意向、无责任人、无性格',
            'last_follow_time': '',
            'stage_entered_at': TODAY,
        },
    ]

    id_map = {}
    stage_steps = {
        'new': 0, 'appointment': 1, 'tracking': 2,
        'proposal': 3, 'deal': 4, 'aftercare': 5,
    }

    for c in customers:
        fields = list(c.keys())
        placeholders = ', '.join(['%s'] * len(fields))
        values = []
        for f in fields:
            v = c[f]
            if isinstance(v, date):
                v = v.isoformat()
            values.append(v)
        cur = conn.execute(
            f'INSERT INTO customer ({", ".join(fields)}) VALUES ({placeholders})',
            values
        )
        cid = cur.lastrowid
        id_map[c['nickname']] = cid

        # 工作流
        steps = [
            {'step': 1, 'name': '新增客户', 'stage': 'new'},
            {'step': 2, 'name': '约访', 'stage': 'appointment'},
            {'step': 3, 'name': '跟踪跟进', 'stage': 'tracking'},
            {'step': 4, 'name': '方案沟通', 'stage': 'proposal'},
            {'step': 5, 'name': '成交', 'stage': 'deal'},
            {'step': 6, 'name': '售后维护', 'stage': 'aftercare'},
        ]
        step_idx = stage_steps.get(c['lifecycle_stage'], 0)
        status = 'completed' if c['lifecycle_stage'] == 'aftercare' else 'running'
        conn.execute(
            '''INSERT INTO workflow (name, workflow_type, steps_json, status, current_step, customer_id)
               VALUES (%s, 'customer', %s, %s, %s, %s)''',
            (f"{c['nickname']} - 客户跟进流程", json.dumps(steps, ensure_ascii=False),
             status, step_idx, cid)
        )
        print(f"[Mock] 客户 #{cid} {c['nickname']} [{c['lifecycle_stage']}] owner={c['owner'] or '未指定'}")

    # ---- 跟进记录 ----
    follows = [
        # 李强 - 约访
        {
            'customer': '【演示】李强',
            'content': '电话沟通，客户很干脆，约了明天上午10点茶叙面谈保障方案。',
            'follow_stage': 'appointment',
            'follow_result': 'appointment_scheduled',
            'operator': '张三',
            'method': 'phone',
            'next_time': f'{_iso(TODAY + timedelta(days=1))} 10:00:00',
            'days_ago': 1,
        },
        {
            'customer': '【演示】李强',
            'content': '转介绍进来，初步了解家庭情况与预算。',
            'follow_stage': 'new',
            'follow_result': 'interested',
            'operator': '李四',
            'method': 'wechat',
            'next_time': '',
            'days_ago': 3,
        },
        # 赵敏 - 跟踪沉默
        {
            'customer': '【演示】赵敏',
            'content': '发了公司评级与条款解读，客户表示要再想想，比较谨慎。',
            'follow_stage': 'tracking',
            'follow_result': 'postponed',
            'operator': '李四',
            'method': 'wechat',
            'next_time': '',
            'days_ago': 8,
        },
        {
            'customer': '【演示】赵敏',
            'content': '首次微信建联，了解医疗险需求。',
            'follow_stage': 'appointment',
            'follow_result': 'interested',
            'operator': '李四',
            'method': 'wechat',
            'next_time': '',
            'days_ago': 12,
        },
        # 陈志远 - 方案
        {
            'customer': '【演示】陈志远',
            'content': '已发送三套方案对比表（保费/保额/免责），客户要周末细看数据。',
            'follow_stage': 'proposal',
            'follow_result': 'proposal_sent',
            'operator': '张三',
            'method': 'wechat',
            'next_time': f'{_iso(TODAY + timedelta(days=2))} 20:00:00',
            'days_ago': 2,
        },
        {
            'customer': '【演示】陈志远',
            'content': '深度面谈1小时，客户理性提问ROI与理赔率。',
            'follow_stage': 'tracking',
            'follow_result': 'interested',
            'operator': '张三',
            'method': 'offline',
            'next_time': '',
            'days_ago': 5,
        },
        # 周阿姨 - 成交
        {
            'customer': '【演示】周阿姨',
            'content': '现场签约防癌险，年缴8600。约定一周后电话回访确认保单。',
            'follow_stage': 'deal',
            'follow_result': 'deal_closed',
            'operator': '王五',
            'method': 'offline',
            'next_time': f'{_iso(TODAY + timedelta(days=1))} 15:00:00',
            'days_ago': 6,
        },
        {
            'customer': '【演示】周阿姨',
            'content': '社区活动认识，聊家庭与健康话题，气氛很好。',
            'follow_stage': 'appointment',
            'follow_result': 'appointment_scheduled',
            'operator': '王五',
            'method': 'offline',
            'next_time': '',
            'days_ago': 10,
        },
        # 孙建国 - 售后
        {
            'customer': '【演示】孙建国',
            'content': '保单送达并讲解条款，客户表示满意，可考虑转介绍同事。',
            'follow_stage': 'aftercare',
            'follow_result': 'policy_delivered',
            'operator': '王五',
            'method': 'phone',
            'next_time': '',
            'days_ago': 40,
        },
        {
            'customer': '【演示】孙建国',
            'content': '正式成交重疾+医疗组合。',
            'follow_stage': 'deal',
            'follow_result': 'deal_closed',
            'operator': '张三',
            'method': 'offline',
            'next_time': '',
            'days_ago': 200,
        },
        # 吴芳
        {
            'customer': '【演示】吴芳',
            'content': '分享了一则母婴理赔真实案例，客户很感动，继续了解少儿重疾。',
            'follow_stage': 'tracking',
            'follow_result': 'interested',
            'operator': '李四',
            'method': 'wechat',
            'next_time': f'{_iso(TODAY + timedelta(days=1))} 21:00:00',
            'days_ago': 2,
        },
    ]

    for f in follows:
        cid = id_map[f['customer']]
        follow_time = TODAY - timedelta(days=f['days_ago'])
        conn.execute(
            '''INSERT INTO follow_record
               (customer_id, content, follow_time, method, next_time, follow_stage, follow_result, operator)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)''',
            (cid, f['content'], f'{_iso(follow_time)} 14:00:00', f['method'],
             f['next_time'], f['follow_stage'], f['follow_result'], f['operator'])
        )
    print(f'[Mock] 跟进记录 {len(follows)} 条')

    # ---- 提醒（含逾期/今天/即将/紧急）----
    reminders = [
        {
            'customer': '【演示】王小美',
            'type': 'high_intent',
            'title': '【演示】王小美 高意向尚未联系',
            'content': '责任人：张三。新客户高意向，建议24小时内首次联系',
            'remind_date': TODAY,
            'priority': 'urgent',
            'suggested_action': '先聊家庭近况再切入保障话题',
            'status': 'pending',
        },
        {
            'customer': '【演示】李强',
            'type': 'appointment',
            'title': '【演示】李强 约访提醒',
            'content': '责任人：张三。明天上午茶叙面谈，请准时',
            'remind_date': TODAY + timedelta(days=1),
            'priority': 'high',
            'suggested_action': '约访直奔主题，准备一页纸方案',
            'status': 'pending',
        },
        {
            'customer': '【演示】赵敏',
            'type': 'silent',
            'title': '【演示】赵敏已8天未联系（跟踪中阶段）',
            'content': '责任人：李四。谨慎型客户，沉默超时需跟进',
            'remind_date': TODAY - timedelta(days=2),  # 逾期
            'priority': 'urgent',
            'suggested_action': '强调产品安全性和公司实力，提供详细条款解读',
            'status': 'pending',
        },
        {
            'customer': '【演示】陈志远',
            'type': 'proposal',
            'title': '【演示】陈志远 方案跟进',
            'content': '方案已发送，等待客户数据反馈',
            'remind_date': TODAY + timedelta(days=2),
            'priority': 'normal',
            'suggested_action': '用表格列出不同方案的保费/保额/免责条款对比',
            'status': 'pending',
        },
        {
            'customer': '【演示】周阿姨',
            'type': 'aftercare',
            'title': '【演示】周阿姨 成交后回访（成交6天）',
            'content': '责任人：王五。确认保单生效，解答疑问',
            'remind_date': TODAY,
            'priority': 'high',
            'suggested_action': '节日问候，关心家庭成员近况；邀请加入客户社群',
            'status': 'pending',
        },
        {
            'customer': '【演示】孙建国',
            'type': 'policy_expiry',
            'title': '【演示】孙建国保单即将到期（25天后）',
            'content': '责任人：王五。建议提前续保沟通',
            'remind_date': TODAY + timedelta(days=5),
            'priority': 'high',
            'suggested_action': '准备续保方案，可推荐升级产品或附加险',
            'status': 'pending',
        },
        {
            'customer': '【演示】孙建国',
            'type': 'birthday',
            'title': '【演示】孙建国生日即将到来（5天后）',
            'content': '责任人：王五。提前准备祝福',
            'remind_date': TODAY,
            'priority': 'high',
            'suggested_action': '发送生日祝福，可附赠小礼物，强化客户关系',
            'status': 'pending',
        },
        {
            'customer': '【演示】孙建国',
            'type': 'aftercare',
            'title': '【演示】孙建国 季度回访',
            'content': '进入售后已近90天，进行季度回访',
            'remind_date': TODAY - timedelta(days=1),
            'priority': 'normal',
            'suggested_action': '定期发送理赔数据和市场分析报告；请求转介绍',
            'status': 'pending',
        },
        {
            'customer': '【演示】吴芳',
            'type': 'follow_up',
            'title': '【演示】吴芳 约定跟进',
            'content': '约定今晚微信跟进少儿重疾',
            'remind_date': TODAY + timedelta(days=1),
            'priority': 'high',
            'suggested_action': '讲故事，分享真实理赔案例，强调家庭安全感',
            'status': 'pending',
        },
        {
            'customer': '【演示】匿名访客',
            'type': 'follow_up',
            'title': '【演示】匿名访客 待分配责任人',
            'content': '低意向线索，尚未指定责任人',
            'remind_date': TODAY,
            'priority': 'normal',
            'suggested_action': '先分配责任人并完成首次触达',
            'status': 'pending',
        },
        # 一条已完成的提醒，方便切换「已完成」筛选
        {
            'customer': '【演示】陈志远',
            'type': 'follow_up',
            'title': '【演示】陈志远 首次建联（已完成）',
            'content': '已完成首次微信建联',
            'remind_date': TODAY - timedelta(days=7),
            'priority': 'normal',
            'suggested_action': '',
            'status': 'done',
        },
    ]

    for r in reminders:
        cid = id_map[r['customer']]
        conn.execute(
            '''INSERT INTO reminder
               (customer_id, type, title, content, remind_date, status, priority, suggested_action)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)''',
            (cid, r['type'], r['title'], r['content'], _iso(r['remind_date']),
             r['status'], r['priority'], r['suggested_action'])
        )
    print(f'[Mock] 提醒 {len(reminders)} 条')

    # ---- AI 分析（给方案/成交客户各一条）----
    analyses = [
        {
            'customer': '【演示】陈志远',
            'deal_probability': 78,
            'focus_points': '保费性价比、免责条款清晰度、公司偿付能力',
            'risk_assessment': '家庭责任重，仅有公司团险不足；预算充足',
            'recommended_products': '重疾险主力 + 定期寿险补充；可对比年金作资产配置',
            'next_step': '周末后电话回访，用一页 ROI 对比表推动二选一决策',
            'extra': {
                'personality_strategy': '理性型：用数据说话，避免情感催促，给清晰优缺点',
            },
        },
        {
            'customer': '【演示】周阿姨',
            'deal_probability': 95,
            'focus_points': '家庭健康话题、社群归属感',
            'risk_assessment': '年龄偏大，防癌需求明确，已成交',
            'recommended_products': '已购防癌险；后续可聊父母意外/子女医疗',
            'next_step': '7天回访确认保单，邀请进客户群，挖掘转介绍',
            'extra': {
                'personality_strategy': '社交型：先维护关系，再轻量提转介绍',
            },
        },
        {
            'customer': '【演示】赵敏',
            'deal_probability': 45,
            'focus_points': '条款安全性、犹豫期与退保规则',
            'risk_assessment': '决策慢，需反复确认，不宜催促',
            'recommended_products': '保守型医疗+意外组合，条款说明要细',
            'next_step': '补充公司资质与理赔案例书面材料，给足思考时间',
            'extra': {
                'personality_strategy': '谨慎型：不要催，材料要完整',
            },
        },
    ]

    for a in analyses:
        cid = id_map[a['customer']]
        blob = {
            'deal_probability': a['deal_probability'],
            'focus_points': a['focus_points'],
            'risk_assessment': a['risk_assessment'],
            'recommended_products': a['recommended_products'],
            'next_step': a['next_step'],
            **a['extra'],
        }
        conn.execute(
            '''INSERT INTO customer_analysis
               (customer_id, deal_probability, focus_points, risk_assessment,
                recommended_products, next_step, ai_analysis)
               VALUES (%s, %s, %s, %s, %s, %s, %s)''',
            (cid, a['deal_probability'], a['focus_points'], a['risk_assessment'],
             a['recommended_products'], a['next_step'],
             json.dumps(blob, ensure_ascii=False))
        )
    print(f'[Mock] AI分析 {len(analyses)} 条')

    conn.commit()
    conn.close()
    print('[Mock] 完成。请刷新「客户管理」查看：漏斗各阶段、提醒中心逾期/今天、责任人筛选、详情策略与AI分析。')


if __name__ == '__main__':
    seed()
