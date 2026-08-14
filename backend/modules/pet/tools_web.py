# -*- coding: utf-8 -*-
"""智仔工具 · 联网读取。

两种能力：
1) web_search：优先真实搜索引擎 API；失败或不配置时降级到模型原生联网。
2) web_fetch：给一个具体网址，抓取并抽取正文（不依赖任何 Key）。

安全边界：仅公共网页检索与指定 URL 抓取，不做登录态爬取、不模拟点击。
"""

from __future__ import annotations

import re
from datetime import datetime

import requests
from config import get_setting
from modules.ai.writer import call_llm

# 原生支持联网的厂商（call_llm 会为这些厂商拼装联网请求）
WEB_SEARCH_SUPPORTED = {'zhipu', 'moonshot'}


def _cite_web(title: str, url: str = '', snippet: str = '') -> dict:
    display = _display_url(url)
    return {
        'score': '联网',
        'title': title or (display or url or '网页'),
        'meta': f'来源：{display}' if display else ('来源：联网检索' if not url else f'来源：{url[:80]}…'),
        'source_type': 'web',
        'source_id': 0,
        'path': url or '/',
        'snippet': (snippet or '')[:220],
    }


def _display_url(url: str, max_len: int = 96) -> str:
    """展示用短链：去掉超长垃圾参数，避免撑破聊天页宽。"""
    u = (url or '').strip()
    if not u:
        return ''
    try:
        from urllib.parse import urlparse, urlunparse
        p = urlparse(u)
        clean = urlunparse((p.scheme, p.netloc, p.path, '', '', ''))
    except Exception:
        clean = u.split('?', 1)[0]
    if len(clean) > max_len:
        return clean[: max_len - 1] + '…'
    return clean


def _real_web_search(query: str) -> dict | None:
    """调用配置的搜索引擎 API（Tavily / Brave / SerpAPI）。

    返回：
    - None：未配置 key
    - {'ok': True, 'cites': [...], 'text': '...'}
    - {'ok': False, 'error': '...'}：已配置但调用失败
    """
    api_key = (get_setting('web', 'search_api_key') or '').strip()
    if not api_key:
        return None
    provider = (get_setting('web', 'search_provider') or 'tavily').strip().lower()

    _TIME_KW = re.compile(
        r'今天|今日|最近|最新|实时|昨日|本周|本月|这周|这月|现在|当下|行情|北向|股价|涨跌|新闻|财报|政策'
    )
    _today = datetime.now().strftime('%Y-%m-%d')
    _time_sensitive = bool(_TIME_KW.search(query))
    search_query = f'{query} {_today}' if _time_sensitive else query

    try:
        if provider == 'brave':
            resp = requests.get(
                'https://api.search.brave.com/res/v1/web/search',
                params={'q': search_query, 'count': 8},
                headers={'Accept': 'application/json',
                         'X-Subscription-Token': api_key},
                timeout=20,
            )
            resp.raise_for_status()
            items = (resp.json().get('web') or {}).get('results') or []
            results = [
                {'title': it.get('title', ''), 'url': it.get('url', ''),
                 'content': it.get('description', '')}
                for it in items
            ]
        elif provider == 'serpapi':
            resp = requests.get(
                'https://serpapi.com/search.json',
                params={'engine': 'google', 'q': search_query, 'api_key': api_key, 'num': 8},
                timeout=20,
            )
            resp.raise_for_status()
            items = resp.json().get('organic_results') or []
            results = [
                {'title': it.get('title', ''), 'url': it.get('link', ''),
                 'content': it.get('snippet', '')}
                for it in items
            ]
        else:  # tavily
            payload = {
                'api_key': api_key,
                'query': search_query,
                'max_results': 8,
                'search_depth': 'basic',
            }
            if _time_sensitive:
                payload['topic'] = 'news'
            resp = requests.post(
                'https://api.tavily.com/search',
                json=payload,
                timeout=25,
            )
            if resp.status_code >= 400:
                try:
                    detail = resp.json()
                    err = detail.get('detail') or detail.get('error') or resp.text[:200]
                except Exception:
                    err = resp.text[:200]
                return {'ok': False, 'error': f'{provider} HTTP {resp.status_code}: {err}'}
            results = [
                {'title': r.get('title', ''), 'url': r.get('url', ''),
                 'content': r.get('content', '')}
                for r in (resp.json().get('results') or [])
            ]
    except requests.exceptions.Timeout:
        return {'ok': False, 'error': f'{provider} 请求超时，请稍后重试'}
    except requests.exceptions.ConnectionError:
        return {'ok': False, 'error': f'无法连接 {provider}，请检查网络或代理'}
    except Exception as e:
        return {'ok': False, 'error': str(e)[:200]}

    if not results:
        return {
            'ok': True,
            'cites': [],
            'text': '联网检索没有返回有效结果。可以换种更具体的问法，或给我一个具体网址。',
        }

    cites = []
    blocks = []
    for i, r in enumerate(results[:8], 1):
        url = r.get('url', '')
        title = r.get('title', '') or (url or f'结果{i}')
        snippet = (r.get('content') or '').strip()
        cites.append(_cite_web(title, url, snippet[:220]))
        blocks.append(f'{i}. {title}\n   来源：{_display_url(url)}\n   {snippet}')
    text = (
        '【联网检索原始材料】（供分析总结，不要把下列条目原文堆给用户）\n'
        '回答时不要在正文里粘贴超长网址；系统会单独展示引用卡片。\n\n'
        + '\n\n'.join(blocks)
        + '\n\n请综合相关条目提炼结论与依据；忽略与问题无关的旧闻/广告。'
    )
    return {'ok': True, 'cites': cites, 'text': text}


