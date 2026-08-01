"""
Data collection module - uses Playwright browser automation for real scraping.

Supported platforms:
  - Xiaohongshu (小红书): browser search page scraping
  - Douyin (抖音): browser search page scraping
  - Shipinhao (视频号): browser search page scraping

The user provides their browser cookies in the Settings page.
This module launches a headless browser, injects cookies, and scrapes real data.
"""

import json
import time
import random
import re
from datetime import datetime

from config import get_collector_config, get_ai_config


def _parse_cookies(cookie_str, domain):
    """Parse cookie string into Playwright cookie format."""
    cookies = []
    for item in cookie_str.split(';'):
        item = item.strip()
        if '=' in item:
            k, v = item.split('=', 1)
            k = k.strip()
            v = v.strip()
            if k and v:
                cookies.append({
                    'name': k,
                    'value': v,
                    'domain': domain,
                    'path': '/',
                })
    return cookies


class BaseCollector:
    """Base class for browser-based collectors."""

    platform = 'unknown'
    cookie_domain = ''

    def __init__(self):
        self.config = get_collector_config(self.platform)

    def is_ready(self):
        return bool(self.config.get('cookies'))

    def _launch_browser(self):
        """Launch a Playwright browser instance."""
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        browser = pw.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-blink-features=AutomationControlled']
        )
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                       '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='zh-CN',
        )
        # Inject cookies
        cookies_str = self.config.get('cookies', '')
        if cookies_str:
            cookies = _parse_cookies(cookies_str, self.cookie_domain)
            if cookies:
                context.add_cookies(cookies)

        page = context.new_page()
        return pw, browser, context, page

    def _close_browser(self, pw, browser, context):
        context.close()
        browser.close()
        pw.stop()

    def search(self, keyword, count=20):
        """Search for trending content. Returns list of dicts."""
        raise NotImplementedError

    def collect(self, keywords, count_per_keyword=10):
        """Collect trending content for multiple keywords."""
        if not self.is_ready():
            return [], 'Cookies 未配置，请在系统设置中填写'

        all_items = []
        errors = []

        for kw in keywords:
            kw = kw.strip()
            if not kw:
                continue
            try:
                items = self.search(kw, count_per_keyword)
                all_items.extend(items)
                time.sleep(random.uniform(2, 4))
            except Exception as e:
                errors.append(f'{kw}: {str(e)[:100]}')

        # Deduplicate by URL
        seen = set()
        unique = []
        for item in all_items:
            url = item.get('url', '')
            if url not in seen:
                seen.add(url)
                unique.append(item)

        msg = f'采集完成，共 {len(unique)} 条'
        if errors:
            msg += f'，部分失败: {"; ".join(errors[:3])}'
        if not unique and not errors:
            msg += '（可能需要更新 Cookies 或页面结构已变化）'
        return unique, msg


class XiaohongshuCollector(BaseCollector):
    """Xiaohongshu collector using Playwright browser automation."""

    platform = 'xiaohongshu'
    cookie_domain = '.xiaohongshu.com'

    def search(self, keyword, count=20):
        pw, browser, context, page = self._launch_browser()
        try:
            # Navigate to search page
            search_url = f'https://www.xiaohongshu.com/search_result?keyword={keyword}&source=web_search_result_notes'
            page.goto(search_url, wait_until='domcontentloaded', timeout=30000)

            # Wait for content to load
            time.sleep(3)

            # Try to wait for note cards
            try:
                page.wait_for_selector('.note-item, section.note-item, div[class*="note"]', timeout=10000)
            except Exception:
                pass

            # Scroll down to load more
            for _ in range(3):
                page.evaluate('window.scrollBy(0, 800)')
                time.sleep(1)

            # Extract data from the page
            items = page.evaluate('''([maxCount, kw]) => {
                const results = [];
                const selectors = [
                    'section.note-item',
                    'div.note-item',
                    '[class*="note-item"]',
                    'a.cover',
                    'div[class*="feeds"] > div'
                ];
                
                let cards = [];
                for (const sel of selectors) {
                    cards = document.querySelectorAll(sel);
                    if (cards.length > 0) break;
                }
                
                if (cards.length === 0) {
                    cards = document.querySelectorAll('a[href*="/explore/"], a[href*="/search_result/"]');
                }
                
                for (const card of cards) {
                    if (results.length >= maxCount) break;
                    
                    let title = '';
                    const titleEl = card.querySelector('.title, .note-title, [class*="title"], span[class*="title"]');
                    if (titleEl) title = titleEl.textContent.trim();
                    if (!title) {
                        const link = card.querySelector('a') || card;
                        title = link.textContent?.trim() || link.getAttribute('title') || '';
                    }
                    
                    let author = '';
                    const authorEl = card.querySelector('.author, .user-name, [class*="author"], [class*="user"] .name');
                    if (authorEl) author = authorEl.textContent.trim();
                    
                    let likes = 0;
                    const likeEl = card.querySelector('.like-wrapper .count, [class*="like"] .count, .like-count, [class*="liked"] .count');
                    if (likeEl) {
                        const txt = likeEl.textContent.trim();
                        if (txt.includes('万')) likes = Math.floor(parseFloat(txt) * 10000);
                        else likes = parseInt(txt.replace('+','')) || 0;
                    }
                    
                    let cover = '';
                    const imgEl = card.querySelector('img');
                    if (imgEl) cover = imgEl.getAttribute('src') || imgEl.getAttribute('data-src') || '';
                    
                    let noteUrl = '';
                    const linkEl = card.tagName === 'A' ? card : card.querySelector('a');
                    if (linkEl) {
                        noteUrl = linkEl.getAttribute('href') || '';
                        if (noteUrl.startsWith('/')) noteUrl = 'https://www.xiaohongshu.com' + noteUrl;
                    }
                    
                    let noteId = '';
                    const idMatch = noteUrl.match(/\/(explore|search_result)\/([a-f0-9]+)/);
                    if (idMatch) noteId = idMatch[2];
                    
                    if (title || noteId) {
                        results.push({
                            platform: 'xiaohongshu',
                            title: title || '(无标题)',
                            author: author,
                            publish_time: '',
                            likes: likes,
                            comments: 0,
                            favorites: 0,
                            shares: 0,
                            url: noteUrl || (noteId ? 'https://www.xiaohongshu.com/explore/' + noteId : ''),
                            cover: cover,
                            keyword: kw || '',
                        });
                    }
                }
                return results;
            }''', [count, keyword])

            return items[:count]

        finally:
            self._close_browser(pw, browser, context)


