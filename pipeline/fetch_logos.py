#!/usr/bin/env python3
"""Fetch every franchise/team-season logo once at build time and inline as data
URIs (96px PNG). Dead hosts fall back to initials chips in the UI — the site
makes zero runtime logo requests."""
import base64
import io
import json
from pathlib import Path

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
MARTS = ROOT / "data" / "marts"
OUT = MARTS / "logos.json"

sav = json.load(open(MARTS / "savant_data.json"))
urls = set()
for f in sav["franchises"]:
    if f.get("logo_url"):
        urls.add(f["logo_url"])
for sd in sav["seasons"].values():
    for t in sd["teams"]:
        if t.get("logo"):
            urls.add(t["logo"])

print("distinct logo urls:", len(urls))
logos = {}
dead = []
for u in sorted(urls):
    try:
        r = requests.get(u, timeout=12, headers={"User-Agent": "Mozilla/5.0 (AFFL Savant build)"})
        if r.status_code != 200 or not r.content:
            dead.append((u, r.status_code))
            continue
        img = Image.open(io.BytesIO(r.content)).convert("RGBA")
        img.thumbnail((96, 96), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, "PNG", optimize=True)
        b = buf.getvalue()
        if len(b) > 60000:
            img.thumbnail((64, 64), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, "PNG", optimize=True)
            b = buf.getvalue()
        logos[u] = "data:image/png;base64," + base64.b64encode(b).decode()
    except Exception as e:
        dead.append((u, type(e).__name__))

json.dump(logos, open(OUT, "w"), separators=(",", ":"))
total = sum(len(v) for v in logos.values())
print("inlined %d logos (%.0f KB), dead/unreachable: %d" % (len(logos), total / 1024, len(dead)))
for u, why in dead:
    print("  DEAD %-8s %s" % (why, u[:110]))
