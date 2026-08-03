"""
Auto-publishing module - uses Playwright browser automation.

Since most platforms (especially WeChat Channels/视频号) don't have open APIs
for content publishing, we use browser automation to:
  1. Open the platform's creator/upload page
  2. Fill in title, description, tags
  3. Upload the video file
  4. Let the user review and click publish (semi-automatic)

浏览器会在后台线程里保持打开，直到用户手动关闭窗口、调用 close_session，
或超过 keep_open_minutes（默认 60 分钟）。

登录态使用 persistent context 落盘到 data/browser_profiles/<platform>，
所以视频号这类需要扫码的平台，扫一次之后下次不用再扫。

Playwright needs to be installed: pip install playwright && playwright install chromium
"""

import os
import threading
import time
import uuid
from datetime import datetime

from config import get_publish_config, get_setting, BASE_DIR


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

# session_id -> session dict
_SESSIONS = {}
_SESSIONS_LOCK = threading.Lock()


def _platform_meta(platform):
    """Resolve platform label / creator_url / cookie_domain from registry."""
    try:
        from modules.content_ops.platforms import get_platform
        meta = get_platform(platform) or {}
    except Exception:
        meta = {}
    return {
        'label': meta.get('label') or PLATFORM_NAMES.get(platform, platform),
        'creator_url': meta.get('creator_url') or PLATFORM_URLS.get(platform, ''),
        'cookie_domain': meta.get('cookie_domain') or '',
    }


def check_playwright():
    """Check if Playwright is installed."""
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def _profile_dir(platform):
    path = os.path.join(BASE_DIR, 'data', 'browser_profiles', platform or 'default')
    os.makedirs(path, exist_ok=True)
    return path


def _keep_open_seconds():
    try:
        return max(60, int(get_setting('publish', 'keep_open_minutes', '60') or 60) * 60)
    except Exception:
        return 3600


# ---------------- session management ----------------

def _new_session(platform, label):
    sid = uuid.uuid4().hex[:12]
    session = {
        'id': sid,
        'platform': platform,
        'label': label,
        'status': 'starting',
        'message': '正在启动浏览器…',
        'warnings': [],
        'logged_in': None,
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'ready': threading.Event(),
        'stop': threading.Event(),
    }
    with _SESSIONS_LOCK:
        _SESSIONS[sid] = session
    return session


def list_sessions():
    with _SESSIONS_LOCK:
        items = list(_SESSIONS.values())
    return [
        {
            'id': s['id'],
            'platform': s['platform'],
            'label': s['label'],
            'status': s['status'],
            'message': s['message'],
            'warnings': s['warnings'],
            'logged_in': s['logged_in'],
            'created_at': s['created_at'],
        }
        for s in items
        if s['status'] not in ('closed', 'error')
    ]


def close_session(sid):
    with _SESSIONS_LOCK:
        session = _SESSIONS.get(sid)
    if not session:
        return {'status': 'error', 'message': '会话不存在或已关闭'}
    session['stop'].set()
    return {'status': 'ok', 'message': '已请求关闭浏览器'}


def _drop_session(sid):
    with _SESSIONS_LOCK:
        _SESSIONS.pop(sid, None)


# ---------------- public entry ----------------