class DouyinCollector(BaseCollector):
    """Douyin collector using Playwright browser automation."""

    platform = 'douyin'
    cookie_domain = '.douyin.com'

    def search(self, keyword, count=20):
        pw, browser, context, page = self._launch_browser()
        try:
            search_url = f'https://www.douyin.com/search/{keyword}'
            page.goto(search_url, wait_until='domcontentloaded', timeout=30000)

            time.sleep(3)

            # Wait for video cards
            try:
                page.wait_for_selector('li[data-e2e="search-video-item"], div[data-e2e="search-video-item"], [class*="video-item"]', timeout=10000)
            except Exception:
                pass

            # Scroll to load more
            for _ in range(3):
                page.evaluate('window.scrollBy(0, 800)')
                time.sleep(1)

            items = page.evaluate('''([maxCount, kw]) => {
                const results = [];
                const selectors = [
                    'li[data-e2e="search-video-item"]',
                    'div[data-e2e="search-video-item"]',
                    '[class*="video-item"]',
                    '[class*="search-result"] li',
                    'ul[data-e2e="scroll-list"] > li'
                ];
                
                let cards = [];
                for (const sel of selectors) {
                    cards = document.querySelectorAll(sel);
                    if (cards.length > 0) break;
                }
                
                for (const card of cards) {
                    if (results.length >= maxCount) break;
                    
                    let title = '';
                    const titleEl = card.querySelector('[class*="title"], p[class*="title"], a[class*="title"]');
                    if (titleEl) title = titleEl.textContent.trim();
                    if (!title) {
                        const link = card.querySelector('a');
                        title = link?.getAttribute('title') || link?.textContent?.trim() || '';
                    }
                    
                    let author = '';
                    const authorEl = card.querySelector('[class*="author"], [class*="nickname"], [data-e2e="video-author-avatar"]');
                    if (authorEl) author = authorEl.textContent.trim();
                    
                    let likes = 0;
                    const likeEl = card.querySelector('[class*="like"] [class*="count"], [class*="digg"], [data-e2e="video-like-count"]');
                    if (likeEl) {
                        const txt = likeEl.textContent.trim();
                        if (txt.includes('万')) likes = Math.floor(parseFloat(txt) * 10000);
                        else likes = parseInt(txt.replace('+','')) || 0;
                    }
                    
                    let cover = '';
                    const imgEl = card.querySelector('img');
                    if (imgEl) cover = imgEl.getAttribute('src') || '';
                    
                    let videoUrl = '';
                    const linkEl = card.querySelector('a[href*="/video/"]');
                    if (linkEl) {
                        videoUrl = linkEl.getAttribute('href') || '';
                        if (videoUrl.startsWith('/')) videoUrl = 'https://www.douyin.com' + videoUrl;
                    }
                    
                    if (title || videoUrl) {
                        results.push({
                            platform: 'douyin',
                            title: title || '(无标题)',
                            author: author,
                            publish_time: '',
                            likes: likes,
                            comments: 0,
                            favorites: 0,
                            shares: 0,
                            url: videoUrl,
                            cover: cover,
                            keyword: kw || '',
                        });
                    }
                }
                return results;
            }''', [count, keyword])

            return items[:count]

        finally:
            self._close_browser(pw, browser, context)


