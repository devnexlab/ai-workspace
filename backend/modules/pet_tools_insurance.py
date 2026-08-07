"""
智仔工具 · 保险常识：内置常青要点 + 知识库/文案定向检索。
不把每日时事写入知识库。
"""

from __future__ import annotations

from typing import Any

from modules.pet_rag import search_vectors

# 常青常识（可后续扩成配置文件；不替代用户自己的知识库）
_INSURANCE_FACTS: list[dict[str, str]] = [
    {
        'id': 'crit_vs_med',
        'title': '重疾险 vs 医疗险',
        'tags': '重疾 医疗 区别 常识',
        'content': (
            '重疾险：确诊合同约定的重大疾病达到条件后，按保额一次性给付，用途不限。'
            '医疗险：实际发生的合理医疗费用按合同报销，通常有免赔额、年限额、责任免除。'
            '二者互补：重疾补收入与康复支出，医疗管住院账单。'
        ),
    },
    {
        'id': 'waiting',
        'title': '等待期（观望期）',
        'tags': '等待期 观望期 重疾 医疗',
        'content': (
            '等待期是合同生效后一段时间内，部分责任（尤其疾病类）先不赔或只退保费。'
            '常见重疾等待期 90～180 天，医疗险也多有等待期；意外伤害通常无等待期。'
            '等待期内出险的处理以条款为准，投保前要讲清楚。'
        ),
    },
    {
        'id': 'hesitation',
        'title': '犹豫期',
        'tags': '犹豫期 退保 冷静期',
        'content': (
            '犹豫期是签收保单后可无条件解除合同、退还已交保费（可能扣工本费）的时间窗口，'
            '常见 15 天（以条款/监管要求为准）。过犹豫期后退保通常按现金价值，可能损失较大。'
        ),
    },
    {
        'id': 'cash_value',
        'title': '现金价值',
        'tags': '现金价值 退保 分红',
        'content': (
            '现金价值是退保或减保时可拿回的金额，长期寿险/年金早期现金价值往往较低。'
            '不等于累计已交保费。贷款、减额交清等也常以现价为基础。'
        ),
    },
    {
        'id': 'disclosure',
        'title': '健康告知与如实告知',
        'tags': '健康告知 如实告知 拒赔 核保',
        'content': (
            '投保人应就保险公司询问的健康与职业事项如实告知。'
            '故意或重大过失未如实告知，保险公司可依法解除合同或拒赔，具体看条款与《保险法》规定。'
            '拿不准的既往症、检查异常，建议先核保或咨询专业人士，不要自行隐瞒。'
        ),
    },
    {
        'id': 'beneficiary',
        'title': '受益人',
        'tags': '受益人 身故 法定',
        'content': (
            '身故保险金由指定受益人领取；未指定时往往按法定继承处理（以条款与法律为准）。'
            '家庭结构变化（结婚、离婚、子女出生）后建议复核受益人指定是否仍合适。'
        ),
    },
    {
        'id': 'pension_3',
        'title': '养老金三支柱（常识框架）',
        'tags': '养老金 养老 退休 社保 商保',
        'content': (
            '常见框架：第一支柱基本养老保险（社保养老）；第二支柱企业/职业年金；'
            '第三支柱个人养老金与商业养老险等。口播与客户沟通时，先厘清「能领多少、差多少、怎么补」，'
            '避免把理财收益承诺说成刚兑。'
        ),
    },
    {
        'id': 'claim_tips',
        'title': '理赔沟通要点',
        'tags': '理赔 材料 时效 常识',
        'content': (
            '理赔前核对：是否在保险期间、是否属于责任、是否过等待期、是否有免责。'
            '材料一般含身份证明、诊断/病历、费用清单、银行卡等，以保险公司清单为准。'
            '出险后尽快报案，保留票据与检查报告，避免口头承诺替代条款。'
        ),
    },
    {
        'id': 'term_vs_whole',
        'title': '定期寿 vs 终身寿（简述）',
        'tags': '定寿 终身寿 身故 保障',
        'content': (
            '定期寿险：约定期间内身故/全残赔付，保费相对低，适合家庭责任高峰期。'
            '终身寿险：保障期限更长，常含现价与传承功能，保费更高。'
            '选型看保障缺口、预算与是否需要储蓄/传承，而不是只看「贵不贵」。'
        ),
    },
    {
        'id': 'social_vs_comm',
        'title': '社保与商保关系',
        'tags': '社保 商保 医保 补充',
        'content': (
            '社保是基础；商业保险多用于补充目录外费用、提升额度、覆盖重疾给付与收入补偿等。'
            '医疗险常要求先医保结算再报销商保（以产品规则为准）。'
            '给客户方案时应先问清社保参保情况，再谈商保层。'
        ),
    },
]