def publish_video(platform, video_path, title, description, tags, cover_text=''):
    """
    打开平台创作后台、填充内容，浏览器保持打开等待人工确认发布。
    立即返回（不阻塞到用户点发布），返回体里带 session_id。
    """
    meta = _platform_meta(platform)
    label = meta['label']
    config = get_publish_config(platform)
    if config.get('enabled') != 'true':
        return {
            'status': 'skipped',
            'message': f'{label} 发布未启用，请在设置中开启',
        }

    if not meta['creator_url']:
        return {
            'status': 'error',
            'message': f'{label} 未配置创作者后台地址，请在平台管理中补充 creator_url',
        }

    if not check_playwright():
        return {
            'status': 'error',
            'message': 'Playwright 未安装。请运行: pip install playwright && playwright install chromium',
        }

    if not video_path or not os.path.exists(video_path):
        return {
            'status': 'error',
            'message': f'视频文件不存在: {video_path}',
        }

    session = _new_session(platform, label)
    args = (session, meta, video_path, title or '', description or '',
            tags or '', config.get('cookies', ''))
    threading.Thread(target=_session_worker, args=args, daemon=True).start()

    # 等待页面就绪/填充完成，最多 120 秒；超时也不杀浏览器
    session['ready'].wait(timeout=120)

    if session['status'] in ('error', 'page_error'):
        return {'status': 'error', 'message': session['message'], 'session_id': session['id']}

    msg = session['message'] or f'已打开{label}发布页面，请在浏览器中确认后点击发布'
    if session['warnings']:
        msg = f"{msg}（{'；'.join(session['warnings'])}）"

    return {
        'status': 'pending_review',
        'message': msg,
        'browser_opened': True,
        'session_id': session['id'],
        'logged_in': session['logged_in'],
    }


# ---------------- worker ----------------

def _session_worker(session, meta, video_path, title, description, tags, cookies_str):
    from playwright.sync_api import sync_playwright

    platform = session['platform']
    label = session['label']
    context = None
    try:
        profile = _profile_dir(platform)
        had_profile = bool(os.listdir(profile))
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                profile,
                headless=False,
                no_viewport=True,
                args=['--start-maximized', '--disable-blink-features=AutomationControlled'],
            )

            # 已有本地登录态时不再注入 Cookies，避免过期 Cookie 覆盖有效登录
            if not had_profile:
                cookies = _parse_cookies(cookies_str, platform, cookie_domain=meta.get('cookie_domain'))
                if cookies:
                    try:
                        context.add_cookies(cookies)
                    except Exception as e:
                        session['warnings'].append(f'Cookies 注入失败: {e}')

            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(20000)

            nav_error = ''
            try:
                page.goto(meta['creator_url'], wait_until='domcontentloaded', timeout=60000)
            except Exception as e:
                nav_error = _nav_error_hint(e)
            page.wait_for_timeout(3000)

            if nav_error:
                session['status'] = 'page_error'
                session['message'] = f'{label} {nav_error}'
                session['ready'].set()
            elif _looks_like_login(page):
                session['logged_in'] = False
                session['status'] = 'need_login'
                session['message'] = (
                    f'{label} 未登录，浏览器已打开并保持不关闭：请扫码/登录后手动上传发布。'
                    f'登录状态会被记住，下次不用再登录。'
                )
                session['ready'].set()
            else:
                session['logged_in'] = True
                try:
                    _fill_platform(platform, page, video_path, title, description, tags, session)
                    session['status'] = 'pending_review'
                    session['message'] = f'已打开{label}发布页面并填充内容，请在浏览器中确认后点击发布'
                except Exception as e:
                    session['status'] = 'pending_review'
                    session['warnings'].append(f'自动填充部分失败: {e}')
                    session['message'] = f'{label} 页面已打开，自动填充未完全成功，请手动补齐后发布'
                session['ready'].set()

            # 保持浏览器打开，直到用户关窗 / 手动关闭 / 超时
            deadline = time.time() + _keep_open_seconds()
            while time.time() < deadline and not session['stop'].is_set():
                try:
                    if not context.pages:
                        break
                except Exception:
                    break
                time.sleep(1.5)

            session['status'] = 'closed'
            session['message'] = f'{label} 浏览器已关闭'
            try:
                context.close()
            except Exception:
                pass
    except Exception as e:
        session['status'] = 'error'
        session['message'] = f'发布失败: {e}'
        session['ready'].set()
    finally:
        session['ready'].set()
        threading.Timer(120, _drop_session, args=(session['id'],)).start()


