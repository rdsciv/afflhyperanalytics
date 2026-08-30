#!/usr/bin/env python3
"""AFFL Savant — identity bridge (ESPN -> GSIS) + weekly custody bridge.

Outputs (into nfl.duckdb):
  bridge_player_external   espn_id -> gsis_id with method/confidence/review
  bridge_affl_player_week  the product contract: who held/started whom, weekly
  bridge_dst_team          ESPN D/ST -> season-aware nflverse team code

A name is display data, not a join key: name matches are published only when
unambiguous, and carry match_method + review_status for the methodology page.
"""
import json
import re
import sqlite3
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
AFFL = ROOT / "data" / "affl.db"
NFL = ROOT / "data" / "nfl.duckdb"
REPORTS = ROOT / "data" / "reports"

# ESPN proTeamId -> modern nflverse code (+ historical renames by season)
ESPN_PRO = {1: "ATL", 2: "BUF", 3: "CHI", 4: "CIN", 5: "CLE", 6: "DAL", 7: "DEN",
            8: "DET", 9: "GB", 10: "TEN", 11: "IND", 12: "KC", 13: "LV", 14: "LA",
            15: "MIA", 16: "MIN", 17: "NE", 18: "NO", 19: "NYG", 20: "NYJ",
            21: "PHI", 22: "ARI", 23: "PIT", 24: "LAC", 25: "SF", 26: "SEA",
            27: "TB", 28: "WAS", 29: "CAR", 30: "JAX", 33: "BAL", 34: "HOU"}


def team_code(pro_id, season):
    code = ESPN_PRO.get(pro_id)
    if code == "LA" and season < 2016:
        return "STL"
    if code == "LAC" and season < 2017:
        return "SD"
    if code == "LV" and season < 2020:
        return "OAK"
    return code


def norm(name):
    s = re.sub(r"[^a-z ]", "", (name or "").lower().replace(".", " "))
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", s)
    return " ".join(s.split())


POS_BY_ESPN = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DST"}

ax = sqlite3.connect(str(AFFL))
espn_players = pd.read_sql_query(
    "SELECT espn_player_id, full_name, default_position_id, pro_team_id, is_dst, "
    "first_seen_season, last_seen_season FROM dim_player_espn", ax)

# custody universe: everyone who ever appears on a roster week or playoff matchup
rostered = pd.read_sql_query("""
  SELECT DISTINCT espn_player_id FROM (
    SELECT espn_player_id FROM fact_roster_week
    UNION SELECT espn_player_id FROM fact_matchup_player_pre2018)""", ax)
rostered_ids = set(rostered.espn_player_id)

con = duckdb.connect(str(NFL))
nfl_players = con.execute("""
  SELECT gsis_id, display_name, position, espn_id, rookie_season, last_season
  FROM dim_nfl_player""").fetchdf()
roster_map = con.execute("""
  SELECT DISTINCT CAST(espn_id AS VARCHAR) AS espn_id, gsis_id
  FROM stg_rosters WHERE espn_id IS NOT NULL""").fetchdf()

by_espn = {}
for r in nfl_players.itertuples():
    if r.espn_id and str(r.espn_id) != "nan":
        by_espn.setdefault(str(int(float(r.espn_id))), r.gsis_id)
for r in roster_map.itertuples():
    if r.espn_id:
        by_espn.setdefault(str(int(float(r.espn_id))), r.gsis_id)

# name index for fallback (position-aware)
name_idx = {}
for r in nfl_players.itertuples():
    name_idx.setdefault((norm(r.display_name), r.position), []).append(r.gsis_id)

rows = []
for p in espn_players.itertuples():
    pid = p.espn_player_id
    if p.is_dst:
        rows.append((pid, p.full_name, None, "dst", 1.0, "resolved_team", int(pid in rostered_ids)))
        continue
    g = by_espn.get(str(pid))
    method, conf, review = "espn_id", 1.0, "reviewed_provider_id"
    if g is None:
        pos = POS_BY_ESPN.get(p.default_position_id)
        cands = name_idx.get((norm(p.full_name), pos), [])
        if len(cands) == 1:
            g, method, conf, review = cands[0], "name_position", 0.8, "auto_unambiguous"
        else:
            cands2 = name_idx.get((norm(p.full_name), None), [])
            allc = {c for c in cands + cands2}
            if len(allc) == 1:
                g, method, conf, review = list(allc)[0], "name_only", 0.6, "auto_unambiguous"
            else:
                method, conf, review = "unmatched", 0.0, "quarantined"
    rows.append((pid, p.full_name, g, method, conf, review, int(pid in rostered_ids)))

bridge = pd.DataFrame(rows, columns=["espn_player_id", "full_name", "gsis_id",
                                     "match_method", "match_confidence",
                                     "review_status", "ever_rostered"])
con.execute("DROP TABLE IF EXISTS bridge_player_external")
con.execute("CREATE TABLE bridge_player_external AS SELECT * FROM bridge")

# D/ST team mapping rows (per season seen)
dst = espn_players[espn_players.is_dst == 1]
dst_rows = []
for p in dst.itertuples():
    for season in range(p.first_seen_season, p.last_seen_season + 1):
        dst_rows.append((p.espn_player_id, season, team_code(p.pro_team_id, season)))
