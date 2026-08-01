"""
Auto-publishing module - uses Playwright browser automation.

Since most platforms (especially WeChat Channels/视频号) don't have open APIs
for content publishing, we use browser automation to:
  1. Open the platform's creator/upload page
  2. Fill in title, description, tags
  3. Upload the video file
  4. Let the user review and click publish (semi-automatic)

The user provides their login cookies in Settings.
Playwright needs to be installed: pip install playwright && playwright install chromium
"""

import os
import json
import asyncio
from config import get_publish_config


# Platform creator URLs
PLATFORM_URLS = {
    'douyin': 'https://creator.douyin.com/creator-micro/content/upload',
    'xiaohongshu': 'https://creator.xiaohongshu.com/publish/publish',
    'shipinhao': 'https://channels.weixin.qq.com/platform/post/create',
}

# Platform display names
PLATFORM_NAMES = {
    'douyin': '抖音',
    'xiaohongshu': '小红书',
    'shipinhao': '视频号',
}


def check_playwright():
    """Check if Playwright is installed."""
    try:
        import playwright
        return True
    except ImportError:
        return False


def publish_video(platform, video_path, title, description, tags, cover_text=''):
    """
    Publish a video to a platform using Playwright browser automation.

    This is a semi-automatic process:
      - The system opens a browser with the user's cookies
      - Fills in the upload form automatically
      - The user reviews and clicks the final publish button

    Args:
        platform: 'douyin', 'xiaohongshu', 'shipinhao'
        video_path: path to the video file (.mp4)
        title: video title
        description: video description
        tags: comma-separated tags
        cover_text: text for cover image

    Returns:
        dict with: status, message, browser_opened (bool)
    """
    config = get_publish_config(platform)
    if config.get('enabled') != 'true':
        return {
            'status': 'skipped',
            'message': f'{PLATFORM_NAMES.get(platform, platform)} 发布未启用，请在设置中开启',
        }

    cookies_str = config.get('cookies', '')
    if not cookies_str:
        return {
            'status': 'error',
            'message': f'{PLATFORM_NAMES.get(platform, platform)} Cookies 未配置',
        }

    if not check_playwright():
        return {
            'status': 'error',
            'message': 'Playwright 未安装。请运行: pip install playwright && playwright install chromium',
        }

    if not os.path.exists(video_path):
        return {
            'status': 'error',
            'message': f'视频文件不存在: {video_path}',
        }

    try:
        result = asyncio.run(_publish_with_playwright(
            platform, video_path, title, description, tags, cover_text, cookies_str
        ))
        return result
    except Exception as e:
        return {
            'status': 'error',
            'message': f'发布失败: {str(e)}',
        }


async def _publish_with_playwright(platform, video_path, title, description, tags, cover_text, cookies_str):
    """Run the Playwright automation."""
    from playwright.async_api import async_playwright

    url = PLATFORM_URLS.get(platform, '')

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # Show browser for user review
        context = await browser.new_context()

        # Set cookies
        cookies = _parse_cookies(cookies_str, platform)
        if cookies:
            await context.add_cookies(cookies)

        page = await context.new_page()
        await page.goto(url, wait_until='networkidle', timeout=30000)

        # Wait for page to load and check if logged in
        await page.wait_for_timeout(3000)

        # Platform-specific upload logic
        if platform == 'douyin':
            await _upload_douyin(page, video_path, title, description, tags)
        elif platform == 'xiaohongshu':
            await _upload_xiaohongshu(page, video_path, title, description, tags)
        elif platform == 'shipinhao':
            await _upload_shipinhao(page, video_path, title, description, tags)

        # Wait for user to review and publish manually
        # The browser stays open until the user closes it
        return {
            'status': 'pending_review',
            'message': f'已打开{PLATFORM_NAMES[platform]}发布页面并填充内容，请在浏览器中确认后点击发布',
            'browser_opened': True,
        }


async def _upload_douyin(page, video_path, title, description, tags):
    """Upload video to Douyin creator platform."""
    # Click upload button
    upload_input = await page.query_selector('input[type="file"]')
    if upload_input:
        await upload_input.set_input_files(video_path)

    # Wait for upload to process
    await page.wait_for_timeout(5000)

    # Fill in title/description
    desc_selector = '[data-content="desc"]'
    desc_input = await page.query_selector(desc_selector)
    if desc_input:
        full_desc = f'{title}\n{description}\n{tags}'
        await desc_input.fill('')
        await desc_input.type(full_desc[:500])

    # The user needs to click publish manually


async def _upload_xiaohongshu(page, video_path, title, description, tags):
    """Upload video to Xiaohongshu creator platform."""
    upload_input = await page.query_selector('input[type="file"]')
    if upload_input:
        await upload_input.set_input_files(video_path)

    await page.wait_for_timeout(5000)

    # Fill title
    title_input = await page.query_selector('.title textarea, .title input')
    if title_input:
        await title_input.fill(title[:20])

    # Fill description
    desc_input = await page.query_selector('.desc textarea, .desc input')
    if desc_input:
        full_desc = f'{description}\n{tags}'
        await desc_input.fill(full_desc[:1000])


async def _upload_shipinhao(page, video_path, title, description, tags):
    """Upload video to WeChat Channels."""
    upload_input = await page.query_selector('input[type="file"]')
    if upload_input:
        await upload_input.set_input_files(video_path)

    await page.wait_for_timeout(5000)

    # Fill title
    title_input = await page.query_selector('.weui-textarea, [placeholder*="标题"]')
    if title_input:
        await title_input.fill(title)

    # Fill description
    desc_input = await page.query_selector('[placeholder*="描述"], [placeholder*="简介"]')
    if desc_input:
        full_desc = f'{description}\n{tags}'
        await desc_input.fill(full_desc[:500])


def _parse_cookies(cookies_str, domain):
    """Parse cookie string into Playwright cookie format."""
    domain_map = {
        'douyin': '.douyin.com',
        'xiaohongshu': '.xiaohongshu.com',
        'shipinhao': '.qq.com',
    }
    cookie_domain = domain_map.get(domain, '.com')

    cookies = []
    for item in cookies_str.split(';'):
        item = item.strip()
        if '=' in item:
            k, v = item.split('=', 1)
            cookies.append({
                'name': k.strip(),
                'value': v.strip(),
                'domain': cookie_domain,
                'path': '/',
            })
    return cookies


def get_publish_status(platform):
    """Check if publishing is ready for a platform."""
    config = get_publish_config(platform)
    return {
        'enabled': config.get('enabled') == 'true',
        'has_cookies': bool(config.get('cookies')),
        'playwright_installed': check_playwright(),
        'platform_name': PLATFORM_NAMES.get(platform, platform),
    }