def _nav_error_hint(err):
    """把 Chromium 的网络错误翻译成可操作的提示。"""
    text = str(err)
    if 'ERR_NAME_NOT_RESOLVED' in text:
        return '页面打不开：本机 DNS 解析失败（域名解析不出 IP）。请检查网络/VPN，或把网卡 DNS 改成 223.5.5.5'
    if 'ERR_PROXY_CONNECTION_FAILED' in text:
        return '页面打不开：代理连接失败，请检查系统代理或科学上网工具是否在运行'
    if 'ERR_INTERNET_DISCONNECTED' in text:
        return '页面打不开：本机没有可用网络连接'
    if 'ERR_CONNECTION_TIMED_OUT' in text or 'Timeout' in text:
        return '页面加载超时，请检查网络后重试'
    return f'页面加载失败: {text.splitlines()[0]}'


def _looks_like_login(page):
    """URL 跳转到登录页，或页面上摆着扫码登录框，都算未登录。"""
    try:
        url = (page.url or '').lower()
    except Exception:
        return False
    if any(k in url for k in ('login', 'signin', 'passport', 'auth')):
        return True

    for sel in ('.login-container', '.login-box', '.qrcode-login',
                '[class*="login-panel"]', '[class*="qrcode"]'):
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                return True
        except Exception:
            continue
    return False


# ---------------- filling helpers ----------------

def _set_video(page, video_path, accept_video_first=True, timeout=15000):
    """找到 file input 并塞视频（隐藏的 input 也可以）。"""
    selectors = ['input[type="file"][accept*="video"]', 'input[type="file"]'] \
        if accept_video_first else ['input[type="file"]']
    deadline = time.time() + timeout / 1000
    while time.time() < deadline:
        for sel in selectors:
            for el in page.query_selector_all(sel):
                try:
                    el.set_input_files(video_path)
                    return True
                except Exception:
                    continue
        page.wait_for_timeout(1000)
    return False


def _fill_first(page, selectors, text, clear=True):
    """按顺序尝试选择器，支持普通输入框和 contenteditable。"""
    if not text:
        return True
    for sel in selectors:
        for el in page.query_selector_all(sel):
            try:
                if not el.is_visible():
                    continue
            except Exception:
                continue
            try:
                el.click()
                editable = el.get_attribute('contenteditable')
                if editable in ('', 'true'):
                    if clear:
                        page.keyboard.press('Control+A')
                        page.keyboard.press('Delete')
                    page.keyboard.insert_text(text)
                else:
                    el.fill('')
                    el.type(text, delay=10)
                return True
            except Exception:
                continue
    return False


def _click_text(page, texts, timeout=4000):
    for t in texts:
        try:
            loc = page.get_by_text(t, exact=False).first
            loc.click(timeout=timeout)
            return True
        except Exception:
            continue
    return False


def _fill_platform(platform, page, video_path, title, description, tags, session):
    if platform == 'douyin':
        _upload_douyin(page, video_path, title, description, tags, session)
    elif platform == 'xiaohongshu':
        _upload_xiaohongshu(page, video_path, title, description, tags, session)
    elif platform == 'shipinhao':
        _upload_shipinhao(page, video_path, title, description, tags, session)
    else:
        _upload_generic(page, video_path, title, description, tags, session)


def _upload_generic(page, video_path, title, description, tags, session):
    if not _set_video(page, video_path):
        session['warnings'].append('未找到上传控件，请手动选择视频')
    page.wait_for_timeout(4000)

    _fill_first(page, [
        'input[placeholder*="标题"]', 'textarea[placeholder*="标题"]',
        '[placeholder*="标题"]',
    ], (title or '')[:80])

    full_desc = f'{description or ""}\n{tags or ""}'.strip()
    _fill_first(page, [
        'div[contenteditable="true"]',
        'textarea[placeholder*="描述"]', 'textarea[placeholder*="简介"]',
        'textarea[placeholder*="文案"]', 'textarea',
    ], full_desc[:1000])


