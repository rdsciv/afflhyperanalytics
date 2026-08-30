#!/usr/bin/env python3
"""Fast, database-free contracts for dashboard routing, scopes, and Pages output."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OK, BAD = [], []


def check(condition, message):
    (OK if condition else BAD).append(message)


savant = json.loads((ROOT / "docs/data/savant.json").read_text())
explore_a = json.loads((ROOT / "docs/data/explore_a.json").read_text())
explore_b = json.loads((ROOT / "docs/data/explore_b.json").read_text())
explore_c = json.loads((ROOT / "docs/data/explore_c.json").read_text())
gamelogs = json.loads((ROOT / "docs/data/gamelogs.json").read_text())
rows = explore_a["rows"] + explore_b["rows"] + explore_c["rows"]
js = (ROOT / "site/app.js").read_text()
css = (ROOT / "site/style.css").read_text()
shell = (ROOT / "docs/index.html").read_text()
build = (ROOT / "site/build_site.py").read_text()
report = json.loads((ROOT / "data/reports/marts_report.json").read_text())
explore_full = dict(explore_a, rows=rows)
explore_bytes = len(json.dumps(explore_full, separators=(",", ":"), ensure_ascii=False).encode())

versions = {savant["meta"]["version"], explore_a["meta"]["version"], gamelogs["meta"]["version"]}
check(len(versions) == 1, "Savant, Explore, and gamelogs publish one dataset version")
check(report["savant_bytes"] == (ROOT / "docs/data/savant.json").stat().st_size and report["explore_bytes"] == explore_bytes and report["gamelogs_bytes"] == (ROOT / "docs/data/gamelogs.json").stat().st_size, "Mart size report matches published payloads")
check(len(explore_a["seasonRows"]) == report["season_rows"] == 7495, "NFL season board carries all 7,495 player-seasons")
check(len(gamelogs["rows"]) == report["gamelog_rows"] and len(gamelogs["custRows"]) == report["gamelog_cust_extra_rows"], "Lazy gamelogs mart row counts match the build report")
check(len(rows) == explore_a["meta"]["custodyRows"] == 31250, "Explore shards reconstruct all 31,250 custody rows")
season_i = explore_a["cols"].index("s")
check(all(r[season_i] <= 2025 for r in rows), "2026 pre-draft rows stay out of historical Explore data")
check(not savant["seasons"]["2026"]["complete"], "2026 remains explicitly pre-draft")

picks = savant["drafts"]
check(len(picks) == 2124, "All Seasons Draft Room source contains all 2,124 picks")
snake = [d for d in picks if not savant["seasons"][str(d["s"])]["auction"]]
check(len(snake) == 320 and {d["s"] for d in snake} == {2014, 2015}, "Only 2014-2015 are snake drafts")
check(all((d.get("bid") or 0) == 0 for d in snake), "Snake drafts carry no invented bids")
cols = explore_a["defBoardCols"]
def_rows = explore_a["defBoards"]
ci = {c: i for i, c in enumerate(cols)}
for pos in sorted({r[ci["pos"]] for r in def_rows}):
    src = [r for r in def_rows if r[ci["pos"]] == pos]
    total_g = sum(r[ci["g"]] for r in src)
    league_rate = sum(r[ci["afp2pg"]] * r[ci["g"]] for r in src) / total_g
    by_def = {}
    for r in src:
        g = r[ci["g"]]
        acc = by_def.setdefault(r[ci["def"]], [0, 0.0])
        acc[0] += g
        acc[1] += r[ci["afp2pg"]] * g
    weighted_index = sum(g * ((afp / g) / league_rate) for g, afp in by_def.values()) / sum(g for g, _ in by_def.values())
    check(abs(weighted_index - 1.0) < 1e-12, f"All Seasons defense index is game-weighted to 1.000 for {pos}")

check("#/drafts/all" in js and "All Seasons</a>" in js, "Draft Room exposes All Seasons")
check("link({dy:0})" in js, "Defense vs position exposes All Seasons")
check("All Seasons · Career" in js, "Career leaderboards use consistent All Seasons labeling")
check("{pi,gr:'weeks'" in js and "X.pi!=null" in js, "Player-to-Explore links use an exact identity filter")
check("g.rows.push(i)" in js and "g.rows.length<400" not in js, "Explore drill-down retains the full candidate set")
check("Object.prototype.hasOwnProperty.call(g.sums,m.k)" in js, "Explore distinguishes missing measures from real zeroes")
check("g:'',v:''" not in js and "g:ming, v:mind" in js, "Leaderboard controls preserve explicit minimums")
check("var(--line)" not in css, "All CSS tracks use defined design tokens")
check(all(name in build for name in ("explore_a.json", "explore_b.json", "explore_c.json", "gamelogs.json")), "Clean builds reconstruct omitted Explore and gamelogs monoliths")
check(js in shell and css in shell, "Published Pages shell embeds the current source JS and CSS")

for msg in OK:
    print("ok ", msg)
for msg in BAD:
    print("!! ", msg)
print(f"\n{len(OK)} passed; {len(BAD)} failed")
sys.exit(1 if BAD else 0)
