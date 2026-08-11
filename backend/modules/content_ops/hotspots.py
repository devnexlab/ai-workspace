"""
全网实时热点聚合。

优先拉取公开热榜（微博/百度等），失败则用 AI 生成「今日可做口播的热点」兜底，
保证内容运营不断粮。
"""

import re
import requests
from datetime import datetime


def fetch_weibo_hot(limit=20):
    """微博热搜。"""
    items = []
    try:
        resp = requests.get(
            'https://weibo.com/ajax/side/hotSearch',
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0',
                'Referer': 'https://weibo.com/',
            },
            timeout=12,
        )
        if resp.status_code != 200:
            return items
        data = resp.json()
        realtime = (data.get('data') or {}).get('realtime') or []
        for i, row in enumerate(realtime[:limit]):
            word = row.get('word') or row.get('note') or ''
            if not word:
                continue
            items.append({
                'platform': 'weibo_hot',
                'title': word,
                'author': '微博热搜',
                'likes': int(row.get('num') or 0),
                'comments': 0,
                'favorites': 0,
                'shares': 0,
                'url': f'https://s.weibo.com/weibo?q={requests.utils.quote(word)}',
                'cover': '',
                'keyword': '实时热搜',
                'source_type': 'hotspot',
                'content_kind': 'hotspot',
                'hot_rank': i + 1,
                'publish_time': datetime.now().strftime('%Y-%m-%d %H:%M'),
            })
    except Exception as e:
        print(f'[Hotspot] weibo failed: {e}')
    return items


def fetch_baidu_hot(limit=20):
    """百度热搜榜。"""
    items = []
    try:
        resp = requests.get(
            'https://top.baidu.com/api/board?platform=pc&tab=realtime',
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0',
                'Referer': 'https://top.baidu.com/board?tab=realtime',
            },
            timeout=12,
        )
        if resp.status_code != 200:
            return items
        data = resp.json()
        cards = (((data.get('data') or {}).get('cards')) or [{}])[0]
        content = cards.get('content') or []
        for i, row in enumerate(content[:limit]):
            word = row.get('word') or row.get('query') or ''
            if not word:
                continue
            hot_score = 0
            try:
                hot_score = int(re.sub(r'\D', '', str(row.get('hotScore') or '0')) or 0)
            except Exception:
                hot_score = 0
            items.append({
                'platform': 'baidu_hot',
                'title': word,
                'author': '百度热搜',
                'likes': hot_score,
                'comments': 0,
                'favorites': 0,
                'shares': 0,
                'url': row.get('rawUrl') or f'https://www.baidu.com/s?wd={requests.utils.quote(word)}',
                'cover': row.get('img') or '',
                'keyword': '实时热搜',
                'source_type': 'hotspot',
                'content_kind': 'hotspot',
                'hot_rank': i + 1,
                'publish_time': datetime.now().strftime('%Y-%m-%d %H:%M'),
            })
    except Exception as e:
        print(f'[Hotspot] baidu failed: {e}')
    return items


_AGG_BASE = 'https://60s.viki.moe/v2'
# 公开聚合源（免登录）。视频号无开放搜索；抖音热榜走聚合接口补选题。
_AGG_SOURCES = [
    ('douyin', 'douyin_hot', '抖音热榜'),
    ('toutiao', 'toutiao_hot', '头条热榜'),
    ('zhihu', 'zhihu_hot', '知乎热榜'),
]


