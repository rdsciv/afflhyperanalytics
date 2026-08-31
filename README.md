# AFFL Annals (repo: afflannals; formerly AFFL Savant / afflhyperanalytics)

The statistical record of the AFFL (ESPN league 51418), 2014-2026 pre-draft.

## Layout
- pipeline/   fetch + build scripts (ESPN snapshots -> affl.db; nflverse -> nfl.duckdb; bridge; marts)
- data/affl.db          canonical league warehouse (SQLite) - local/full-bundle only; omitted from the GitHub API mirror
- data/nfl.duckdb       NFL warehouse (DuckDB) - rebuild: fetch_nflverse.py + build_nfl_db.py
- data/marts/           versioned site payloads (JSON) + inlined logos
- data/reports/         build/validation reports
- site/                 single-file SPA (style.css + app.js -> build_site.py -> index.html)

## Rebuild from scratch
1. Credentials: /agent/secrets/espn.env (ESPN_SWID, ESPN_S2, ESPN_LEAGUE_ID) - NEVER commit
2. python3 pipeline/fetch_espn.py          # raw ESPN snapshots (resumable)
3. python3 pipeline/fetch_nflverse.py      # nflverse assets 2014-2025
4. python3 pipeline/fetch_ffopportunity.py # ffverse ep_weekly 2014-2025 (xfp_v2 source)
4b. python3 pipeline/fetch_athlete_names.py # names for drafted-then-cut ids (public ESPN athlete API)
5. python3 pipeline/build_affl_db.py       # affl.db + identity canon + reconciliation
6. python3 pipeline/build_nfl_db.py        # nfl.duckdb + std_fp_v1 + xfp_v1 (legacy)
7. python3 pipeline/build_xfp2.py          # xfp_v2 (canon) + def-vs-pos tables + validation
8. python3 pipeline/build_bridge.py        # espn->gsis bridge + custody bridge
8b. python3 pipeline/sanitize_db.py        # strip member SWIDs from affl.db (REQUIRED before committing)
9. python3 pipeline/export_marts.py        # metrics (par_v1, trade_v1, adjfac_v1) + site marts
10. python3 pipeline/league_metrics.py     # luck/skill + rankheat_v1 + streaks_v1 (affl.db only)
11. python3 pipeline/fetch_logos.py        # inline league logos as data URIs
12. python3 site/build_site.py             # -> site/index.html + docs/index.html (Pages mirror)
13. python3 audit/audit_ui_contracts.py    # fast dashboard, scope, shard, and build contracts

## Deploy (GitHub Pages)
The build writes docs/ as a slim shell (docs/index.html) that fetches the marts from
docs/data/ same-origin (Pages serves static files; the sandboxed artifact host does not,
which is why site/index.html inlines everything instead). On GitHub: Settings -> Pages ->
Source "Deploy from a branch" -> branch `main`, folder `/(root)`. The root `index.html`
preserves the hash route and redirects into `docs/`, so leave the Pages source on root. The
site then serves at https://rdsciv.github.io/afflannals/ (pre-rename: /afflhyperanalytics/). NOTE: a Pages site is publicly
reachable at that URL regardless of repo visibility (access control for Pages is Enterprise-only),
and on the Free plan Pages requires a PUBLIC repo. The affl.db carried in full thread bundles is
sanitized (sanitize_db.py): zero member SWIDs/ids — verified by regenerating all marts
byte-identical after stripping. ESPN cookies never enter the repo.
GitHub-tree note: the API mirror excludes data/affl.db (binary over a text-only file
API) and the built site/index.html (over the transport cap); both regenerate via the
pipeline, and the full git history incl. both lives in the thread's affl-savant bundles.

Canon: franchise identity follows OWNERS (union-find on owner display names), never ESPN slot ids.
2026 is pre-draft planning only. 2014-15 snake drafts excluded from auction analysis.
Pre-2018 slots NULL/Unavailable; bench custody unobservable; multiweek playoff points matchup-grain.
