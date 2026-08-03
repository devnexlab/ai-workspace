"""
内容情报流水线：
  1) 全网实时热点
  2) 分年龄段关键词 × 已启用平台 → 搜高互动口播素材
  3) 计算互动率、排序入库
"""

from config import get_collector_config, get_setting
from modules.content_ops.platforms import list_platforms, platform_map
from modules.content_ops.age_bands import (
    keywords_for_ages, guess_age_band, list_age_bands, INSURANCE_KEYWORDS,
)
from modules.content_ops.hotspots import fetch_all_hotspots


def calc_engagement(item):
    """
    互动综合分：点赞 + 收藏*1.5 + 评论*2 + 转发*3
    并给出相对「互动率」近似（有播放量更好，暂无则用绝对互动量归一）。
    """
    likes = int(item.get('likes') or 0)
    fav = int(item.get('favorites') or 0)
    comments = int(item.get('comments') or 0)
    shares = int(item.get('shares') or 0)
    score = likes + fav * 1.5 + comments * 2 + shares * 3
    # 归一到 0-100 粗分（对数友好）
    import math
    rate = min(100.0, round(math.log10(score + 1) * 25, 2)) if score > 0 else 0.0
    return score, rate


def get_enabled_platforms(override=None):
    """返回已启用且可采集的平台 key 列表。"""
    platforms = list_platforms()
    pmap = {p['key']: p for p in platforms}
    keys = override or [p['key'] for p in platforms]
    enabled = []
    for key in keys:
        meta = pmap.get(key)
        if not meta:
            continue
        if not meta.get('enable_collector', True):
            continue
        cfg = get_collector_config(key)
        if str(cfg.get('enabled', 'true')).lower() == 'true':
            enabled.append(key)
    return enabled


def collect_platform_koubo(platforms=None, age_bands=None, count_per_keyword=5,
                           max_keywords=12):
    """
    按年龄段口播关键词，去各平台搜高互动内容。
    """
    from modules.collector import get_collector

    plats = get_enabled_platforms(platforms)
    pmap = platform_map()
    kws = keywords_for_ages(age_bands, include_insurance=False)
    # 限制关键词数量，避免一次跑太久
    kws = kws[:max_keywords]

    all_items = []
    messages = []

    for plat in plats:
        meta = pmap.get(plat, {})
        label = meta.get('label', plat)
        collector = get_collector(plat)
        if not collector:
            messages.append(f'{label}: 未注册采集器')
            continue
        if not collector.is_ready():
            messages.append(f'{label}: 未配置 Cookies，已跳过')
            continue
        try:
            items, msg = collector.collect(kws, count_per_keyword=count_per_keyword)
            for it in items:
                it['source_type'] = 'platform'
                it['content_kind'] = 'koubo'
                it['age_band'] = guess_age_band(it.get('title', ''), it.get('keyword', ''))
                eng, rate = calc_engagement(it)
                it['engagement_score'] = eng
                it['engagement_rate'] = rate
            all_items.extend(items)
            messages.append(f'{label}: {msg}')
        except Exception as e:
            messages.append(f'{label}: 失败 {e}')

    return all_items, '；'.join(messages)


def enrich_and_rank(items):
    """补齐字段并按互动分排序。"""
    for it in items:
        if 'engagement_score' not in it:
            eng, rate = calc_engagement(it)
            it['engagement_score'] = eng
            it['engagement_rate'] = rate
        if not it.get('age_band'):
            it['age_band'] = guess_age_band(it.get('title', ''), it.get('keyword', ''))
        if not it.get('source_type'):
            it['source_type'] = 'platform'
        if not it.get('content_kind'):
            it['content_kind'] = 'koubo'
    items.sort(key=lambda x: (x.get('engagement_score') or 0, x.get('likes') or 0), reverse=True)
    return items


def run_full_intelligence(platforms=None, age_bands=None, include_hotspots=True,
                          count_per_keyword=5, max_keywords=10):
    """
    一键内容情报：
      - 全网实时热点
      - 分龄口播平台采集
      - 互动率排序
    """
    results = []
    logs = []

    if include_hotspots:
        hot_items, hot_msg = fetch_all_hotspots(use_ai_fallback=True)
        for it in hot_items:
            eng, rate = calc_engagement(it)
            it['engagement_score'] = eng
            it['engagement_rate'] = rate
            if not it.get('age_band'):
                it['age_band'] = guess_age_band(it.get('title', ''), it.get('keyword', ''))
        results.extend(hot_items)
        logs.append(hot_msg)

    plat_items, plat_msg = collect_platform_koubo(
        platforms=platforms,
        age_bands=age_bands,
        count_per_keyword=count_per_keyword,
        max_keywords=max_keywords,
    )
    results.extend(plat_items)
    logs.append(plat_msg)

    ranked = enrich_and_rank(results)

    # 去重标题（规范化后前 40 字）
    seen = set()
    unique = []
    for it in ranked:
        t = ' '.join((it.get('title') or '').strip().split())
        key = t[:40]
        if not t or key in seen:
            continue
        seen.add(key)
        it['title'] = t
        unique.append(it)

    return unique, ' | '.join([x for x in logs if x])


def platform_status():
    """给前端展示各平台配置状态。"""
    from modules.collector import get_collector
    rows = []
    for p in list_platforms():
        if not p.get('enable_collector', True):
            continue
        cfg = get_collector_config(p['key'])
        enabled = str(cfg.get('enabled', 'true')).lower() == 'true'
        has_cookie = bool((cfg.get('cookies') or '').strip())
        collector = get_collector(p['key'])
        rows.append({
            **p,
            'enabled': enabled,
            'cookies_ready': has_cookie,
            'collector_ready': bool(collector),
            'keywords': cfg.get('keywords') or '',
            'ready': enabled and has_cookie and bool(collector),
        })
    return rows
