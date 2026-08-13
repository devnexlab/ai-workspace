# -*- coding: utf-8 -*-
"""Try shipinhao post_list with different request bodies."""
import json
import os
import time
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from modules.playwright_env import ensure_playwright_browsers_path
from modules.publish.publisher import (
    MANAGE_URLS,
    _kill_stale_profile_browsers,
    _clear_profile_locks,
    _launch_persistent,
    _parse_shipinhao_post_list_payload,
    _profile_dir,
    _stop_platform_sessions,
)
from playwright.sync_api import sync_playwright

ensure_playwright_browsers_path()
profile = _profile_dir("shipinhao")
out = os.path.join(os.path.dirname(__file__), "_tmp_sph_api.json")

_stop_platform_sessions("shipinhao")
_kill_stale_profile_browsers(profile)
_clear_profile_locks(profile)
time.sleep(2)

PROBE_JS = r"""
async () => {
  const bodies = [
    { currentPage: 1, pageSize: 20, timestamp: Date.now() },
    { currentPage: 1, pageSize: 20, timestamp: Date.now(), userpageType: 11 },
    { currentPage: 1, pageSize: 20, timestamp: Date.now(), userpageType: 0 },
    { currentPage: 1, pageSize: 20, timestamp: Date.now(), userpageType: 1 },
    { pageNum: 1, pageSize: 20, timestamp: Date.now() },
    { currentPage: 1, pageSize: 50, timestamp: Date.now() },
  ];
  const paths = [
    '/cgi-bin/mmfinderassistant-bin/post/post_list',
    'https://channels.weixin.qq.com/cgi-bin/mmfinderassistant-bin/post/post_list',
    '/cgi-bin/mmfinderassistant-bin/auth/auth_data',
    'https://channels.weixin.qq.com/cgi-bin/mmfinderassistant-bin/auth/auth_data',
  ];
  const results = [];
  for (const path of paths) {
    for (const body of bodies) {
      // auth_data only needs timestamp
      const payload = path.includes('auth_data') ? { timestamp: Date.now() } : body;
      try {
        const resp = await fetch(path, {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/plain, */*',
          },
          body: JSON.stringify(payload),
        });
        const text = await resp.text();
        let data = null;
        try { data = JSON.parse(text); } catch (e) {}
        results.push({
          path,
          body: payload,
          status: resp.status,
          text_head: text.slice(0, 500),
          errCode: data && data.errCode,
          errMsg: data && data.errMsg,
          data_keys: data && data.data && typeof data.data === 'object' ? Object.keys(data.data).slice(0, 30) : null,
          list_len: data && data.data && Array.isArray(data.data.list) ? data.data.list.length : null,
          totalCount: data && data.data && (data.data.totalCount ?? data.data.feedsCount ?? null),
          finder: data && data.data && data.data.finderUser ? {
            nickname: data.data.finderUser.nickname,
            feedsCount: data.data.finderUser.feedsCount,
            uniqId: data.data.finderUser.uniqId,
          } : null,
        });
      } catch (e) {
        results.push({ path, body: payload, error: String(e && e.message || e) });
      }
      if (path.includes('auth_data')) break;
    }
  }
  return results;
}
"""

captured_native = []

def on_req(req):
    url = (req.url or "").lower()
    if "post_list" in url or "auth_data" in url:
        captured_native.append({
            "type": "req",
            "url": req.url[:250],
            "method": req.method,
            "body": (req.post_data or "")[:600],
        })

def on_resp(resp):
    url = (resp.url or "").lower()
    if "post_list" not in url and "auth_data" not in url:
        return
    entry = {"type": "resp", "url": resp.url[:250], "status": resp.status}
    try:
        data = resp.json()
        entry["errCode"] = data.get("errCode")
        if isinstance(data.get("data"), dict):
            d = data["data"]
            entry["data_keys"] = list(d.keys())[:40]
            if isinstance(d.get("list"), list):
                entry["list_len"] = len(d["list"])
            fu = d.get("finderUser")
            if isinstance(fu, dict):
                entry["finder"] = {
                    "nickname": fu.get("nickname"),
                    "feedsCount": fu.get("feedsCount"),
                }
        entry["json_head"] = json.dumps(data, ensure_ascii=False)[:800]
    except Exception as e:
        entry["err"] = str(e)[:160]
    captured_native.append(entry)

with sync_playwright() as p:
    ctx = _launch_persistent(p, profile)
    try:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.on("request", on_req)
        page.on("response", on_resp)
        page.goto(MANAGE_URLS["shipinhao"], wait_until="domcontentloaded", timeout=60000)
        # poll instead of long wait_for_timeout (survives better)
        for i in range(20):
            if page.is_closed():
                raise RuntimeError("page closed early")
            time.sleep(0.5)
            if any("/micro/" in (f.url or "") for f in page.frames):
                time.sleep(2)
                break

        micro = None
        for f in page.frames:
            if "/micro/" in (f.url or ""):
                micro = f
                break
        root = micro or page
        probe = root.evaluate(PROBE_JS)
        # also try form-urlencoded style via page
        form_probe = root.evaluate(
            r"""
            async () => {
              const ts = Date.now();
              const body = new URLSearchParams({
                currentPage: '1', pageSize: '20', timestamp: String(ts)
              });
              const resp = await fetch('/cgi-bin/mmfinderassistant-bin/post/post_list', {
                method: 'POST', credentials: 'include',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: body.toString(),
              });
              const text = await resp.text();
              let data=null; try{data=JSON.parse(text)}catch(e){}
              return {
                status: resp.status,
                list_len: data && data.data && Array.isArray(data.data.list) ? data.data.list.length : null,
                text_head: text.slice(0,400),
                errCode: data && data.errCode,
              };
            }
            """
        )
        result = {
            "page_url": page.url,
            "frames": [f.url for f in page.frames],
            "native": captured_native,
            "probe": probe,
            "form_probe": form_probe,
            "micro_text": (micro.evaluate("document.body?document.body.innerText:''") if micro else "")[:500],
        }
        with open(out, "w", encoding="utf-8") as fp:
            json.dump(result, fp, ensure_ascii=False, indent=2)
        print("wrote", out)
        print("micro:", (result.get("micro_text") or "")[:200].replace("\n", " | "))
        print("form_probe", form_probe)
        for row in probe:
            if row.get("finder") or row.get("list_len") not in (None, 0) or "auth_data" in (row.get("path") or ""):
                print("HIT", json.dumps(row, ensure_ascii=False)[:300])
        # print summary of all list_len
        for row in probe:
            print(
                "probe",
                (row.get("path") or "")[-40:],
                "status", row.get("status"),
                "list", row.get("list_len"),
                "total", row.get("totalCount"),
                "err", row.get("errCode"),
                "bodyKeys", list((row.get("body") or {}).keys()),
            )
    finally:
        try:
            ctx.close()
        except Exception:
            pass
