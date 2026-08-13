# -*- coding: utf-8 -*-
"""Probe shipinhao nav links + network APIs for content list."""
import json
import os
import re
import time
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from modules.playwright_env import ensure_playwright_browsers_path
from modules.publish.publisher import (
    MANAGE_URLS,
    _launch_persistent,
    _profile_dir,
    _stop_platform_sessions,
)
from playwright.sync_api import sync_playwright

ensure_playwright_browsers_path()
profile = _profile_dir("shipinhao")
out = os.path.join(os.path.dirname(__file__), "_tmp_sph_net.json")
_stop_platform_sessions("shipinhao")
time.sleep(1)

apis = []

def on_resp(resp):
    try:
        url = resp.url or ""
        low = url.lower()
        if resp.status != 200:
            return
        if not any(k in low for k in (
            "post", "list", "feed", "content", "finder", "cgi-bin", "mmfinder", "getpost", "work"
        )):
            return
        if any(x in low for x in (".js", ".css", ".png", ".jpg", ".svg", ".woff", "favicon")):
            return
        entry = {"url": url[:300], "status": resp.status}
        try:
            ct = (resp.headers or {}).get("content-type", "")
            entry["ct"] = ct[:80]
            if "json" in ct or "javascript" in ct or low.endswith("json"):
                data = resp.json()
                text = json.dumps(data, ensure_ascii=False)
                entry["json_head"] = text[:1200]
                entry["keys"] = list(data.keys())[:30] if isinstance(data, dict) else type(data).__name__
                # dig for list-like
                if isinstance(data, dict):
                    for k in ("data", "list", "object", "postList", "posts", "listInfo"):
                        v = data.get(k)
                        if isinstance(v, dict):
                            entry["data_keys"] = list(v.keys())[:40]
                        elif isinstance(v, list):
                            entry["list_len"] = len(v)
        except Exception as e:
            entry["json_err"] = str(e)[:120]
        apis.append(entry)
    except Exception:
        pass

with sync_playwright() as p:
    ctx = _launch_persistent(p, profile)
    try:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.on("response", on_resp)
        page.goto(MANAGE_URLS["shipinhao"], wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)

        # collect sidebar/nav links from main + micro
        nav = page.evaluate(
            """() => {
              const out = [];
              for (const a of Array.from(document.querySelectorAll('a[href]'))) {
                const href = a.href || '';
                const t = ((a.innerText||a.textContent||'')+'').trim().replace(/\\s+/g,' ');
                if (!/channels\\.weixin\\.qq\\.com/.test(href)) continue;
                if (!t && !/post|list|feed|content|dynamic|image|picture|text/.test(href)) continue;
                out.push({t: t.slice(0,40), href: href.slice(0,200)});
              }
              return out.slice(0,80);
            }"""
        )
        # also from micro frames
        micro_nav = []
        for f in page.frames:
            if "/micro/" not in (f.url or ""):
                continue
            try:
                micro_nav = f.evaluate(
                    """() => Array.from(document.querySelectorAll('a[href], [role=tab], .tab, .weui-desktop-tab__nav'))
                      .map(el => ({
                        t: ((el.innerText||el.textContent||'')+'').trim().replace(/\\s+/g,' ').slice(0,40),
                        href: (el.href||el.getAttribute('href')||'').slice(0,200),
                        cls: String(el.className||'').slice(0,80)
                      })).filter(x => x.t || x.href).slice(0,100)"""
                )
            except Exception as e:
                micro_nav = [{"err": str(e)}]

        # Click 图文 in main shell if present
        clicked = page.evaluate(
            """() => {
              const els = Array.from(document.querySelectorAll('a,div,span,li,button'));
              for (const el of els) {
                const t = ((el.innerText||el.textContent||'')+'').trim();
                if (t === '图文' || t === '动态') {
                  try { el.click(); return t; } catch(e) { return 'err:'+t; }
                }
              }
              return '';
            }"""
        )
        page.wait_for_timeout(4000)

        after_url = page.url
        after_frames = [f.url for f in page.frames]
        after_text = ""
        for f in page.frames:
            if "/micro/" in (f.url or ""):
                try:
                    after_text = (f.evaluate("document.body ? document.body.innerText : ''") or "")[:1500]
                except Exception:
                    pass

        # Try known alternate URLs
        alt_urls = [
            "https://channels.weixin.qq.com/platform/post/list?tab=image",
            "https://channels.weixin.qq.com/platform/post/list?type=2",
            "https://channels.weixin.qq.com/platform/post/images/list",
            "https://channels.weixin.qq.com/platform/post/feedList",
            "https://channels.weixin.qq.com/platform/content/manage",
            "https://channels.weixin.qq.com/micro/content/post/list",
        ]
        alt_results = []
        for u in alt_urls:
            try:
                page.goto(u, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2500)
                txt = ""
                for f in page.frames:
                    try:
                        t = f.evaluate("document.body ? document.body.innerText : ''") or ""
                        if len(t) > len(txt):
                            txt = t
                    except Exception:
                        pass
                alt_results.append({
                    "url": u,
                    "final": page.url,
                    "text_head": txt[:400].replace("\n", " | "),
                    "has_count": bool(re.search(r"(视频|图文|动态|作品)\\s*[（(]\\s*\\d+", txt)),
                })
            except Exception as e:
                alt_results.append({"url": u, "err": str(e)[:160]})

        data = {
            "nav": nav,
            "micro_nav": micro_nav,
            "clicked": clicked,
            "after_url": after_url,
            "after_frames": after_frames,
            "after_text": after_text,
            "alt_results": alt_results,
            "apis": apis[-80:],
        }
        with open(out, "w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2)
        print("wrote", out)
        print("clicked", clicked)
        print("apis", len(apis))
        for a in apis[-15:]:
            print("API", a.get("url", "")[:120], "list_len", a.get("list_len"), "keys", a.get("keys"))
    finally:
        ctx.close()
