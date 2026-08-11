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
import re
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

# 创作者「作品管理」页（用于同步链接与互动）
MANAGE_URLS = {
    'douyin': 'https://creator.douyin.com/creator-micro/content/manage',
    'xiaohongshu': 'https://creator.xiaohongshu.com/new/note-manager',
    'shipinhao': 'https://channels.weixin.qq.com/platform/post/list',
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

_CONTENT_URL_HINTS = (
    'douyin.com/video/',
    'v.douyin.com/',
    'xiaohongshu.com/explore/',
    'xiaohongshu.com/discovery/item/',
    'xhslink.com/',
    'weixin.qq.com/sph/',
    'channels.weixin.qq.com/web/',
    'channels.weixin.qq.com/mobile/',
)
_EXCLUDE_URL_HINTS = (
    'upload', 'publish/publish', 'post/create', 'login', 'passport',
    'developers.weixin.qq.com', 'platform/post/list', 'platform/post/create',
    'miniprogram/dev', 'doc.weixin', 'support.weixin', '/platform/',
)


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
    """Check if Playwright + Chromium are available."""
    try:
        from modules.playwright_env import ensure_playwright_browsers_path, playwright_chromium_ready
        ensure_playwright_browsers_path()
        ok, _msg = playwright_chromium_ready()
        return bool(ok)
    except Exception:
        try:
            import playwright  # noqa: F401
            return True
        except ImportError:
            return False


def _profile_dir(platform):
    path = os.path.join(BASE_DIR, 'data', 'browser_profiles', platform or 'default')
    os.makedirs(path, exist_ok=True)
    return path


def _clear_profile_locks(profile):
    """清理 Chromium 残留锁文件，避免「目录正被使用 / 启动即关闭」。"""
    for name in (
        'SingletonLock', 'SingletonCookie', 'SingletonSocket',
        'lockfile', 'RunningChromeVersion',
    ):
        path = os.path.join(profile, name)
        try:
            if os.path.isfile(path) or os.path.islink(path):
                os.remove(path)
        except Exception:
            pass


def _kill_stale_profile_browsers(profile):
    """结束仍占用该 user-data-dir 的 chrome/chromium 进程（Windows 常见残留）。"""
    if os.name != 'nt':
        return
    needle = os.path.normcase(os.path.abspath(profile))
    try:
        import subprocess
        ps = (
            "Get-CimInstance Win32_Process | "
            "Where-Object { $_.Name -match 'chrome|chromium' -and $_.CommandLine } | "
            "ForEach-Object { "
            f"if ($_.CommandLine -like '*{needle.replace(chr(39), '')}*') "
            "{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } }"
        )
        subprocess.run(
            ['powershell', '-NoProfile', '-Command', ps],
            capture_output=True, text=True, timeout=15,
        )
    except Exception:
        pass


def _stop_platform_sessions(platform, except_id=None):
    """关闭同平台已有会话，避免重复占用同一 profile。"""
    with _SESSIONS_LOCK:
        targets = [
            s for s in _SESSIONS.values()
            if s.get('platform') == platform
            and s.get('id') != except_id
            and s.get('status') not in ('closed', 'error')
        ]
    if not targets:
        return
    for s in targets:
        s['stop'].set()
    # 等旧会话有机会关掉浏览器
    time.sleep(2)


def _launch_persistent(playwright, profile):
    """启动持久化浏览器；失败则清锁/杀残留后重试一次。"""
    from modules.playwright_env import ensure_playwright_browsers_path
    ensure_playwright_browsers_path()
    last_err = None
    for attempt in range(2):
        _clear_profile_locks(profile)
        if attempt > 0:
            _kill_stale_profile_browsers(profile)
            time.sleep(1.5)
            _clear_profile_locks(profile)
        try:
            return playwright.chromium.launch_persistent_context(
                profile,
                headless=False,
                no_viewport=True,
                args=[
                    '--start-maximized',
                    '--disable-blink-features=AutomationControlled',
                    '--no-first-run',
                    '--no-default-browser-check',
                ],
                ignore_default_args=['--enable-automation'],
            )
        except Exception as e:
            last_err = e
            msg = str(e).lower()
            retryable = any(k in msg for k in (
                'has been closed', 'target page', 'user data directory',
                'singleton', 'process', 'browser has been closed',
            ))
            if not retryable or attempt >= 1:
                break
            time.sleep(1)
    raise last_err


def _launch_error_hint(err, profile, label):
    text = str(err)
    if "Executable doesn't exist" in text or 'cursor-sandbox-cache' in text:
        return (
            f'{label} 浏览器启动失败：未找到 Chromium。'
            f'请在仓库根目录执行：.venv\\Scripts\\python.exe -m playwright install chromium'
            f'；若从 Cursor 启动后端，请用 start_backend.bat（会清除错误的 PLAYWRIGHT_BROWSERS_PATH）。'
        )
    if 'has been closed' in text or 'Target page' in text:
        return (
            f'{label} 浏览器启动失败：配置目录可能被占用或已损坏。'
            f'请先关闭所有 Chromium/Chrome 窗口后重试；'
            f'仍失败可删除目录后重登：{profile}'
        )
    return f'{label} 浏览器启动失败: {text.splitlines()[0]}'


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
            'task_id': s.get('task_id'),
            'detected_url': s.get('detected_url') or '',
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

def publish_video(platform, video_path, title, description, tags, cover_text='', task_id=None):
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
    session['task_id'] = task_id
    session['title'] = title or ''
    session['detected_url'] = ''
    args = (session, meta, video_path, title or '', description or '',
            tags or '', config.get('cookies', ''))
    threading.Thread(target=_session_worker, args=args, daemon=True).start()

    # 等待页面就绪/填充完成，最多 120 秒；超时也不杀浏览器
    session['ready'].wait(timeout=120)

    if session['status'] in ('error', 'page_error'):
        return {'status': 'error', 'message': session['message'], 'session_id': session['id']}

    if session['status'] == 'need_login':
        return {
            'status': 'need_login',
            'message': session['message'] or f'{label} 需要登录，请在已打开的浏览器中扫码登录',
            'browser_opened': True,
            'session_id': session['id'],
            'logged_in': False,
        }

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
        # 同平台只保留一个浏览器，避免 profile 互锁
        _stop_platform_sessions(platform, except_id=session['id'])

        profile = _profile_dir(platform)
        had_profile = bool(os.listdir(profile))
        with sync_playwright() as p:
            try:
                context = _launch_persistent(p, profile)
            except Exception as e:
                session['status'] = 'error'
                session['message'] = _launch_error_hint(e, profile, label)
                session['ready'].set()
                return

            # 已有本地登录态时不再注入 Cookies，避免过期 Cookie 覆盖有效登录
            if not had_profile:
                cookies = _parse_cookies(cookies_str, platform, cookie_domain=meta.get('cookie_domain'))
                if cookies:
                    try:
                        context.add_cookies(cookies)
                    except Exception as e:
                        session['warnings'].append(f'Cookies 注入失败: {e}')

            try:
                page = context.pages[0] if context.pages else context.new_page()
            except Exception as e:
                session['status'] = 'error'
                session['message'] = _launch_error_hint(e, profile, label)
                session['ready'].set()
                try:
                    context.close()
                except Exception:
                    pass
                return
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
            elif _looks_like_login(page, platform):
                # profile 无效时，再尝试注入设置里的 Cookies
                cookies = _parse_cookies(
                    cookies_str, platform, cookie_domain=meta.get('cookie_domain')
                )
                if cookies:
                    try:
                        context.add_cookies(cookies)
                        page.goto(meta['creator_url'], wait_until='domcontentloaded', timeout=60000)
                        page.wait_for_timeout(3000)
                    except Exception as e:
                        session['warnings'].append(f'登录态 Cookies 注入失败: {e}')

                if _looks_like_login(page, platform):
                    session['logged_in'] = False
                    session['status'] = 'need_login'
                    session['message'] = (
                        f'{label} 未登录：请在已打开的浏览器中扫码/登录。'
                        f'登录成功后会自动继续上传并填充；登录状态会记住，下次不用再登。'
                    )
                    session['ready'].set()
                    logged_in = _wait_until_logged_in(
                        page, platform, session, timeout_sec=300
                    )
                    if logged_in:
                        session['logged_in'] = True
                        try:
                            if not _on_publish_page(page, platform):
                                page.goto(meta['creator_url'], wait_until='domcontentloaded', timeout=60000)
                                page.wait_for_timeout(2500)
                            _fill_platform(platform, page, video_path, title, description, tags, session)
                            session['status'] = 'pending_review'
                            session['message'] = (
                                f'登录成功，已打开{label}发布页并填充内容，请在浏览器中确认后点击发布'
                            )
                        except Exception as e:
                            session['status'] = 'pending_review'
                            session['warnings'].append(f'自动填充部分失败: {e}')
                            session['message'] = (
                                f'登录成功，{label} 页面已打开，自动填充未完全成功，请手动补齐后发布'
                            )
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
            # 期间尽量捕捉作品链接，并处理「同步互动」请求
            deadline = time.time() + _keep_open_seconds()
            while time.time() < deadline and not session['stop'].is_set():
                try:
                    if not context.pages:
                        break
                except Exception:
                    break
                try:
                    active = context.pages[0]
                    _maybe_capture_publish_url(session, active)
                    req = session.pop('sync_request', None)
                    if req:
                        try:
                            session['sync_result'] = _scrape_manage_page(
                                active, platform, req.get('title') or session.get('title') or '',
                            )
                        except Exception as e:
                            session['sync_result'] = {'ok': False, 'error': str(e)}
                        done = session.get('sync_done')
                        if done:
                            done.set()
                except Exception:
                    pass
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


def _is_content_url(url):
    u = (url or '').lower()
    if not u.startswith('http'):
        return False
    if any(x in u for x in _EXCLUDE_URL_HINTS):
        return False
    if any(x in u for x in _CONTENT_URL_HINTS):
        return True
    if re.search(r'weixin\.qq\.com/sph[/?#]', u):
        return True
    if re.search(r'channels\.weixin\.qq\.com/.+(feed|share|export)', u):
        return True
    return False


def _sanitize_engagement(likes, comments):
    """过滤把日期误当成赞评的情况（如 2026/8）。"""
    try:
        likes = int(likes or 0)
    except Exception:
        likes = 0
    try:
        comments = int(comments or 0)
    except Exception:
        comments = 0
    # 年份误判
    if 1900 <= likes <= 2100 and 1 <= comments <= 31:
        return 0, 0
    # 过大不合理
    if likes > 10_000_000:
        likes = 0
    if comments > 10_000_000:
        comments = 0
    return max(0, likes), max(0, comments)


def _detect_url_from_page(page):
    """从当前页 URL 或页面链接里尽量找出作品公开链。"""
    try:
        cur = page.url or ''
    except Exception:
        cur = ''
    if _is_content_url(cur):
        return cur
    try:
        hrefs = page.eval_on_selector_all(
            'a[href]',
            'els => els.map(e => e.href).filter(Boolean)',
        ) or []
    except Exception:
        hrefs = []
    for h in hrefs:
        if _is_content_url(h):
            return h
    # 正文里可能出现分享短链
    try:
        text = page.inner_text('body', timeout=1500) or ''
        for m in re.finditer(r'https?://[^\s\"\'<>]+', text):
            if _is_content_url(m.group(0)):
                return m.group(0).rstrip('.,);]')
    except Exception:
        pass
    return ''


def _write_task_publish_url(task_id, url):
    if not task_id or not url:
        return
    try:
        from config import get_db
        conn = get_db()
        conn.execute(
            "UPDATE publish_task SET publish_url=? "
            "WHERE id=? AND (publish_url IS NULL OR publish_url='')",
            (url, int(task_id)),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def _maybe_capture_publish_url(session, page):
    if session.get('detected_url'):
        return
    url = _detect_url_from_page(page)
    if not url:
        return
    session['detected_url'] = url
    session['message'] = f"已检测到作品链接，确认时可自动回填"
    _write_task_publish_url(session.get('task_id'), url)


def _parse_cn_count(text):
    """解析 1.2万 / 3千 / 128 等中文互动数。"""
    if text is None:
        return 0
    s = str(text).strip().replace(',', '').replace(' ', '')
    if not s or s in ('-', '—', '赞', '评论'):
        return 0
    m = re.match(r'^([\d.]+)\s*([万wW千kK])?', s)
    if not m:
        digits = re.sub(r'[^\d]', '', s)
        return int(digits) if digits else 0
    num = float(m.group(1))
    unit = (m.group(2) or '').lower()
    if unit in ('万', 'w'):
        num *= 10000
    elif unit in ('千', 'k'):
        num *= 1000
    return int(num)


def _title_match_keys(title, platform=''):
    """生成用于作品列表匹配的标题关键字（短标题 / 截断 / 去标点）。"""
    raw = (title or '').strip()
    keys = []
    if not raw:
        return keys

    def add(s):
        s = (s or '').strip()
        if not s:
            return
        if s not in keys:
            keys.append(s)

    add(raw)
    add(raw[:24])
    add(raw[:16])
    add(raw[:12])
    add(raw[:8])
    if platform == 'shipinhao':
        add(_shipinhao_short_title(raw))
    # 去常见标点后再取前缀
    compact = re.sub(r'[\s\-_|｜·•，。！？、：:；;（）()【】\[\]《》<>\"\'“”‘’]+', '', raw)
    add(compact[:16])
    add(compact[:12])
    add(compact[:8])
    # 过滤太短的无意义键
    return [k for k in keys if len(k) >= 4]


def _page_looks_like_login_or_qr(page):
    """作品管理页若落在登录墙 / 微信扫码观看页，则无法刮取列表。"""
    try:
        url = (page.url or '').lower()
    except Exception:
        url = ''
    if any(x in url for x in ('login', 'passport', 'signin', 'sso')):
        return True
    try:
        text = page.inner_text('body', timeout=2000) or ''
    except Exception:
        text = ''
    markers = (
        '扫码登录', '手机号登录', '请使用微信扫码', '可扫码前往微信观看',
        '扫码关注', '登录后查看', '微信扫一扫登录',
    )
    return any(m in text for m in markers)


def _scrape_roots(page):
    """主文档 + iframe（视频号 wujie /micro/ 优先）。"""
    roots = []
    try:
        frames = list(page.frames)
        micro = [f for f in frames if '/micro/' in (f.url or '')]
        others = [f for f in frames if f not in micro]
        # Frame 自身可 evaluate；page 用 main frame
        for f in micro + others:
            roots.append(f)
    except Exception:
        pass
    if not roots:
        roots = [page]
    return roots


def _scrape_manage_page(page, platform, title, navigate=True):
    """在创作者作品管理页按标题匹配，提取链接与点赞/评论（尽力而为）。"""
    manage = MANAGE_URLS.get(platform) or ''
    if navigate and manage:
        try:
            page.goto(manage, wait_until='domcontentloaded', timeout=60000)
            page.wait_for_timeout(2500)
            try:
                page.wait_for_function(
                    "() => !!(document.body && document.body.innerText && document.body.innerText.length > 80)",
                    timeout=8000,
                )
            except Exception:
                pass
            page.wait_for_timeout(2000)
            try:
                page.mouse.wheel(0, 1200)
                page.wait_for_timeout(800)
                page.mouse.wheel(0, -600)
                page.wait_for_timeout(500)
            except Exception:
                pass
        except Exception as e:
            return {'ok': False, 'error': f'打开作品管理页失败: {e}'}

    if _page_looks_like_login_or_qr(page):
        return {
            'ok': False,
            'error': '创作者后台未登录或落在扫码页。请先用「浏览器发布」扫码登录，保持登录后再点同步',
        }

    title_keys = _title_match_keys(title, platform)
    scrape_js = """
    (payload) => {
      const titleKeys = (payload && payload.keys) || [];
      const platform = (payload && payload.platform) || '';
      const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim();
      const parseNum = (s) => {
        s = String(s || '').trim().replace(/,/g, '');
        if (!s) return 0;
        const m = s.match(/^([\\d.]+)\\s*([万wW千kK])?$/);
        if (!m) return 0;
        let n = parseFloat(m[1]);
        if (!isFinite(n)) return 0;
        const u = (m[2] || '').toLowerCase();
        if (u === '万' || u === 'w') n *= 10000;
        if (u === '千' || u === 'k') n *= 1000;
        return Math.round(n);
      };
      const stripDateNoise = (s) => String(s || '')
        .replace(/\\d{4}\\s*年\\s*\\d{1,2}\\s*月\\s*\\d{1,2}\\s*日/g, ' ')
        .replace(/\\d{4}[\\/-]\\d{1,2}[\\/-]\\d{1,2}/g, ' ')
        .replace(/\\d{1,2}\\s*[:：]\\s*\\d{2}(?:\\s*[:：]\\s*\\d{2})?/g, ' ')
        .replace(/\\d{4}\\s*年\\s*\\d{1,2}\\s*月/g, ' ');
      const isBadDocUrl = (href) => {
        const u = (href || '').toLowerCase();
        return /developers\\.weixin\\.qq\\.com|miniprogram\\/dev|doc\\.weixin|support\\.weixin|platform\\/post\\/(list|create)/.test(u);
      };
      const isContent = (href) => {
        const u = (href || '').toLowerCase();
        if (!u.startsWith('http') || isBadDocUrl(u)) return false;
        if (/upload|publish\\/publish|post\\/create|login|passport/.test(u)) return false;
        return /douyin\\.com\\/video\\/|v\\.douyin\\.com\\/|xiaohongshu\\.com\\/(explore|discovery\\/item)\\/|xhslink\\.com\\/|weixin\\.qq\\.com\\/sph\\/?|channels\\.weixin\\.qq\\.com\\/(web|mobile)\\//.test(u);
      };
      const keys = (titleKeys || []).filter(Boolean);
      const hit = (text) => {
        if (!keys.length) return true;
        const t = norm(text);
        const compact = t.replace(/[\\s\\-_|｜·•，。！？、：:；;（）()【】\\[\\]《》<>\"'“”‘’]+/g, '');
        return keys.some(k => t.includes(k) || compact.includes(String(k).replace(/\\s+/g, '')));
      };
      const parseEngagement = (rawText) => {
        const t0 = norm(rawText);
        const t = stripDateNoise(t0);
        let likes = 0, comments = 0, views = 0;
        const labeledLike = t.match(/(?:点赞|赞)\\s*[:：]?\\s*([\\d.]+\\s*[万wW千kK]?)/);
        const labeledComment = t.match(/(?:评论|回复)\\s*[:：]?\\s*([\\d.]+\\s*[万wW千kK]?)/);
        const labeledView = t.match(/(?:播放|观看|浏览|阅读)\\s*[:：]?\\s*([\\d.]+\\s*[万wW千kK]?)/);
        if (labeledLike) likes = parseNum(labeledLike[1]);
        if (labeledComment) comments = parseNum(labeledComment[1]);
        if (labeledView) views = parseNum(labeledView[1]);
        const nums = (t.match(/\\d+(?:\\.\\d+)?\\s*[万wW千kK]?/g) || [])
          .map(parseNum)
          .filter(n => n >= 0 && n < 100000000 && !(n >= 1900 && n <= 2100));
        // 视频号管理页常见顺序：播放 喜欢 评论 分享 点赞
        if (platform === 'shipinhao' && (!labeledLike || !labeledComment)) {
          if (nums.length >= 5) {
            views = views || nums[0];
            comments = labeledComment ? comments : nums[2];
            likes = labeledLike ? likes : nums[4];
          } else if (nums.length >= 3) {
            comments = labeledComment ? comments : nums[Math.min(2, nums.length - 1)];
            likes = labeledLike ? likes : nums[nums.length - 1];
          } else if (nums.length === 2) {
            likes = labeledLike ? likes : nums[0];
            comments = labeledComment ? comments : nums[1];
          } else if (nums.length === 1 && !labeledLike) {
            likes = nums[0];
          }
        } else if (!labeledLike && !labeledComment) {
          if (nums.length >= 2) { likes = nums[0]; comments = nums[1]; }
          else if (nums.length === 1) { likes = nums[0]; }
        }
        if (likes >= 1900 && likes <= 2100 && comments >= 1 && comments <= 31) {
          likes = 0; comments = 0;
        }
        return { likes, comments, views };
      };
      const cards = [];
      const seen = new Set();
      const nodes = Array.from(document.querySelectorAll(
        '[class*="post"], [class*="feed"], [class*="item"], [class*="card"], [class*="row"], [class*="list"] > *, li, tr, [role="listitem"], a'
      ));
      for (const el of nodes) {
        const t = norm(el.innerText || el.textContent || '');
        if (!t || t.length < 4 || t.length > 800) continue;
        if (!hit(t)) continue;
        const looksPost = /\\d{4}\\s*年|点赞|评论|播放|分享|置顶|可见权限/.test(t)
          || (platform === 'shipinhao' && /#/.test(t));
        if (keys.length && !looksPost && t.length < 20) continue;
        let href = '';
        const feedId = el.getAttribute && (
          el.getAttribute('data-feed-id') || el.getAttribute('data-feedid') || el.getAttribute('data-id') || ''
        );
        if (el.tagName === 'A' && el.href && isContent(el.href)) href = el.href;
        if (!href) {
          const anchors = el.querySelectorAll ? Array.from(el.querySelectorAll('a[href]')) : [];
          for (const a of anchors) {
            if (isContent(a.href)) { href = a.href; break; }
          }
        }
        if (href && isBadDocUrl(href)) href = '';
        const eng = parseEngagement(t);
        const key = (href || feedId || '') + '|' + t.slice(0, 48);
        if (seen.has(key)) continue;
        seen.add(key);
        cards.push({
          title: t.slice(0, 120),
          url: href || '',
          feedId: feedId || '',
          likes: eng.likes,
          comments: eng.comments,
          views: eng.views,
          score: (href ? 12 : 0) + (eng.likes + eng.comments > 0 ? 8 : 0) + (looksPost ? 6 : 0),
        });
        if (cards.length >= 24) break;
      }
      cards.sort((a, b) => (b.score || 0) - (a.score || 0));
      return cards;
    }
    """

    payload = {'keys': title_keys, 'platform': platform or ''}
    items = []
    samples = []
    for root in _scrape_roots(page):
        try:
            found = root.evaluate(scrape_js, payload) or []
            items.extend(found)
        except Exception:
            continue
        if not samples:
            try:
                raw = root.evaluate(scrape_js, {'keys': [], 'platform': platform or ''}) or []
                samples = [
                    s for s in raw
                    if 6 <= len((s.get('title') or '')) <= 120
                    and not any(x in (s.get('title') or '') for x in ('作品管理', '发表视频', '数据中心', '设置', '首页'))
                ][:5] or raw[:3]
            except Exception:
                pass

    uniq, seen = [], set()
    for it in items:
        k = (it.get('url') or '') + '|' + (it.get('feedId') or '') + '|' + (it.get('title') or '')[:40]
        if k in seen:
            continue
        seen.add(k)
        uniq.append(it)
    items = uniq

    if not items:
        url = _detect_url_from_page(page)
        if url and _is_content_url(url):
            return {'ok': True, 'publish_url': url, 'likes': 0, 'comments': 0, 'matched': False}
        hint = ''
        if samples:
            titles = '；'.join((s.get('title') or '')[:20] for s in samples[:3] if s.get('title'))
            if titles:
                hint = f'。页上可见：{titles}'
        elif title_keys:
            hint = f'（匹配关键字：{title_keys[0][:16]}）'
        return {'ok': False, 'error': f'未在作品管理页匹配到该标题，请确认已发布成功{hint}'}

    best = items[0]
    for it in items:
        if it.get('url') and _is_content_url(it.get('url')):
            best = it
            break

    likes, comments = _sanitize_engagement(best.get('likes'), best.get('comments'))
    publish_url = best.get('url') or ''
    if publish_url and not _is_content_url(publish_url):
        publish_url = ''

    if platform == 'shipinhao' and not publish_url:
        share = _shipinhao_try_share_url(page, title_keys)
        if share:
            publish_url = share

    return {
        'ok': True,
        'publish_url': publish_url,
        'likes': likes,
        'comments': comments,
        'matched': True,
        'matched_title': best.get('title') or '',
    }


def _shipinhao_try_share_url(page, title_keys):
    """点击作品「分享」，尽量拿到视频号公开链。"""
    keys = [k for k in (title_keys or []) if k]
    click_js = """
    (keys) => {
      const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim();
      const hit = (t) => !keys.length || keys.some(k => t.includes(k));
      const nodes = Array.from(document.querySelectorAll('button, a, span, div'));
      for (const el of nodes) {
        if (norm(el.innerText || '') !== '分享') continue;
        let p = el;
        for (let i = 0; i < 8 && p; i++) {
          const pt = norm(p.innerText || '');
          if (hit(pt) && pt.length > 10) { el.click(); return true; }
          p = p.parentElement;
        }
      }
      const any = nodes.find(el => norm(el.innerText || '') === '分享');
      if (any) { any.click(); return true; }
      return false;
    }
    """
    clicked = False
    for root in _scrape_roots(page):
        try:
            if root.evaluate(click_js, keys):
                clicked = True
                break
        except Exception:
            continue
    if not clicked:
        return ''

    page.wait_for_timeout(1200)
    read_js = """
    () => {
      const bad = /developers\\.weixin\\.qq\\.com|miniprogram\\/dev|platform\\/post\\//;
      for (const el of Array.from(document.querySelectorAll('input, textarea'))) {
        const v = (el.value || el.getAttribute('value') || '').trim();
        if (/^https?:\\/\\//.test(v) && /weixin\\.qq\\.com|channels\\.weixin/.test(v) && !bad.test(v)) return v;
      }
      for (const a of Array.from(document.querySelectorAll('a[href]'))) {
        const u = a.href || '';
        if (/weixin\\.qq\\.com\\/sph|channels\\.weixin\\.qq\\.com\\/(web|mobile)/.test(u) && !bad.test(u)) return u;
      }
      const text = document.body ? (document.body.innerText || '') : '';
      const m = text.match(/https?:\\/\\/[^\\s\"']*(?:weixin\\.qq\\.com\\/sph|channels\\.weixin\\.qq\\.com\\/(?:web|mobile))[^\\s\"']*/);
      return m ? m[0] : '';
    }
    """
    for root in _scrape_roots(page):
        try:
            found = root.evaluate(read_js)
            if found and _is_content_url(found):
                return found.rstrip('.,);]')
        except Exception:
            continue
        try:
            root.evaluate("""
            () => {
              const nodes = Array.from(document.querySelectorAll('button, a, span, div'));
              const btn = nodes.find(el => /复制链接|复制/.test((el.innerText || '').trim()));
              if (btn) btn.click();
            }
            """)
            page.wait_for_timeout(400)
        except Exception:
            pass
    try:
        page.keyboard.press('Escape')
    except Exception:
        pass
    return ''



def request_session_sync(session_id, title=''):
    """向已打开会话请求同步互动；成功返回结果 dict，超时/失败返回 error。"""
    with _SESSIONS_LOCK:
        session = _SESSIONS.get(session_id)
    if not session or session.get('status') in ('closed', 'error'):
        return None
    done = threading.Event()
    session['sync_done'] = done
    session['sync_result'] = None
    session['sync_request'] = {'title': title}
    if not done.wait(timeout=45):
        return {'ok': False, 'error': '同步超时，请稍后重试'}
    return session.get('sync_result') or {'ok': False, 'error': '无同步结果'}


def sync_publish_engagement(task):
    """
    同步作品链接与点赞/评论。
    优先复用同平台已打开的发布浏览器；否则临时启动登录态浏览器打开作品管理页。
    规则：likes>0 或 comments>0 → 建议标记 got_consult。
    """
    platform = (task.get('platform') or '').strip()
    title = task.get('title') or ''
    if not platform:
        return {'ok': False, 'error': '任务未设置平台'}
    if not check_playwright():
        return {'ok': False, 'error': 'Playwright 未安装'}

    # 1) 复用会话
    with _SESSIONS_LOCK:
        live = [
            s for s in _SESSIONS.values()
            if s.get('platform') == platform and s.get('status') not in ('closed', 'error', 'starting')
        ]
    if live:
        sid = live[0]['id']
        result = request_session_sync(sid, title=title)
        if result is not None:
            if result.get('ok') and not result.get('publish_url') and live[0].get('detected_url'):
                result['publish_url'] = live[0]['detected_url']
            return result

    # 2) 临时浏览器
    meta = _platform_meta(platform)
    label = meta['label']
    profile = _profile_dir(platform)
    _stop_platform_sessions(platform)
    time.sleep(1.2)

    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as p:
            context = _launch_persistent(p, profile)
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.set_default_timeout(20000)
                result = _scrape_manage_page(page, platform, title)
                # 视频号未匹配时多等一会再刮一次（列表异步渲染，不再重复 goto）
                if not result.get('ok') and platform == 'shipinhao':
                    try:
                        page.wait_for_timeout(3500)
                        try:
                            page.mouse.wheel(0, 1600)
                            page.wait_for_timeout(800)
                        except Exception:
                            pass
                        result2 = _scrape_manage_page(page, platform, title, navigate=False)
                        if result2.get('ok'):
                            result = result2
                        elif result2.get('error') and '页上可见' in (result2.get('error') or ''):
                            result = result2
                    except Exception:
                        pass
                return result
            finally:
                try:
                    context.close()
                except Exception:
                    pass
    except Exception as e:
        return {'ok': False, 'error': _launch_error_hint(e, profile, label)}


def apply_engagement_to_consult(likes, comments):
    """点赞或评论/回复视为「有咨询」（互动代理，非真实私信）。"""
    return int(likes or 0) > 0 or int(comments or 0) > 0


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


def _looks_like_login(page, platform=''):
    """URL 跳到登录页，或明确的登录控件出现，才算未登录。

    不要用宽泛的 [class*=qrcode]：创作页里也常有二维码相关 class，会误判小红书已登录。
    """
    try:
        url = (page.url or '').lower()
    except Exception:
        return False

    login_url_keys = (
        '/login', 'login.', 'signin', 'passport', 'sso.',
        'accounts.xiaohongshu', 'www.xiaohongshu.com/login',
    )
    if any(k in url for k in login_url_keys):
        return True

    for t in ('扫码登录', '手机号登录', '请登录', '登录后继续'):
        try:
            loc = page.get_by_text(t, exact=False).first
            if loc.is_visible(timeout=300):
                return True
        except Exception:
            continue

    for sel in (
        '.login-container',
        '.login-box',
        '.qrcode-login',
        '[class*="login-panel"]',
        '[class*="LoginContainer"]',
        '[class*="login-modal"]',
    ):
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                return True
        except Exception:
            continue
    return False


def _on_publish_page(page, platform):
    try:
        url = (page.url or '').lower()
    except Exception:
        return False
    if platform == 'xiaohongshu':
        return 'creator.xiaohongshu.com' in url and 'login' not in url
    if platform == 'douyin':
        return 'creator.douyin.com' in url and 'login' not in url
    if platform == 'shipinhao':
        return 'channels.weixin.qq.com' in url and 'login' not in url
    return 'login' not in url


def _wait_until_logged_in(page, platform, session, timeout_sec=300):
    """等待用户在浏览器中完成登录。"""
    deadline = time.time() + timeout_sec
    while time.time() < deadline and not session['stop'].is_set():
        try:
            if not _looks_like_login(page, platform):
                return True
        except Exception:
            pass
        remaining = int(max(0, deadline - time.time()))
        session['message'] = (
            f'{session.get("label") or platform} 等待扫码登录中…（约剩 {remaining}s），'
            f'登录成功后将自动继续上传填充'
        )
        try:
            page.wait_for_timeout(2500)
        except Exception:
            time.sleep(2.5)
    try:
        return not _looks_like_login(page, platform)
    except Exception:
        return False


# ---------------- filling helpers ----------------

def _set_video(page, video_path, accept_video_first=True, timeout=15000, search_frames=False):
    """找到 file input 并塞视频（隐藏的 input 也可以）。

    search_frames=True 时还会在 iframe（如视频号 wujie 微前端）里找。
    """
    selectors = ['input[type="file"][accept*="video"]', 'input[type="file"]'] \
        if accept_video_first else ['input[type="file"]']
    deadline = time.time() + timeout / 1000
    while time.time() < deadline:
        roots = [page]
        if search_frames:
            try:
                frames = list(page.frames)
                micro = [f for f in frames if '/micro/' in (f.url or '')]
                others = [f for f in frames if f not in micro and f != page.main_frame]
                roots = micro + others + [page]
            except Exception:
                roots = [page]

        for root in roots:
            for sel in selectors:
                try:
                    els = root.query_selector_all(sel)
                except Exception:
                    continue
                for el in els:
                    try:
                        el.set_input_files(video_path)
                        return True
                    except Exception:
                        continue
        page.wait_for_timeout(1000)
    return False


def _set_video_via_chooser(page, video_path, timeout=20000):
    """点击上传区域触发系统文件选择框，再塞文件（视频号常用）。"""
    click_targets = [
        'text=上传视频',
        'text=点击上传',
        'text=选择文件',
        'div.upload-content',
        'div[class*="upload-content"]',
        'div[class*="upload-btn"]',
        'div[class*="uploader"]',
        'button:has-text("上传")',
    ]
    try:
        with page.expect_file_chooser(timeout=timeout) as fc_info:
            clicked = False
            for frame in page.frames:
                try:
                    n = frame.locator('input[type="file"]').count()
                    if n > 0:
                        frame.evaluate(
                            'document.querySelector("input[type=\\"file\\"]").click()'
                        )
                        clicked = True
                        break
                except Exception:
                    continue
            if not clicked:
                for sel in click_targets:
                    try:
                        loc = page.locator(sel).first
                        if loc.count() > 0 and loc.is_visible():
                            loc.click(timeout=3000)
                            clicked = True
                            break
                    except Exception:
                        pass
                    for frame in page.frames:
                        try:
                            loc = frame.locator(sel).first
                            if loc.count() > 0:
                                loc.click(timeout=3000)
                                clicked = True
                                break
                        except Exception:
                            continue
                    if clicked:
                        break
            if not clicked:
                raise Exception('未找到可点击的上传入口')
        chooser = fc_info.value
        chooser.set_files(video_path)
        return True
    except Exception:
        return False


def _shipinhao_short_title(title):
    """视频号短标题要求约 6～16 字。"""
    t = (title or '').strip() or '精彩短视频分享'
    if len(t) < 6:
        t = (t + '精彩内容分享')[:16]
    return t[:16]


def _fill_in_frames(page, selectors, text, clear=True):
    """主页面 + 各 iframe 里尝试填充。"""
    if not text:
        return True
    roots = []
    try:
        frames = list(page.frames)
        micro = [f for f in frames if '/micro/' in (f.url or '')]
        roots = micro + [f for f in frames if f not in micro]
    except Exception:
        roots = [page]
    for root in roots:
        try:
            if _fill_first(root, selectors, text, clear=clear):
                return True
        except Exception:
            continue
    return False


def _fill_first(page, selectors, text, clear=True):
    """按顺序尝试选择器，支持普通输入框和 contenteditable。

    page 可为 Page 或 Frame（视频号 iframe）。
    """
    if not text:
        return True
    try:
        keyboard = page.keyboard
    except AttributeError:
        keyboard = page.page.keyboard
    for sel in selectors:
        try:
            els = page.query_selector_all(sel)
        except Exception:
            continue
        for el in els:
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
                        keyboard.press('Control+A')
                        keyboard.press('Delete')
                    keyboard.insert_text(text)
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
    """视频号：上传控件常在 wujie iframe（/micro/）内，需跨 frame 查找。"""
    # 等微前端加载
    for _ in range(20):
        try:
            if any('/micro/' in (f.url or '') for f in page.frames):
                break
            if page.query_selector('input[type="file"]'):
                break
        except Exception:
            pass
        page.wait_for_timeout(1000)

    uploaded = _set_video(page, video_path, timeout=25000, search_frames=True)
    if not uploaded:
        uploaded = _set_video_via_chooser(page, video_path, timeout=25000)
    if not uploaded:
        session['warnings'].append(
            '未找到视频号上传控件（可能在 iframe 内未加载完），请在浏览器中手动选择视频'
        )
        return

    # 等待上传完成：出现预览 video / 删除按钮 / 短标题可填
    upload_done = False
    for i in range(90):
        try:
            for root in list(page.frames) + [page]:
                try:
                    if root.query_selector('video'):
                        upload_done = True
                        break
                    if root.query_selector('button:has-text("删除")'):
                        upload_done = True
                        break
                    st = root.query_selector('input[placeholder*="概括视频主要内容"]')
                    if st and not st.is_disabled():
                        upload_done = True
                        break
                except Exception:
                    continue
            if upload_done:
                break
        except Exception:
            pass
        if i in (10, 30, 60):
            session['message'] = f'视频号视频上传中…（已等待约 {i * 2}s）'
        page.wait_for_timeout(2000)

    if not upload_done:
        session['warnings'].append(
            '未检测到上传完成标志，仍尝试填写表单，请人工确认视频是否已选上'
        )

    page.wait_for_timeout(2000)

    tag_suffix = ''
    if tags:
        parts = [t.strip() for t in str(tags).replace('，', ',').split(',') if t.strip()]
        tag_suffix = ' ' + ' '.join(f'#{t}' for t in parts[:5])
    full_desc = f'{(description or "").strip()}{tag_suffix}'.strip()

    short = _shipinhao_short_title(title)
    if not _fill_in_frames(page, [
        'input[placeholder*="概括视频主要内容"]',
        'input[placeholder*="短标题"]',
        'input[placeholder*="标题"]',
    ], short):
        session['warnings'].append('短标题未自动填充（需 6～16 字）')

    if full_desc:
        if not _fill_in_frames(page, [
            'div.input-editor[contenteditable="true"]',
            'div[contenteditable="true"][data-placeholder*="描述"]',
            'div[contenteditable="true"]',
            '.weui-desktop-form__input',
        ], full_desc[:900]):
            session['warnings'].append('描述未自动填充')

    session['message'] = '视频号已尝试上传并填充，请在浏览器中确认后点击「发表」'


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
