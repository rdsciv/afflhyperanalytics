#!/usr/bin/env python3
"""AFFL Savant — xFP v2 from ffopportunity (nflverse canon) + opponent adjustment.

Adds to nfl.duckdb (run AFTER build_nfl_db.py):
  fact_player_week_xfp2   canon expected FP per player-week, AFFL-rescored
  fact_def_pos_week       defense x position x week FP allowed (both scopes)
  fact_def_pos_season     defense x position x season factors (LOO-safe inputs)

Metric versions:
  xfp_v2   Expected AFFL FP from ffverse/ffopportunity expected stats (the
           nflreadr::load_ff_opportunity() payload): XGBoost completion
           probability + xYAC models trained by ffverse on nflfastR pbp.
           Rescored here to AFFL scoring: pass 0.04/yd, 4 TD, -2 INT;
           rush/rec 0.1/yd, 6 TD; +2 two-point (all families).
           SCOPE NOTE: no fumble term (ffopportunity does not model expected
           fumbles) and no kicking/ST. Its paired actual (afp_v2) uses the
           SAME scope so fpoe_v2 = afp_v2 - xfp_v2 is same-scope by
           construction. v1 buckets baked league-average fumble rates into
           expectations; v2 is silent on fumbles on both sides.
           rec_interception (INTs on passes targeting the player) is not a
           fantasy-scoring event and is excluded from both sides.
  adjfac_v1  Opponent factor: defense x position season factor on the afp_v2
           scope, leave-one-week-out, shrunk toward 1 by g/(g+4). Adjusted
           expectation = xfp_v2 * factor; adj FPOE = afp_v2 - adjusted.

Validation battery (data/reports/xfp2_report.json):
  1. grain uniqueness (season, week, gsis_id)
  2. join coverage vs official weekly stats (QB/RB/WR/TE)
  3. independent-path actual reconciliation: afp_v2 (pbp-aggregated by
     ffverse) vs same-scope FP recomputed from official gamebook weekly stats
  4. calibration: sum(xfp2) vs sum(afp2) by position x season
  5. holdout predictiveness: weeks 1-8 mean xFP -> weeks 9+ mean actual,
     v2 vs v1 vs actual-as-predictor, same player set, 2014-2025
"""
import json
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "ffopportunity"
DB = ROOT / "data" / "nfl.duckdb"
REPORTS = ROOT / "data" / "reports"

con = duckdb.connect(str(DB))
con.execute("SET threads TO 4")

for t in ("fact_player_week_xfp2", "fact_def_pos_week", "fact_def_pos_season"):
    con.execute("DROP TABLE IF EXISTS %s" % t)

# ---- xfp2: AFFL-rescored expected + same-scope actual -------------------------
# REG filter mirrors fact_player_week: weeks <=17 through 2020, <=18 from 2021.
AFFL_EXPR = """
  0.04*COALESCE(pass_yards_gained{sfx},0) + 4*COALESCE(pass_touchdown{sfx},0)
  - 2*COALESCE(pass_interception{sfx},0)
  + 0.1*(COALESCE(rush_yards_gained{sfx},0) + COALESCE(rec_yards_gained{sfx},0))
  + 6*(COALESCE(rush_touchdown{sfx},0) + COALESCE(rec_touchdown{sfx},0))
  + 2*(COALESCE(pass_two_point_conv{sfx},0) + COALESCE(rush_two_point_conv{sfx},0)
       + COALESCE(rec_two_point_conv{sfx},0))
"""
con.execute("""
CREATE TABLE fact_player_week_xfp2 AS
SELECT CAST(season AS INTEGER) AS season, CAST(week AS INTEGER) AS week,
       player_id AS gsis_id, ANY_VALUE(posteam) AS team,
       ROUND(SUM(%s), 2) AS xfp2,
       ROUND(SUM(%s), 2) AS afp2,
       ROUND(SUM(%s) - SUM(%s), 2) AS fpoe2
FROM read_parquet('%s', union_by_name=true)
WHERE player_id IS NOT NULL
  AND ((CAST(season AS INTEGER) <= 2020 AND week <= 17)
       OR (CAST(season AS INTEGER) >= 2021 AND week <= 18))
GROUP BY 1, 2, 3
""" % (AFFL_EXPR.format(sfx="_exp"), AFFL_EXPR.format(sfx=""),
       AFFL_EXPR.format(sfx=""), AFFL_EXPR.format(sfx="_exp"),
       RAW / "ep_weekly_*.parquet"))