def _fetch_aggregated(source, platform_key, author, limit=20):
    """
    公开热榜聚合接口（HTTP JSON，无需 Playwright / Cookie）。
    得到的是「选题标题 + 热度」，不是平台成片视频文件，也不是完整口播稿。
    口播文案请在热点上点「生成口播」用 AI 改写。
    """
    items = []
    try:
        resp = requests.get(
            f'{_AGG_BASE}/{source}',
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'},
            timeout=15,
        )
        if resp.status_code != 200:
            return items
        payload = resp.json() or {}
        rows = payload.get('data') or []
        if isinstance(rows, dict):
            rows = rows.get('list') or rows.get('data') or []
        if not isinstance(rows, list):
            return items
        for i, row in enumerate(rows[:limit]):
            if not isinstance(row, dict):
                continue
            title = (row.get('title') or row.get('word') or row.get('name') or '').strip()
            if not title:
                continue
            hot = 0
            for key in ('hot_value', 'hot', 'hot_score', 'hotScore', 'num', 'score'):
                if row.get(key) is not None:
                    try:
                        hot = int(re.sub(r'\D', '', str(row.get(key))) or 0)
                    except Exception:
                        hot = 0
                    if hot:
                        break
            link = (
                row.get('link') or row.get('url') or row.get('mobile_url')
                or row.get('rawUrl') or ''
            )
            items.append({
                'platform': platform_key,
                'title': title,
                'author': author,
                'likes': hot,
                'comments': 0,
                'favorites': 0,
                'shares': 0,
                'url': link,
                'cover': row.get('cover') or row.get('img') or '',
                'keyword': '实时热榜',
                'source_type': 'hotspot',
                'content_kind': 'hotspot',
                'hot_rank': i + 1,
                'publish_time': datetime.now().strftime('%Y-%m-%d %H:%M'),
            })
    except Exception as e:
        print(f'[Hotspot] {source} failed: {e}')
    return items


def fetch_ai_daily_hotspots(limit=10):
    """AI 兜底：生成今日适合泛流量/保险口播的热点选题。"""
    try:
        from modules.ai.writer import call_llm
        import json
        today = datetime.now().strftime('%Y年%m月%d日')
        prompt = f"""今天是{today}。请给出{limit}条「适合短视频口播」的实时/近期热点选题。
覆盖不同年龄段（20-80岁），偏人生共鸣、家庭、健康、社会话题；其中约2条可自然接到保险/保障。
只返回JSON数组：
[{{"title":"选题标题","age_band":"20s|30s|40s|50s|60s|70s|80s|all","kind":"traffic|insurance","reason":"为何适合口播"}}]"""
        resp, _, _ = call_llm(prompt, system_prompt='只输出JSON数组', temperature=0.4, max_tokens=1200)
        match = re.search(r'\[[\s\S]*\]', resp or '')
        if not match:
            return []
        arr = json.loads(match.group())
        items = []
        for i, row in enumerate(arr[:limit]):
            title = row.get('title') or ''
            if not title:
                continue
            items.append({
                'platform': 'web_ai',
                'title': title,
                'author': '全网热点AI',
                'likes': 1000 - i * 10,
                'comments': 0,
                'favorites': 0,
                'shares': 0,
                'url': '',
                'cover': '',
                'keyword': row.get('kind', 'traffic'),
                'source_type': 'hotspot',
                'content_kind': 'hotspot',
                'age_band': row.get('age_band') or 'all',
                'analysis': row.get('reason') or '',
                'hot_rank': i + 1,
                'publish_time': datetime.now().strftime('%Y-%m-%d %H:%M'),
            })
        return items
    except Exception as e:
        print(f'[Hotspot] AI fallback failed: {e}')
        return []


def fetch_all_hotspots(use_ai_fallback=True):
    """聚合全网实时热点（公开 HTTP，免登录；不含平台成片下载）。"""
    items = []
    sources_ok = []

    weibo = fetch_weibo_hot(20)
    if weibo:
        sources_ok.append('微博')
    items.extend(weibo)

    baidu = fetch_baidu_hot(20)
    if baidu:
        sources_ok.append('百度')
    items.extend(baidu)

    for source, platform_key, author in _AGG_SOURCES:
        rows = _fetch_aggregated(source, platform_key, author, 20)
        if rows:
            sources_ok.append(author.replace('热榜', ''))
        items.extend(rows)

    # 去重
    seen = set()
    unique = []
    for it in items:
        t = (it.get('title') or '').strip()
        if not t or t in seen:
            continue
        seen.add(t)
        unique.append(it)

    if len(unique) < 5 and use_ai_fallback:
        ai_items = fetch_ai_daily_hotspots(12)
        for it in ai_items:
            t = it['title']
            if t not in seen:
                seen.add(t)
                unique.append(it)
        if ai_items:
            sources_ok.append('AI补全')

    src = '/'.join(sources_ok) if sources_ok else '无可用源'
    return unique, f'全网热点 {len(unique)} 条（{src}，免登录）'