def _score_fact(question: str, fact: dict[str, str]) -> float:
    q = (question or '').strip().lower()
    if not q:
        return 0.0
    blob = f"{fact.get('title', '')} {fact.get('tags', '')} {fact.get('content', '')}".lower()
    keys = []
    for n in (2, 3, 4):
        for i in range(max(0, len(q) - n + 1)):
            piece = q[i:i + n]
            if any('\u4e00' <= ch <= '\u9fff' for ch in piece):
                keys.append(piece)
    for t in (question or '').replace('？', ' ').replace('?', ' ').split():
        if len(t) >= 2:
            keys.append(t.lower())
    if not keys:
        return 0.0
    hit = sum(1 for k in set(keys) if k in blob)
    return hit / max(len(set(keys)), 1)


def _builtin_hits(question: str, top_k: int = 4) -> list[dict[str, Any]]:
    scored = []
    for fact in _INSURANCE_FACTS:
        s = _score_fact(question, fact)
        if s <= 0:
            continue
        scored.append((s, fact))
    scored.sort(key=lambda x: x[0], reverse=True)
    # 若几乎不匹配，仍返回最通用的 2 条框架常识
    if not scored:
        fallback = [_INSURANCE_FACTS[0], _INSURANCE_FACTS[6]]
        return [{
            'score': 0.2,
            'title': f"保险常识 · {f['title']}",
            'content': f['content'],
            'source': 'builtin',
        } for f in fallback]
    out = []
    for s, f in scored[:top_k]:
        if s < 0.05 and out:
            break
        out.append({
            'score': round(0.4 + s * 0.5, 3),
            'title': f"保险常识 · {f['title']}",
            'content': f['content'],
            'source': 'builtin',
        })
    return out


def tool_insurance_knowledge(question: str) -> tuple[list[dict], str]:
    """
    保险常识工具：内置要点 + 知识库/文案检索。
    """
    cites: list[dict] = [{
        'score': '工具',
        'title': '保险常识工具',
        'meta': '常青要点 · 非时事新闻',
        'source_type': 'insurance_tool',
        'source_id': 0,
        'path': '/knowledge',
        'snippet': '',
    }]

    parts = ['【保险常识工具】']
    builtin = _builtin_hits(question, top_k=4)
    if builtin:
        parts.append('\n一、常青常识（内置）')
        for i, b in enumerate(builtin, 1):
            parts.append(f"{i}. {b['title']}\n{(b.get('content') or '')[:500]}")
            cites.append({
                'score': f"{b['score']:.2f}",
                'title': b['title'],
                'meta': '保险常识 · 内置',
                'source_type': 'insurance_tool',
                'source_id': i,
                'path': '/knowledge',
                'snippet': (b.get('content') or '')[:120],
            })

    # 定向检索用户知识库/文案（不搜股票简报）
    try:
        hits = search_vectors(
            question,
            source_types=['knowledge', 'script'],
            top_k=5,
            min_score=0.18,
        )
    except Exception as e:
        hits = []
        parts.append(f'\n（知识库检索暂不可用：{e}）')

    # 偏好标题/正文含保险相关词的条目
    prefer_keys = (
        '保险', '重疾', '医疗', '理赔', '保单', '条款', '养老', '年金',
        '寿险', '等待期', '核保', '保费', '保额',
    )
    preferred, others = [], []
    for h in hits:
        blob = f"{h.get('title', '')} {h.get('content', '')}"
        if any(k in blob for k in prefer_keys):
            preferred.append(h)
        else:
            others.append(h)
    ordered = (preferred + others)[:5]

    if ordered:
        parts.append('\n二、知识库 / 文案召回')
        for i, h in enumerate(ordered, 1):
            parts.append(
                f"{i}. [{h.get('label')}] {h.get('title')}（相似度 {h.get('score')}）\n"
                f"{(h.get('content') or '')[:600]}"
            )
            cites.append({
                'score': f"{h['score']:.2f}",
                'title': h.get('title') or '',
                'meta': f"{h.get('label')} · 保险工具召回",
                'source_type': h.get('source_type'),
                'source_id': h.get('source_id'),
                'path': '/knowledge' if h.get('source_type') == 'knowledge' else '/scripts',
                'snippet': (h.get('content') or '')[:120],
            })
    else:
        parts.append(
            '\n二、知识库 / 文案：暂无足够相关条目。'
            '可将产品要点、话术按主题写入知识库，本工具会优先召回。'
        )

    parts.append(
        '\n说明：内置常识为通用框架，具体以产品条款与当地监管为准；'
        '不作销售误导，不替代持牌顾问的一对一建议。'
    )
    return cites, '\n'.join(parts)
