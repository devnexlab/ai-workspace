# -*- coding: utf-8 -*-
"""Diagnose why shipinhao post/list scrape returns empty-state junk."""
import json
import os
import time
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from modules.playwright_env import ensure_playwright_browsers_path
from modules.publish.publisher import (
    MANAGE_URLS,
    _collect_manage_cards,
    _launch_persistent,
    _profile_dir,
    _scrape_roots,
    _stop_platform_sessions,
)
from playwright.sync_api import sync_playwright

ensure_playwright_browsers_path()
platform = "shipinhao"
profile = _profile_dir(platform)
out = os.path.join(os.path.dirname(__file__), "_tmp_sph_dom.json")
_stop_platform_sessions(platform)
time.sleep(1.0)

SCROLL_JS = """
() => {
  const score = (el) => {
    try {
      const st = window.getComputedStyle(el);
      const oy = st.overflowY || '';
      if (!(oy === 'auto' || oy === 'scroll' || oy === 'overlay')) return 0;
      return Math.max(0, (el.scrollHeight||0)-(el.clientHeight||0));
    } catch (e) { return 0; }
  };
  const nodes = Array.from(document.querySelectorAll('div,section,main,ul,tbody'));
  nodes.sort((a,b)=>score(b)-score(a));
  let moved = 0;
  for (const el of nodes.slice(0,4)) {
    if (score(el) <= 0) continue;
    const before = el.scrollTop;
    el.scrollTop = Math.min((el.scrollTop||0) + Math.max(Math.floor((el.clientHeight||400)*0.85), 500), el.scrollHeight||0);
    if ((el.scrollTop||0) > before + 8) moved += 1;
  }
  window.scrollBy(0, 800);
  return moved;
}
"""

with sync_playwright() as p:
    ctx = _launch_persistent(p, profile)
    try:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(MANAGE_URLS[platform], wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(6000)
        for _ in range(25):
            if any("/micro/" in (f.url or "") for f in page.frames):
                page.wait_for_timeout(2000)
                break
            page.wait_for_timeout(400)

        data = {
            "page_url": page.url,
            "frames": [{"url": f.url, "name": f.name} for f in page.frames],
        }

        for f in page.frames:
            if "/micro/" not in (f.url or ""):
                continue
            info = f.evaluate(
                """() => {
                  const text = (document.body && document.body.innerText) || '';
                  const html = (document.body && document.body.innerHTML) || '';
                  const frames = Array.from(document.querySelectorAll('iframe')).map(i => ({
                    src: i.src || '', id: i.id || '', cls: String(i.className||'').slice(0,80)
                  }));
                  const tabs = Array.from(document.querySelectorAll('a,button,div,span,li'))
                    .map(el => ((el.innerText||el.textContent||'')+'').trim())
                    .filter(t => t && t.length <= 24)
                    .filter(t => /视频|图文|全部|已发表|发表|草稿|动态|内容|作品/.test(t))
                    .slice(0, 60);
                  const imgs = Array.from(document.querySelectorAll('img')).slice(0, 30).map(i => ({
                    src: (i.currentSrc||i.src||'').slice(0,180),
                    w: Math.round((i.getBoundingClientRect()||{}).width||0),
                    h: Math.round((i.getBoundingClientRect()||{}).height||0),
                    alt: (i.alt||'').slice(0,40)
                  }));
                  const candidates = Array.from(document.querySelectorAll('div,ul,section,table,tbody,tr'))
                    .map(el => {
                      const t = ((el.innerText||'')+'').trim();
                      const cls = String(el.className||'');
                      if (t.length < 20 || t.length > 5000) return null;
                      if (!/(list|post|feed|card|row|table|content|wrap|item|video)/i.test(cls) && t.length < 60) return null;
                      return { cls: cls.slice(0,120), tag: el.tagName, len: t.length, sample: t.slice(0,220).replace(/\\s+/g,' ') };
                    }).filter(Boolean).slice(0, 40);
                  // network-ish markers in DOM
                  const hasDate = /20\\d{2}[\\/-]\\d{1,2}/.test(text);
                  const hasPlay = /播放|点赞|评论|曝光/.test(text);
                  const emptyHints = (text.match(/还没有|暂无|去发布|请输入/g) || []).slice(0, 10);
                  return {
                    text_head: text.slice(0, 2000),
                    text_len: text.length,
                    html_len: html.length,
                    html_head: html.slice(0, 3000),
                    iframes: frames,
                    tabs,
                    imgs,
                    candidates,
                    hasDate,
                    hasPlay,
                    emptyHints,
                  };
                }"""
            )
            data["micro"] = info

            # Try switching tabs that might reveal content
            clicks = f.evaluate(
                """() => {
                  const want = ['全部', '图文', '视频', '已发表', '发表'];
                  const hits = [];
                  const els = Array.from(document.querySelectorAll('a,button,div,span,li'));
                  for (const w of want) {
                    for (const el of els) {
                      const t = ((el.innerText||el.textContent||'')+'').trim();
                      if (t === w || t.startsWith(w + ' ')) {
                        hits.push({want:w, text:t.slice(0,20)});
                        try { el.click(); } catch(e) {}
                        break;
                      }
                    }
                  }
                  return hits;
                }"""
            )
            data["clicked"] = clicks
            page.wait_for_timeout(3000)
            after = f.evaluate(
                """() => {
                  const text = (document.body && document.body.innerText) || '';
                  return {
                    text_head: text.slice(0, 2000),
                    text_len: text.length,
                    imgs: document.querySelectorAll('img').length,
                    trs: document.querySelectorAll('tr').length,
                    hasDate: /20\\d{2}[\\/-]\\d{1,2}/.test(text),
                    hasPlay: /播放|点赞|评论/.test(text),
                  };
                }"""
            )
            data["after_click"] = after

        for i in range(6):
            for root in _scrape_roots(page):
                try:
                    root.evaluate(SCROLL_JS)
                except Exception:
                    pass
            page.wait_for_timeout(700)
            batch = _collect_manage_cards(page, platform, max_items=150)
            data.setdefault("rounds", []).append(
                {"i": i, "n": len(batch), "titles": [x.get("title") for x in batch[:8]]}
            )

        data["final_items"] = _collect_manage_cards(page, platform, max_items=150)

        with open(out, "w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2)
        print("wrote", out)
        print("final_n", len(data["final_items"]))
        for it in data["final_items"][:15]:
            print("-", it.get("title"), "|plays", it.get("plays"))
    finally:
        try:
            ctx.close()
        except Exception:
            pass