class ShipinhaoCollector(BaseCollector):
    """WeChat Channels (视频号) collector using Playwright."""

    platform = 'shipinhao'
    cookie_domain = '.qq.com'

    def search(self, keyword, count=20):
        pw, browser, context, page = self._launch_browser()
        try:
            search_url = f'https://channels.weixin.qq.com/web/pages/search?keyword={keyword}'
            page.goto(search_url, wait_until='domcontentloaded', timeout=30000)

            time.sleep(4)

            # Scroll to load more
            for _ in range(3):
                page.evaluate('window.scrollBy(0, 600)')
                time.sleep(1.5)

            items = page.evaluate('''([maxCount, kw]) => {
                const results = [];
                const cards = document.querySelectorAll('[class*="video-item"], [class*="card"], [class*="search-item"], .video-card');
                
                for (const card of cards) {
                    if (results.length >= maxCount) break;
                    
                    let title = '';
                    const titleEl = card.querySelector('[class*="title"], [class*="desc"]');
                    if (titleEl) title = titleEl.textContent.trim();
                    
                    let author = '';
                    const authorEl = card.querySelector('[class*="author"], [class*="nickname"]');
                    if (authorEl) author = authorEl.textContent.trim();
                    
                    let likes = 0;
                    const likeEl = card.querySelector('[class*="like"], [class*="digg"]');
                    if (likeEl) {
                        const txt = likeEl.textContent.trim();
                        if (txt.includes('万')) likes = Math.floor(parseFloat(txt) * 10000);
                        else likes = parseInt(txt) || 0;
                    }
                    
                    let cover = '';
                    const imgEl = card.querySelector('img');
                    if (imgEl) cover = imgEl.getAttribute('src') || '';
                    
                    if (title) {
                        results.push({
                            platform: 'shipinhao',
                            title: title,
                            author: author,
                            publish_time: '',
                            likes: likes,
                            comments: 0,
                            favorites: 0,
                            shares: 0,
                            url: '',
                            cover: cover,
                            keyword: kw || '',
                        });
                    }
                }
                return results;
            }''', [count, keyword])

            return items[:count]

        finally:
            self._close_browser(pw, browser, context)


# ---- Registry ----

COLLECTORS = {
    'douyin': DouyinCollector,
    'xiaohongshu': XiaohongshuCollector,
    'shipinhao': ShipinhaoCollector,
}


def get_collector(platform):
    cls = COLLECTORS.get(platform)
    if not cls:
        return None
    return cls()


def collect_all(keywords=None, platforms=None, count_per_keyword=10):
    """Collect from all enabled platforms."""
    all_items = []
    messages = []

    if platforms is None:
        platforms = ['douyin', 'xiaohongshu', 'shipinhao']

    for platform in platforms:
        config = get_collector_config(platform)
        if config.get('enabled') != 'true':
            continue

        collector = get_collector(platform)
        if not collector:
            continue

        kws = keywords
        if not kws:
            kw_str = config.get('keywords', '')
            kws = [k.strip() for k in kw_str.split(',') if k.strip()]

        if not kws:
            messages.append(f'{platform}: 无关键词')
            continue

        items, msg = collector.collect(kws, count_per_keyword)
        all_items.extend(items)
        messages.append(f'{platform}: {msg}')

    return all_items, '\n'.join(messages)


def analyze_hot_topic(topic_data):
    """Use AI to analyze a hot topic and give it a score."""
    from modules.ai_writer import call_llm

    ai_config = get_ai_config()
    if not ai_config.get('api_key'):
        total_engagement = (
            topic_data.get('likes', 0) +
            topic_data.get('comments', 0) * 3 +
            topic_data.get('favorites', 0) * 2 +
            topic_data.get('shares', 0) * 2
        )
        score = min(100, total_engagement / 100)
        return score, '未配置AI，基于互动量计算基础评分'

    prompt = f"""分析以下{topic_data.get('platform','')}爆款内容，给出1-100的运营价值评分和简短分析。

标题: {topic_data.get('title','')}
作者: {topic_data.get('author','')}
点赞: {topic_data.get('likes',0)}  评论: {topic_data.get('comments',0)}  收藏: {topic_data.get('favorites',0)}

请返回JSON格式:
{{"score": 85, "analysis": "简短分析（为什么有运营价值，适合什么方向）"}}"""

    try:
        result, _tokens, _model = call_llm(prompt, temperature=0.3, max_tokens=500)
        json_match = re.search(r'\{[^}]+\}', result)
        if json_match:
            parsed = json.loads(json_match.group())
            return float(parsed.get('score', 0)), parsed.get('analysis', '')
        return 50, result[:200]
    except Exception as e:
        return 0, f'AI分析失败: {str(e)}'
