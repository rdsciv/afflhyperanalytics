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
gamelogs = (MARTS / "gamelogs_data.json").read_text()
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
<script>window.GAMELOGS=__GAMELOGS__;</script>
<script>__JS__</script>
</body>
</html>"""

meta = json.loads(savant)["meta"]
html = html.replace("__CSS__", css).replace("__VER__", meta["version"])
html = html.replace("__SAVANT__", savant).replace("__EXPLORE__", explore)
html = html.replace("__LUCK__", luck).replace("__GAMELOGS__", gamelogs)
html = html.replace("__VALID__", json.dumps(valid)).replace("__LOGOS__", logos).replace("__JS__", js)

out = SITE / "index.html"
out.write_text(html)
print("wrote %s  (%.2f MB)" % (out, out.stat().st_size / 1e6))

# GitHub Pages variant: unlike the sandboxed artifact host (no CORS -> data
# must be inline), Pages serves same-origin static files, so docs/ ships a
# slim shell that fetches the marts. This also keeps every pushed file under
# the GitHub MCP transport cap (~4MB params): explore_data is split in half.
docs = ROOT / "docs"
data_dir = docs / "data"
data_dir.mkdir(parents=True, exist_ok=True)
(docs / ".nojekyll").write_text("")

ex = json.loads(explore)
rows = ex.pop("rows")
# three-way split keeps every pushed file well under the GitHub MCP transport
# cap (~4MB params): a = everything but rows + first third of rows; b/c = rest.
third = len(rows) // 3
ex_a = dict(ex, rows=rows[:third])
ex_b = {"rows": rows[third:2 * third]}
ex_c = {"rows": rows[2 * third:]}
def _w(name, obj):
    p = data_dir / name
    p.write_text(json.dumps(obj, separators=(",", ":"), ensure_ascii=False))
    return p.stat().st_size
sizes = {
    "savant.json": (data_dir / "savant.json").write_text(savant),
    "explore_a.json": _w("explore_a.json", ex_a),
    "explore_b.json": _w("explore_b.json", ex_b),
    "explore_c.json": _w("explore_c.json", ex_c),
    "luck.json": (data_dir / "luck.json").write_text(luck),
    "logos.json": (data_dir / "logos.json").write_text(logos),
    # gamelogs are fetched lazily (first player-page visit), not at boot
    "gamelogs.json": (data_dir / "gamelogs.json").write_text(gamelogs),
}

shell = html.split("<script>window.SAVANT=")[0]
shell = shell.replace("</head>", "<style>#bootmsg{position:fixed;inset:0;display:flex;align-items:center;justify-content:center;font:600 14px 'IBM Plex Mono',monospace;color:#8fa2bd;background:#0a0d13;z-index:99}</style></head>")
shell += """<div id="bootmsg">loading the record… <span id="bootpct"></span></div>
<script>window.VALID=__VALID__;</script>
<script>
(function(){
  // ?v= pins every data file to this shell's dataset version: a cached copy of
  // one generation can never mix with fresh copies of another (split-file skew).
  var V = '__DATAVER__';
  var files = ['data/savant.json','data/explore_a.json','data/explore_b.json','data/explore_c.json','data/luck.json','data/logos.json']
    .map(function(f){ return f+'?v='+V; });
  var done = 0, pct = document.getElementById('bootpct');
  function got(r){ if(!r.ok) throw new Error(r.url+' -> '+r.status); done++; if(pct) pct.textContent = done+'/'+files.length; return r.json(); }
  Promise.all(files.map(function(f){ return fetch(f).then(got); })).then(function(d){
    window.SAVANT = d[0];
    var ex = d[1]; ex.rows = ex.rows.concat(d[2].rows, d[3].rows);
    if(ex.meta && ex.meta.custodyRows && ex.rows.length !== ex.meta.custodyRows)
      throw new Error('data generation skew ('+ex.rows.length+' rows, expected '+ex.meta.custodyRows+') — hard-refresh (Ctrl/Cmd+Shift+R)');
    window.EXPLORE = ex;
    window.LUCK = d[4];
    window.LOGOS = d[5];
    window.GAMELOGS_URLS = ['data/gamelogs.json?v='+V];  // lazy: fetched on first player page
    document.getElementById('bootmsg').remove();
    __boot();
  }).catch(function(e){
    document.getElementById('bootmsg').textContent = 'failed to load data: '+e.message;
  });
})();
function __boot(){
__JS__
}
</script>
</body>
</html>"""
shell = shell.replace("__VALID__", json.dumps(valid)).replace("__JS__", js)
shell = shell.replace("__DATAVER__", meta["version"])
(docs / "index.html").write_text(shell)
print("wrote %s  (Pages shell, %.2f MB) + data/ splits: %s"
      % (docs / "index.html", (docs / "index.html").stat().st_size / 1e6,
         {k: "%.2f MB" % (v / 1e6) for k, v in sizes.items()}))
