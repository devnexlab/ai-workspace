# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from modules.playwright_env import ensure_playwright_browsers_path
ensure_playwright_browsers_path()
from database import get_db
conn = get_db()
c = conn.execute("SELECT COUNT(*) AS c FROM publish_task WHERE platform='shipinhao'").fetchone()["c"]
print("shipinhao_count", c)
rows = conn.execute(
    "SELECT id, title, source, plays, likes, comments, published_at "
    "FROM publish_task WHERE platform='shipinhao' ORDER BY id DESC LIMIT 40"
).fetchall()
for r in rows:
    d = dict(r)
    print(d["id"], (d.get("title") or "")[:50], "src", d.get("source"), "plays", d.get("plays"))