def _upload_douyin(page, video_path, title, description, tags, session):
    if not _set_video(page, video_path):
        session['warnings'].append('未找到上传控件，请手动选择视频')
        return
    # 抖音上传后会跳到编辑页
    try:
        page.wait_for_url('**/content/publish**', timeout=60000)
    except Exception:
        pass
    page.wait_for_timeout(4000)

    _fill_first(page, [
        'input[placeholder*="作品标题"]', 'input[placeholder*="标题"]',
        '.title input', 'input.semi-input',
    ], (title or '')[:30])

    full_desc = f'{description or ""}\n{tags or ""}'.strip()
    if not _fill_first(page, [
        '.zone-container[contenteditable="true"]',
        'div[data-placeholder*="作品简介"]',
        'div[contenteditable="true"]',
    ], full_desc[:900]):
        session['warnings'].append('简介未自动填充')


def _upload_xiaohongshu(page, video_path, title, description, tags, session):
    # 小红书默认可能停在“上传图文”，需要先切到“上传视频”
    _click_text(page, ['上传视频'])
    page.wait_for_timeout(1500)

    if not _set_video(page, video_path):
        session['warnings'].append('未找到上传控件，请手动选择视频')
        return

    # 等待进入编辑表单（标题框出现）
    appeared = False
    for _ in range(60):
        if page.query_selector('input[placeholder*="标题"], .d-text[placeholder*="标题"]'):
            appeared = True
            break
        page.wait_for_timeout(1000)
    if not appeared:
        session['warnings'].append('视频仍在上传中，表单未就绪，请稍后手动填写')
        return

    if not _fill_first(page, [
        'input[placeholder*="标题"]', '.d-text[placeholder*="标题"]',
        '.title input', 'input.title',
    ], (title or '')[:20]):
        session['warnings'].append('标题未自动填充')

    full_desc = f'{description or ""}\n{tags or ""}'.strip()
    if not _fill_first(page, [
        '.ql-editor[contenteditable="true"]',
        'div[contenteditable="true"]',
        'textarea[placeholder*="正文"]',
    ], full_desc[:900]):
        session['warnings'].append('正文未自动填充')


def _upload_shipinhao(page, video_path, title, description, tags, session):
    if not _set_video(page, video_path):
        session['warnings'].append('未找到上传控件，请手动选择视频')
        return
    page.wait_for_timeout(5000)

    full_desc = f'{description or ""}\n{tags or ""}'.strip()
    if not _fill_first(page, [
        '.input-editor[contenteditable="true"]',
        'div[contenteditable="true"]',
        '.weui-desktop-form__input',
    ], full_desc[:900]):
        session['warnings'].append('描述未自动填充')

    _fill_first(page, [
        'input[placeholder*="概括视频主要内容"]',
        'input[placeholder*="短标题"]',
        'input[placeholder*="标题"]',
    ], (title or '')[:16])


def _parse_cookies(cookies_str, domain, cookie_domain=''):
    """Parse cookie string into Playwright cookie format."""
    if not cookies_str:
        return []

    domain_map = {
        'douyin': '.douyin.com',
        'xiaohongshu': '.xiaohongshu.com',
        'shipinhao': '.weixin.qq.com',
    }
    # 视频号 Cookie 属于 channels.weixin.qq.com，注册表里的 .qq.com 太宽会登录不上
    if domain == 'shipinhao' and cookie_domain in ('', '.qq.com', 'qq.com'):
        cookie_domain = '.weixin.qq.com'
    if not cookie_domain:
        cookie_domain = domain_map.get(domain, '')
    if not cookie_domain:
        try:
            from modules.content_ops.platforms import get_platform
            meta = get_platform(domain) or {}
            cookie_domain = meta.get('cookie_domain') or ''
        except Exception:
            cookie_domain = ''
    if not cookie_domain:
        return []

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
    meta = _platform_meta(platform)
    config = get_publish_config(platform)
    profile = os.path.join(BASE_DIR, 'data', 'browser_profiles', platform)
    return {
        'enabled': config.get('enabled') == 'true',
        'has_cookies': bool(config.get('cookies')),
        'has_profile': os.path.isdir(profile) and bool(os.listdir(profile)),
        'playwright_installed': check_playwright(),
        'platform_name': meta['label'],
        'creator_url': meta['creator_url'],
    }