dst_df = pd.DataFrame(dst_rows, columns=["espn_player_id", "season", "nfl_team"])
con.execute("DROP TABLE IF EXISTS bridge_dst_team")
con.execute("CREATE TABLE bridge_dst_team AS SELECT * FROM dst_df")

# ---- custody bridge ----------------------------------------------------------
rw = pd.read_sql_query("""
  SELECT rw.season, rw.week, rw.team_id, ts.franchise_id, rw.espn_player_id,
         rw.lineup_slot_id, rw.started, rw.applied_points, rw.projected_points,
         rw.injury_status, rw.acquisition_type, rw.slot_evidence, rw.source
  FROM fact_roster_week rw
  JOIN dim_team_season ts ON ts.season = rw.season AND ts.team_id = rw.team_id""", ax)
con.execute("DROP TABLE IF EXISTS bridge_affl_player_week")
con.execute("""
CREATE TABLE bridge_affl_player_week AS
SELECT rw.season, rw.week, rw.franchise_id, rw.team_id, rw.espn_player_id,
       b.gsis_id, d.nfl_team AS dst_team,
       1 AS rostered, rw.started, rw.lineup_slot_id, rw.slot_evidence,
       rw.applied_points AS affl_points, rw.projected_points,
       rw.injury_status, rw.acquisition_type, rw.source
FROM rw
LEFT JOIN bridge_player_external b USING (espn_player_id)
LEFT JOIN bridge_dst_team d ON d.espn_player_id = rw.espn_player_id AND d.season = rw.season
""")

# ---- coverage report ----------------------------------------------------------
cov = con.execute("""
SELECT season,
  COUNT(*) AS roster_weeks,
  SUM(CASE WHEN gsis_id IS NOT NULL OR dst_team IS NOT NULL THEN 1 ELSE 0 END) AS identified,
  SUM(started) AS starter_weeks,
  SUM(CASE WHEN started=1 AND (gsis_id IS NOT NULL OR dst_team IS NOT NULL) THEN 1 ELSE 0 END) AS starter_identified
FROM bridge_affl_player_week GROUP BY season ORDER BY season""").fetchdf()

# starter-week NFL stat match: started non-DST players joined to a real NFL week row
match = con.execute("""
SELECT b.season,
  COUNT(*) AS starter_weeks_nondst,
  SUM(CASE WHEN w.gsis_id IS NOT NULL THEN 1 ELSE 0 END) AS with_nfl_week,
  SUM(CASE WHEN w.gsis_id IS NULL AND COALESCE(b.affl_points,0) != 0 THEN 1 ELSE 0 END) AS unmatched_nonzero
FROM bridge_affl_player_week b
LEFT JOIN fact_player_week w
  ON w.gsis_id = b.gsis_id AND w.season = b.season AND w.week = b.week
WHERE b.started = 1 AND b.dst_team IS NULL
GROUP BY b.season ORDER BY b.season""").fetchdf()

quarantined = con.execute("""
SELECT espn_player_id, full_name, ever_rostered FROM bridge_player_external
WHERE review_status = 'quarantined' ORDER BY ever_rostered DESC, full_name""").fetchdf()

summary = {
    "bridge_total": len(bridge),
    "rostered_identities": int(bridge.ever_rostered.sum()),
    "rostered_dst": int(bridge[(bridge.ever_rostered == 1) & (bridge.match_method == "dst")].shape[0]),
    "rostered_matched_gsis": int(bridge[(bridge.ever_rostered == 1) & bridge.gsis_id.notna()].shape[0]),
    "rostered_quarantined": int(bridge[(bridge.ever_rostered == 1) & (bridge.review_status == "quarantined")].shape[0]),
    "by_method": bridge.groupby("match_method").size().to_dict(),
    "custody_rows": int(con.execute("SELECT COUNT(*) FROM bridge_affl_player_week").fetchone()[0]),
    "coverage_by_season": cov.to_dict("records"),
    "starter_nfl_match_by_season": match.to_dict("records"),
    "quarantined_rostered": quarantined[quarantined.ever_rostered == 1].to_dict("records"),
}
REPORTS.mkdir(parents=True, exist_ok=True)
json.dump(summary, open(REPORTS / "bridge_report.json", "w"), indent=2, default=str)

overall = match.starter_weeks_nondst.sum()
matched = match.with_nfl_week.sum()
print("rostered identities: %d (dst %d, gsis %d, quarantined %d)" % (
    summary["rostered_identities"], summary["rostered_dst"],
    summary["rostered_matched_gsis"], summary["rostered_quarantined"]))
print("methods:", summary["by_method"])
print("custody rows:", summary["custody_rows"])
print("starter non-DST weeks: %d, with NFL week row: %d (%.2f%%), unmatched w/ nonzero pts: %d" % (
    overall, matched, 100.0 * matched / overall, match.unmatched_nonzero.sum()))
print("quarantined+rostered:", len(summary["quarantined_rostered"]))
con.close()
ax.close()