def _native_llm_web_search(query: str) -> tuple[list[dict], str, bool]:
    """厂商原生联网降级。返回 (cites, text, supported)。"""
    system = (
        '你是一个联网检索助手。基于联网检索结果先筛选相关信息，再分析总结后回答用户问题，并注明信息来源。'
        '不要把检索条目原文列表直接甩给用户；若资料不足或偏旧，如实说明，不要编造。'
    )
    prompt = f'请联网检索、分析总结后回答：{query}'
    content, _tok, _model, extra = call_llm(
        prompt, system_prompt=system, temperature=0.3, max_tokens=1200,
        web_search=True, return_extra=True,
    )
    content = (content or '').strip()
    cites: list[dict] = []
    for c in (extra.get('citations') or []):
        cites.append(_cite_web(
            c.get('title') or c.get('url') or '检索结果',
            c.get('url') or '',
            c.get('snippet') or '',
        ))
    supported = bool(extra.get('web_supported'))
    if not content:
        content = '联网检索没有返回有效内容，请换种问法，或给我一个具体网址。'
    return cites, content, supported


def web_search(query: str, history: list[dict] | None = None) -> tuple[list[dict], str]:
    """联网搜索：优先真实搜索引擎；失败或不配置时降级到厂商原生联网。"""
    enabled = str(get_setting('web', 'enabled', 'true')).lower() != 'false'
    if not enabled:
        return [], '当前已关闭联网功能（web.enabled=false），可在系统设置中开启；或给我一个具体网址，我仍可抓取。'

    api_err = ''
    real = _real_web_search(query)
    if real is not None and real.get('ok'):
        return real.get('cites') or [], real.get('text') or ''
    if real is not None and not real.get('ok'):
        api_err = str(real.get('error') or '搜索引擎调用失败')

    try:
        cites, content, supported = _native_llm_web_search(query)
    except Exception as e:
        tips = []
        if api_err:
            tips.append(f'搜索引擎：{api_err}')
        tips.append(f'模型联网：{e}')
        tips.append('可到「系统设置 → 联网搜索」检查 API Key / 网络，或直接给我一个官网链接，我帮你抓取正文。')
        return (
            [_cite_web('联网检索', snippet=(api_err or str(e))[:120])],
            '联网检索暂时不可用。\n- ' + '\n- '.join(tips),
        )

    if api_err and supported:
        content = f'（搜索引擎暂不可用，已自动改用模型联网：{api_err}）\n\n' + content
    elif not cites and not supported:
        prefix = f'（搜索引擎失败：{api_err}；' if api_err else '（'
        content += (
            f'\n\n{prefix}当前模型也不支持原生联网，以上可能不是实时检索。'
            '请在系统设置「联网搜索」中确认 search API Key，'
            '或直接给我一个具体网址，我可以用 web_fetch 抓取正文。）'
        )
    return cites, content.strip()


def web_fetch(url: str, max_chars: int = 6000) -> tuple[list[dict], str]:
    """抓取指定网页并抽取正文（不依赖任何 Key）。"""
    url = (url or '').strip()
    if not url:
        return [], '请提供要读取的网页网址。'
    if not re.match(r'^https?://', url, re.I):
        return [], '只支持 http/https 网址。'

    try:
        resp = requests.get(
            url,
            timeout=20,
            headers={
                'User-Agent': 'Mozilla/5.0 (compatible; WorkBuddyBot/1.0)',
                'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
            },
            allow_redirects=True,
        )
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        return [_cite_web('网页抓取', url, str(e)[:120])], f'抓取网页失败：{e}'

    text = _html_to_text(html)
    if not text.strip():
        return [_cite_web('网页抓取', url)], f'已打开网页但未能抽取到正文：{url}'

    if len(text) > max_chars:
        text = text[:max_chars] + '\n\n（原文较长，已截断展示前 {0} 字；如需更多可让我继续读取。）'.format(max_chars)

    body = (
        f'已读取网页正文：{url}\n\n'
        f'{text}\n\n'
        f'（来源：{url}；本操作为只读抓取，未做任何登录态访问）'
    )
    return [_cite_web('网页抓取', url, text[:200])], body


def _html_to_text(html: str) -> str:
    """把 HTML 转成干净正文（优先 BeautifulSoup，缺失则正则兜底）。"""
    html = re.sub(r'(?is)<script.*?</script>', ' ', html)
    html = re.sub(r'(?is)<style.*?</style>', ' ', html)
    html = re.sub(r'(?is)<head.*?</head>', ' ', html)
    html = re.sub(r'(?is)<noscript.*?</noscript>', ' ', html)

    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        for tag in soup(['script', 'style', 'head', 'nav', 'footer', 'aside', 'form']):
            tag.decompose()
        main = soup.find('article') or soup.find('main') or soup.body
        text = main.get_text(separator='\n') if main else soup.get_text(separator='\n')
    except Exception:
        text = re.sub(r'(?s)<[^>]+>', ' ', html)

    lines = [ln.strip() for ln in text.splitlines()]
    text = '\n'.join(ln for ln in lines if ln)
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    return text
