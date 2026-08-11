"""Playwright 浏览器路径修正。

Cursor / 部分 CI 会把 PLAYWRIGHT_BROWSERS_PATH 指到 sandbox 临时目录，
里面往往没有真正的 chromium，导致 launch 报 Executable doesn't exist。
"""

from __future__ import annotations

import os
from functools import lru_cache


def _looks_like_sandbox_cache(path: str) -> bool:
    norm = path.replace('\\', '/').lower()
    return 'cursor-sandbox-cache' in norm or '/temp/playwright' in norm


def _chrome_exists_under(root: str) -> bool:
    if not root or not os.path.isdir(root):
        return False
    for dirpath, _dirnames, filenames in os.walk(root):
        lower = {f.lower() for f in filenames}
        if 'chrome.exe' in lower or 'chromium.exe' in lower:
            return True
        if 'chrome' in lower and os.name != 'nt':
            return True
    return False


def ensure_playwright_browsers_path() -> str | None:
    """修正环境变量，返回最终使用的 browsers 目录（可能为 None=Playwright 默认）。"""
    current = os.environ.get('PLAYWRIGHT_BROWSERS_PATH') or ''
    if current and _chrome_exists_under(current) and not _looks_like_sandbox_cache(current):
        return current

    # 沙箱路径或缺文件：优先本机默认目录
    candidates = []
    local = os.environ.get('LOCALAPPDATA') or ''
    home = os.path.expanduser('~')
    if local:
        candidates.append(os.path.join(local, 'ms-playwright'))
    if home:
        candidates.append(os.path.join(home, 'AppData', 'Local', 'ms-playwright'))
        candidates.append(os.path.join(home, '.cache', 'ms-playwright'))

    for cand in candidates:
        if _chrome_exists_under(cand):
            os.environ['PLAYWRIGHT_BROWSERS_PATH'] = cand
            return cand

    # 清掉坏路径，交给 Playwright 默认查找 / 后续 install
    if current:
        os.environ.pop('PLAYWRIGHT_BROWSERS_PATH', None)
    return None


@lru_cache(maxsize=1)
def playwright_chromium_ready() -> tuple[bool, str]:
    """返回 (是否可用, 说明)。"""
    ensure_playwright_browsers_path()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False, 'Playwright 未安装，请执行: uv sync 后 python -m playwright install chromium'

    pw = None
    try:
        pw = sync_playwright().start()
        exe = pw.chromium.executable_path
        if not exe or not os.path.isfile(exe):
            return False, (
                'Chromium 未安装或不完整。请在仓库根目录执行：'
                '.venv\\Scripts\\python.exe -m playwright install chromium'
                '（并确认未使用 Cursor 沙箱的 PLAYWRIGHT_BROWSERS_PATH）'
            )
        return True, exe
    except Exception as e:
        text = str(e)
        if "Executable doesn't exist" in text:
            return False, (
                'Chromium 可执行文件不存在。请执行：'
                '.venv\\Scripts\\python.exe -m playwright install chromium'
            )
        return False, f'Playwright 检查失败: {text.splitlines()[0]}'
    finally:
        if pw is not None:
            try:
                pw.stop()
            except Exception:
                pass


def clear_playwright_ready_cache():
    playwright_chromium_ready.cache_clear()
