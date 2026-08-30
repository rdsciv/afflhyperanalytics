#!/usr/bin/env python3
"""Assemble the single-file AFFL Savant site: index.html (CSS + data + app inline)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
MARTS = ROOT / "data" / "marts"
REPORTS = ROOT / "data" / "reports"

savant = (MARTS / "savant_data.json").read_text()
logos = (MARTS / "logos.json").read_text()
explore = (MARTS / "explore_data.json").read_text()
luck = (MARTS / "luck_data.json").read_text()
css = (SITE / "style.css").read_text()
js = (SITE / "app.js").read_text()

affl_rep = json.load(open(REPORTS / "affl_build_report.json"))
nfl_rep = json.load(open(REPORTS / "nfl_build_report.json"))
bridge_rep = json.load(open(REPORTS / "bridge_report.json"))
marts_rep = json.load(open(REPORTS / "marts_report.json"))
xfp2_rep = json.load(open(REPORTS / "xfp2_report.json"))

starter = bridge_rep["starter_nfl_match_by_season"]
sw = sum(int(x["starter_weeks_nondst"]) for x in starter)
sm = sum(int(x["with_nfl_week"]) for x in starter)
valid = {
    "modern_ok": affl_rep["reconciliation"]["modern"]["ok"],
    "fp_recon_n": nfl_rep["fp_reconciliation_pbp_vs_official"]["n"],
    "fp_recon_pct": nfl_rep["fp_reconciliation_pbp_vs_official"]["pct_within_1"],
    "fp_recon_mad": nfl_rep["fp_reconciliation_pbp_vs_official"]["mean_abs_diff"],
    "starter_weeks": sw,
    "starter_match_pct": round(100.0 * sm / sw, 2),
    "pbp_plays": nfl_rep["counts"]["stg_pbp"],
    "bridge": {
        "rostered": bridge_rep["rostered_identities"],
        "gsis": bridge_rep["rostered_matched_gsis"],
        "dst": bridge_rep["rostered_dst"],
        "quarantined": bridge_rep["rostered_quarantined"],
    },
    "trades": marts_rep["trade_validation"],
    "xfp2": {
        "recon": xfp2_rep["actual_reconciliation_ffverse_vs_official"],
        "holdout": xfp2_rep["holdout_h1_to_h2"],
        "worst_bias_pct": xfp2_rep["calibration_worst_abs_bias_pct"],
    },
}

html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AFFL Savant — The Statistical Record of the AFFL</title>
<meta name="description" content="Twelve seasons of AFFL history joined to NFL production at the player level. Franchises, players, seasons, drafts, trades, records, and the Explore query engine.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700;800&family=IBM+Plex+Mono:wght@400;500;600&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>__CSS__</style>
</head>
<body>
<header class="topbar"><div class="wrap topbar-in">
  <a class="wordmark" href="#/">AFFL<b>SAVANT</b></a>
  <nav class="mainnav" id="nav" aria-label="Primary"></nav>
  <span class="ver">v__VER__</span>
</div></header>
<main id="app" aria-live="polite"></main>
<footer><div class="wrap">
  <span>AFFL Savant · the statistical record of the American Fantasy Football League (ESPN 51418)</span>
  <span>League truth: authenticated ESPN v3 snapshots · NFL truth: nflverse (weekly stats + play-by-play)</span>
  <span>Scoring: ESPN standard non-PPR · metrics versioned in <a class="footlink" href="#/methods">Methodology</a></span>
</div></footer>
<script>window.SAVANT=__SAVANT__;</script>
<script>window.EXPLORE=__EXPLORE__;</script>
<script>window.LUCK=__LUCK__;</script>
<script>window.VALID=__VALID__;</script>
<script>window.LOGOS=__LOGOS__;</script>
<script>__JS__</script>
</body>
</html>"""

meta = json.loads(savant)["meta"]
html = html.replace("__CSS__", css).replace("__VER__", meta["version"])
html = html.replace("__SAVANT__", savant).replace("__EXPLORE__", explore)
html = html.replace("__LUCK__", luck)
html = html.replace("__VALID__", json.dumps(valid)).replace("__LOGOS__", logos).replace("__JS__", js)

out = SITE / "index.html"
out.write_text(html)
print("wrote %s  (%.2f MB)" % (out, out.stat().st_size / 1e6))

# GitHub Pages copy: Pages (deploy-from-branch) serves only / or /docs, so the
# built site is mirrored into docs/. .nojekyll skips Jekyll processing.
docs = ROOT / "docs"
docs.mkdir(exist_ok=True)
(docs / "index.html").write_text(html)
(docs / ".nojekyll").write_text("")
print("wrote %s  (Pages mirror)" % (docs / "index.html"))