# ---- validation 1: grain ------------------------------------------------------
dups = con.execute("""
SELECT COUNT(*) FROM (SELECT season, week, gsis_id FROM fact_player_week_xfp2
GROUP BY 1,2,3 HAVING COUNT(*) > 1)""").fetchone()[0]

# ---- validation 2: join coverage ---------------------------------------------
cov = con.execute("""
WITH official AS (
  SELECT gsis_id, season, week, std_fp, position FROM fact_player_week
  WHERE position IN ('QB','RB','WR','TE')
)
SELECT o.season,
       COUNT(*) AS official_pw,
       SUM(CASE WHEN x.gsis_id IS NOT NULL THEN 1 ELSE 0 END) AS matched,
       ROUND(SUM(CASE WHEN x.gsis_id IS NOT NULL THEN 1 ELSE 0 END)*100.0/COUNT(*), 2) AS pct,
       SUM(CASE WHEN x.gsis_id IS NULL AND ABS(o.std_fp) > 3 THEN 1 ELSE 0 END) AS unmatched_gt3fp
FROM official o
LEFT JOIN fact_player_week_xfp2 x USING (gsis_id, season, week)
GROUP BY 1 ORDER BY 1""").fetchall()

# ---- validation 3: independent-path actual reconciliation ---------------------
# afp2 (ffverse pbp aggregation) vs same-scope FP from official gamebook stats
recon = con.execute("""
WITH official_scope AS (
  SELECT gsis_id, season, week,
         0.04*COALESCE(passing_yards,0) + 4*COALESCE(passing_tds,0)
         - 2*COALESCE(passing_interceptions,0)
         + 0.1*(COALESCE(rushing_yards,0) + COALESCE(receiving_yards,0))
         + 6*(COALESCE(rushing_tds,0) + COALESCE(receiving_tds,0))
         + 2*(COALESCE(passing_2pt_conversions,0) + COALESCE(rushing_2pt_conversions,0)
              + COALESCE(receiving_2pt_conversions,0)) AS fp_official_scope
  FROM fact_player_week
  WHERE position IN ('QB','RB','WR','TE')
)
SELECT COUNT(*) AS n,
       ROUND(AVG(ABS(x.afp2 - o.fp_official_scope)), 3) AS mean_abs_diff,
       ROUND(SUM(CASE WHEN ABS(x.afp2 - o.fp_official_scope) <= 1.0 THEN 1 ELSE 0 END)*100.0/COUNT(*), 2) AS pct_within_1,
       ROUND(MAX(ABS(x.afp2 - o.fp_official_scope)), 1) AS worst
FROM fact_player_week_xfp2 x
JOIN official_scope o USING (gsis_id, season, week)
""").fetchdf().to_dict("records")[0]

# ---- validation 4: calibration by position x season ---------------------------
calib = con.execute("""
SELECT w.position, x.season,
       ROUND(SUM(x.xfp2), 0) AS xfp2_sum, ROUND(SUM(x.afp2), 0) AS afp2_sum,
       ROUND((SUM(x.afp2) - SUM(x.xfp2))*100.0/NULLIF(SUM(x.xfp2),0), 2) AS bias_pct
FROM fact_player_week_xfp2 x
JOIN fact_player_week w USING (gsis_id, season, week)
WHERE w.position IN ('QB','RB','WR','TE')
GROUP BY 1, 2 ORDER BY 1, 2""").fetchall()
worst_bias = max(abs(r[4]) for r in calib if r[4] is not None)

# ---- validation 5: holdout predictiveness (H1 -> H2), v2 vs v1 ----------------
pred = con.execute("""
WITH joined AS (
  SELECT w.gsis_id, w.season, w.week, w.position,
         x2.xfp2, x2.afp2, x1.xfp AS xfp1, x1.actual_fp_pbp AS afp1
  FROM fact_player_week w
  JOIN fact_player_week_xfp2 x2 USING (gsis_id, season, week)
  JOIN fact_player_week_xfp  x1 USING (gsis_id, season, week)
  WHERE w.position IN ('QB','RB','WR','TE')
), halves AS (
  SELECT gsis_id, season, ANY_VALUE(position) AS position,
         AVG(CASE WHEN week <= 8 THEN xfp2 END) AS h1_xfp2,
         AVG(CASE WHEN week <= 8 THEN afp2 END) AS h1_afp2,
         AVG(CASE WHEN week <= 8 THEN xfp1 END) AS h1_xfp1,
         AVG(CASE WHEN week <= 8 THEN afp1 END) AS h1_afp1,
         AVG(CASE WHEN week > 8 THEN afp2 END) AS h2_afp2,
         AVG(CASE WHEN week > 8 THEN afp1 END) AS h2_afp1,
         SUM(CASE WHEN week <= 8 THEN 1 ELSE 0 END) AS g1,
         SUM(CASE WHEN week > 8 THEN 1 ELSE 0 END) AS g2
  FROM joined GROUP BY 1, 2
)
SELECT position, COUNT(*) AS n,
       ROUND(CORR(h1_xfp2, h2_afp2), 4) AS xfp2_pred,
       ROUND(CORR(h1_afp2, h2_afp2), 4) AS actual_pred,
       ROUND(CORR(h1_xfp1, h2_afp1), 4) AS xfp1_pred,
       ROUND(CORR(h1_afp1, h2_afp1), 4) AS actual1_pred
FROM halves WHERE g1 >= 5 AND g2 >= 5
GROUP BY ROLLUP(position) ORDER BY position NULLS FIRST""").fetchall()

# ---- defense x position allowed (both scopes) ---------------------------------
con.execute("""
CREATE TABLE fact_def_pos_week AS
SELECT w.season, w.week, w.opponent AS defteam, w.position,
       COUNT(*) AS players,
       ROUND(SUM(w.std_fp), 2) AS std_fp_allowed,
       ROUND(SUM(COALESCE(x.afp2, 0)), 2) AS afp2_allowed,
       ROUND(SUM(COALESCE(x.xfp2, 0)), 2) AS xfp2_allowed
FROM fact_player_week w
LEFT JOIN fact_player_week_xfp2 x USING (gsis_id, season, week)
WHERE w.position IN ('QB','RB','WR','TE','K') AND w.opponent IS NOT NULL
GROUP BY 1, 2, 3, 4
""")

# season rollup + leave-one-week-out factor inputs on afp2 scope
con.execute("""
CREATE TABLE fact_def_pos_season AS
WITH d AS (
  SELECT season, defteam, position,
         COUNT(DISTINCT week) AS g,
         SUM(afp2_allowed) AS afp2_tot,
         SUM(std_fp_allowed) AS std_tot,
         SUM(xfp2_allowed) AS xfp2_tot
  FROM fact_def_pos_week
  WHERE position IN ('QB','RB','WR','TE')
  GROUP BY 1, 2, 3
), lg AS (
  SELECT season, position, SUM(afp2_tot) AS lg_afp2, SUM(g) AS lg_g
  FROM d GROUP BY 1, 2
)
SELECT d.season, d.defteam, d.position, d.g,
       ROUND(d.afp2_tot / d.g, 2) AS afp2_allowed_pg,
       ROUND(d.std_tot / d.g, 2) AS std_fp_allowed_pg,
       ROUND(d.xfp2_tot / d.g, 2) AS xfp2_allowed_pg,
       ROUND(lg.lg_afp2 / lg.lg_g, 2) AS lg_afp2_pg,
       d.afp2_tot AS afp2_tot, lg.lg_afp2 AS lg_afp2_tot, lg.lg_g AS lg_g
FROM d JOIN lg USING (season, position)
""")

counts = {}
for t in ("fact_player_week_xfp2", "fact_def_pos_week", "fact_def_pos_season"):
    counts[t] = con.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]

report = {
    "counts": counts,
    "grain_duplicates": dups,
    "join_coverage_by_season": [
        {"season": r[0], "official_pw": r[1], "matched": r[2], "pct": r[3],
         "unmatched_gt3fp": r[4]} for r in cov],
    "actual_reconciliation_ffverse_vs_official": recon,
    "calibration_worst_abs_bias_pct": worst_bias,
    "calibration_by_pos_season": [
        {"pos": r[0], "season": r[1], "xfp2": r[2], "afp2": r[3], "bias_pct": r[4]}
        for r in calib],
    "holdout_h1_to_h2": [
        {"pos": r[0] or "ALL", "n": r[1], "xfp2_pred_r": r[2], "actual2_pred_r": r[3],
         "xfp1_pred_r": r[4], "actual1_pred_r": r[5]} for r in pred],
}
REPORTS.mkdir(parents=True, exist_ok=True)
json.dump(report, open(REPORTS / "xfp2_report.json", "w"), indent=2, default=str)
print(json.dumps({k: v for k, v in report.items()
                  if k not in ("calibration_by_pos_season", "join_coverage_by_season")},
                 indent=2, default=str))
print("\njoin coverage (first/last 3):")
for r in report["join_coverage_by_season"][:3] + report["join_coverage_by_season"][-3:]:
    print(" ", r)
con.close()
