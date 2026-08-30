#!/usr/bin/env python3
"""AFFL Savant — build nfl.duckdb (NFL performance warehouse) from nflverse.

Tables:
  dim_nfl_player          players.csv identity + espn_id mapping
  fact_player_week        official weekly stats (stats_player_week_*) + std_fp
  fact_player_week_opp    pbp-derived opportunity/efficiency per player-week-role
  xfp_bucket_*            xFP v1 reference curves (rush/target/dropback)
  fact_player_week_xfp    xFP + FPOE per player-week (skill positions)

Metric versions:
  std_fp_v1  standard non-PPR: pass 0.04/yd, 4 TD, -2 INT; rush/rec 0.1/yd,
             6 TD; -2 fumble lost; +2 two-point; ST TD 6; K: distance-tiered
             FG (3/4/5) + PAT 1 when distance columns exist, else 3 flat.
  xfp_v1     expected std_fp from opportunity buckets learned on 2014-2025 pbp:
             rush by yardline bins; targets by air-yards bins x red zone;
             dropbacks by yardline bins. FPOE = actual - expected.
"""
import duckdb
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "nflverse"
DB = ROOT / "data" / "nfl.duckdb"
REPORTS = ROOT / "data" / "reports"

if DB.exists():
    DB.unlink()
con = duckdb.connect(str(DB))
con.execute("SET threads TO 4")

# ---- identity ---------------------------------------------------------------
con.execute("""
CREATE TABLE dim_nfl_player AS
SELECT gsis_id, display_name, position_group, position, espn_id,
       birth_date, height, weight, headshot, college_name, jersey_number,
       rookie_season, last_season, latest_team, status
FROM read_csv_auto('%s', types={'espn_id':'VARCHAR','jersey_number':'VARCHAR'})
WHERE gsis_id IS NOT NULL
""" % (RAW / "players.csv"))

# season rosters give per-season espn_id backfill
con.execute("""
CREATE TABLE stg_rosters AS
SELECT season, team, position, full_name, gsis_id, CAST(espn_id AS VARCHAR) AS espn_id
FROM read_csv_auto('%s', union_by_name=true, types={'espn_id':'VARCHAR'})
WHERE gsis_id IS NOT NULL
""" % (RAW / "roster_*.csv"))

# ---- official weekly stats --------------------------------------------------
con.execute("""
CREATE TABLE fact_player_week AS
WITH raw AS (
  SELECT * FROM read_csv_auto('%s', union_by_name=true)
)
SELECT
  player_id AS gsis_id, player_display_name AS name, position, position_group,
  season, week, team, opponent_team AS opponent,
  completions, attempts, passing_yards, passing_tds, passing_interceptions,
  sacks_suffered,
  passing_air_yards, passing_epa, passing_cpoe, passing_2pt_conversions,
  carries, rushing_yards, rushing_tds, rushing_fumbles_lost, rushing_epa,
  rushing_2pt_conversions,
  receptions, targets, receiving_yards, receiving_tds, receiving_fumbles_lost,
  receiving_air_yards, receiving_yards_after_catch, receiving_epa,
  receiving_2pt_conversions, target_share, air_yards_share, wopr,
  sack_fumbles_lost, special_teams_tds,
  fg_made, fg_att, COALESCE(fg_made_0_19,0)+COALESCE(fg_made_20_29,0)+COALESCE(fg_made_30_39,0) AS fg_made_u40,
  COALESCE(fg_made_40_49,0) AS fg_made_40s,
  COALESCE(fg_made_50_59,0)+COALESCE(fg_made_60_,0) AS fg_made_50p,
  pat_made, pat_att,
  ROUND(
    COALESCE(passing_yards,0)*0.04 + COALESCE(passing_tds,0)*4
    - COALESCE(passing_interceptions,0)*2 + COALESCE(passing_2pt_conversions,0)*2
    + COALESCE(rushing_yards,0)*0.1 + COALESCE(rushing_tds,0)*6
    + COALESCE(rushing_2pt_conversions,0)*2
    + COALESCE(receiving_yards,0)*0.1 + COALESCE(receiving_tds,0)*6
    + COALESCE(receiving_2pt_conversions,0)*2
    - (COALESCE(sack_fumbles_lost,0)+COALESCE(rushing_fumbles_lost,0)+COALESCE(receiving_fumbles_lost,0))*2
    + COALESCE(special_teams_tds,0)*6
    + CASE WHEN COALESCE(fg_made,0)+COALESCE(pat_made,0) > 0 THEN
        CASE WHEN COALESCE(fg_made_0_19,0)+COALESCE(fg_made_20_29,0)+COALESCE(fg_made_30_39,0)
                  +COALESCE(fg_made_40_49,0)+COALESCE(fg_made_50_59,0)+COALESCE(fg_made_60_,0) = COALESCE(fg_made,0)
        THEN (COALESCE(fg_made_0_19,0)+COALESCE(fg_made_20_29,0)+COALESCE(fg_made_30_39,0))*3
             + COALESCE(fg_made_40_49,0)*4 + (COALESCE(fg_made_50_59,0)+COALESCE(fg_made_60_,0))*5
        ELSE COALESCE(fg_made,0)*3 END
        + COALESCE(pat_made,0)*1
      ELSE 0 END
  , 2) AS std_fp
FROM raw
WHERE season_type = 'REG'
""" % (RAW / "stats_player_week_*.csv"))

# ---- pbp: per-play role rows with std fantasy value -------------------------
con.execute("""
CREATE TABLE stg_pbp AS
SELECT season, week, game_id, play_id, posteam, defteam, yardline_100,
       play_type, two_point_attempt, two_point_conv_result,
       rush_attempt, pass_attempt, qb_dropback, sack, complete_pass,
       interception, pass_touchdown, rush_touchdown, yards_gained,
       air_yards, yards_after_catch, epa, qb_epa, success, cpoe,
       passer_player_id, rusher_player_id, receiver_player_id,
       fumble_lost, fumbled_1_player_id
FROM read_parquet('%s', union_by_name=true)
WHERE (qb_dropback = 1 OR rush_attempt = 1) AND posteam IS NOT NULL
  -- FIX: official weekly stats are REG-only; pbp-derived opportunity/EPA/xFP
  -- must match that scope or the two paths are not comparable (4.2 to 4.9 pct of
  -- role-plays are POST, measured on 2024).
  AND season_type = 'REG'
""" % (RAW / "play_by_play_*.parquet"))

# role rows: rush
con.execute("""
CREATE TABLE stg_rush AS
SELECT season, week, game_id, play_id, posteam, defteam, yardline_100,
       rusher_player_id AS gsis_id, epa, success,
       CASE WHEN two_point_attempt=1 THEN 0 ELSE COALESCE(yards_gained,0) END AS yards,
       rush_touchdown AS td,
       CASE WHEN fumble_lost=1 AND fumbled_1_player_id=rusher_player_id THEN 1 ELSE 0 END AS fum_lost,
       CASE WHEN two_point_attempt=1 AND two_point_conv_result='success' THEN 1 ELSE 0 END AS two_pt,
       CASE WHEN yardline_100 <= 5 THEN 1 ELSE 0 END AS goal_line,
       CASE WHEN yardline_100 <= 20 THEN 1 ELSE 0 END AS red_zone,
       CASE WHEN two_point_attempt=1 THEN 2.0*(CASE WHEN two_point_conv_result='success' THEN 1 ELSE 0 END)
            ELSE COALESCE(yards_gained,0)*0.1 + rush_touchdown*6
                 - 2*(CASE WHEN fumble_lost=1 AND fumbled_1_player_id=rusher_player_id THEN 1 ELSE 0 END)
       END AS fp,
       two_point_attempt AS is_2pt, play_type
FROM stg_pbp WHERE rush_attempt = 1 AND rusher_player_id IS NOT NULL
""")

# role rows: target
con.execute("""
CREATE TABLE stg_tgt AS
SELECT season, week, game_id, play_id, posteam, defteam, yardline_100,
       receiver_player_id AS gsis_id, epa, success, air_yards,
       complete_pass, COALESCE(yards_after_catch,0) AS yac,
       CASE WHEN two_point_attempt=1 THEN 0 ELSE complete_pass*COALESCE(yards_gained,0) END AS yards,
       pass_touchdown AS td,
       CASE WHEN fumble_lost=1 AND fumbled_1_player_id=receiver_player_id THEN 1 ELSE 0 END AS fum_lost,
       CASE WHEN two_point_attempt=1 AND two_point_conv_result='success' THEN 1 ELSE 0 END AS two_pt,
       CASE WHEN yardline_100 <= 20 THEN 1 ELSE 0 END AS red_zone,
       CASE WHEN air_yards IS NOT NULL AND air_yards >= yardline_100 THEN 1 ELSE 0 END AS end_zone_tgt,
       CASE WHEN two_point_attempt=1 THEN 2.0*(CASE WHEN two_point_conv_result='success' THEN 1 ELSE 0 END)
            ELSE complete_pass*COALESCE(yards_gained,0)*0.1 + pass_touchdown*6
                 - 2*(CASE WHEN fumble_lost=1 AND fumbled_1_player_id=receiver_player_id THEN 1 ELSE 0 END)
       END AS fp,
       two_point_attempt AS is_2pt, play_type
FROM stg_pbp WHERE pass_attempt = 1 AND receiver_player_id IS NOT NULL
""")

# role rows: dropback (passer)
con.execute("""
CREATE TABLE stg_dropback AS
SELECT season, week, game_id, play_id, posteam, defteam, yardline_100,
       passer_player_id AS gsis_id, qb_epa AS epa, success, cpoe,
       sack, complete_pass, interception, air_yards,
       CASE WHEN two_point_attempt=1 THEN 0 ELSE complete_pass*COALESCE(yards_gained,0) END AS yards,
       pass_touchdown AS td,
       CASE WHEN two_point_attempt=1 THEN 2.0*(CASE WHEN two_point_conv_result='success' THEN 1 ELSE 0 END)
            ELSE complete_pass*COALESCE(yards_gained,0)*0.04 + pass_touchdown*4 - interception*2
                 - 2*(CASE WHEN fumble_lost=1 AND fumbled_1_player_id=passer_player_id THEN 1 ELSE 0 END)
       END AS fp,
       two_point_attempt AS is_2pt, play_type
FROM stg_pbp WHERE qb_dropback = 1 AND passer_player_id IS NOT NULL
""")

# Bucket key expressions are defined ONCE and reused for both learning the
# reference curve and applying it, so the two can never drift apart.
# two-point attempts get their OWN bucket: they are not scrimmage downs, and
# folding them into the goal-line band understated it by 5.5 pct (2024, measured).
RUSH_BIN = """CASE WHEN is_2pt = 1 THEN '2pt'
            WHEN yardline_100<=2 THEN '01-02' WHEN yardline_100<=5 THEN '03-05'
            WHEN yardline_100<=10 THEN '06-10' WHEN yardline_100<=20 THEN '11-20'
            WHEN yardline_100<=40 THEN '21-40' WHEN yardline_100<=60 THEN '41-60'
            ELSE '61-99' END"""
TGT_BIN = """CASE WHEN is_2pt = 1 THEN '2pt'
            WHEN air_yards IS NULL THEN 'na' WHEN air_yards < 0 THEN 'neg'
            WHEN air_yards <= 4 THEN '00-04' WHEN air_yards <= 9 THEN '05-09'
            WHEN air_yards <= 14 THEN '10-14' WHEN air_yards <= 19 THEN '15-19'
            WHEN air_yards <= 29 THEN '20-29' ELSE '30+' END"""
DB_BIN = """CASE WHEN is_2pt = 1 THEN '2pt'
            WHEN yardline_100<=10 THEN '01-10' WHEN yardline_100<=20 THEN '11-20'
            WHEN yardline_100<=40 THEN '21-40' WHEN yardline_100<=60 THEN '41-60'
            ELSE '61-99' END"""

# ---- xFP v1 buckets ----------------------------------------------------------
con.execute("""
CREATE TABLE xfp_bucket_rush AS
SELECT %s AS yl_bin, AVG(fp) AS exp_fp, COUNT(*) AS n
FROM stg_rush
WHERE COALESCE(play_type, '') NOT IN ('qb_kneel', 'qb_spike')
GROUP BY 1
""" % RUSH_BIN)
con.execute("""
CREATE TABLE xfp_bucket_tgt AS
SELECT %s AS air_bin, red_zone, AVG(fp) AS exp_fp, COUNT(*) AS n
FROM stg_tgt
WHERE COALESCE(play_type, '') NOT IN ('qb_kneel', 'qb_spike')
GROUP BY 1, 2
""" % TGT_BIN)
con.execute("""
CREATE TABLE xfp_bucket_dropback AS
SELECT %s AS yl_bin, AVG(fp) AS exp_fp, COUNT(*) AS n
FROM stg_dropback
WHERE COALESCE(play_type, '') NOT IN ('qb_kneel', 'qb_spike')
GROUP BY 1
""" % DB_BIN)

# ---- per player-week opportunity + xfp ---------------------------------------
con.execute(("""
CREATE TABLE fact_player_week_opp AS
WITH r AS (
  SELECT season, week, gsis_id, ANY_VALUE(posteam) AS team,
         COUNT(*) AS carries, SUM(yards) AS rush_yards, SUM(td) AS rush_tds,
         SUM(goal_line) AS gl_carries, SUM(red_zone) AS rz_carries,
         SUM(epa) AS rush_epa, AVG(CAST(success AS DOUBLE)) AS rush_success,
         SUM(fp) AS rush_fp,
         SUM(b.exp_fp) AS rush_xfp
  FROM stg_rush
  JOIN xfp_bucket_rush b ON b.yl_bin = {RUSH_BIN}
  GROUP BY 1,2,3
), t AS (
  SELECT season, week, gsis_id, ANY_VALUE(posteam) AS team,
         COUNT(*) AS targets, SUM(complete_pass) AS receptions,
         SUM(yards) AS rec_yards, SUM(td) AS rec_tds,
         SUM(COALESCE(air_yards,0)) AS air_yards, SUM(yac) AS yac,
         AVG(air_yards) AS adot,
         SUM(stg_tgt.red_zone) AS rz_targets, SUM(end_zone_tgt) AS ez_targets,
         SUM(epa) AS rec_epa, AVG(CAST(success AS DOUBLE)) AS tgt_success,
         SUM(fp) AS rec_fp,
         SUM(b.exp_fp) AS rec_xfp
  FROM stg_tgt
  JOIN xfp_bucket_tgt b ON b.air_bin = {TGT_BIN}
        AND b.red_zone = stg_tgt.red_zone
  GROUP BY 1,2,3
), d AS (
  SELECT season, week, gsis_id, ANY_VALUE(posteam) AS team,
         COUNT(*) AS dropbacks, SUM(sack) AS sacks_taken,
         SUM(complete_pass) AS completions, SUM(yards) AS pass_yards,
         SUM(td) AS pass_tds, SUM(interception) AS ints,
         SUM(epa) AS pass_epa, AVG(CAST(success AS DOUBLE)) AS db_success,
         AVG(cpoe) AS cpoe, SUM(fp) AS pass_fp,
         SUM(b.exp_fp) AS pass_xfp
  FROM stg_dropback
  JOIN xfp_bucket_dropback b ON b.yl_bin = {DB_BIN}
  GROUP BY 1,2,3
)
SELECT COALESCE(r.season, t.season, d.season) AS season,
       COALESCE(r.week, t.week, d.week) AS week,
       COALESCE(r.gsis_id, t.gsis_id, d.gsis_id) AS gsis_id,
       COALESCE(r.team, t.team, d.team) AS team,
       COALESCE(carries,0) AS carries, COALESCE(rush_yards,0) AS rush_yards,
       COALESCE(rush_tds,0) AS rush_tds, COALESCE(gl_carries,0) AS gl_carries,
       COALESCE(rz_carries,0) AS rz_carries, rush_epa, rush_success,
       COALESCE(rush_fp,0) AS rush_fp, COALESCE(rush_xfp,0) AS rush_xfp,
       COALESCE(targets,0) AS targets, COALESCE(receptions,0) AS receptions,
       COALESCE(rec_yards,0) AS rec_yards, COALESCE(rec_tds,0) AS rec_tds,
       COALESCE(t.air_yards,0) AS air_yards, COALESCE(yac,0) AS yac, adot,
       COALESCE(rz_targets,0) AS rz_targets, COALESCE(ez_targets,0) AS ez_targets,
       rec_epa, tgt_success, COALESCE(rec_fp,0) AS rec_fp, COALESCE(rec_xfp,0) AS rec_xfp,
       COALESCE(dropbacks,0) AS dropbacks, COALESCE(sacks_taken,0) AS sacks_taken,
       COALESCE(d.completions,0) AS completions, COALESCE(pass_yards,0) AS pass_yards,
       COALESCE(pass_tds,0) AS pass_tds, COALESCE(ints,0) AS ints,
       pass_epa, db_success, cpoe, COALESCE(pass_fp,0) AS pass_fp, COALESCE(pass_xfp,0) AS pass_xfp
FROM r
FULL OUTER JOIN t ON r.season=t.season AND r.week=t.week AND r.gsis_id=t.gsis_id
FULL OUTER JOIN d ON COALESCE(r.season,t.season)=d.season AND COALESCE(r.week,t.week)=d.week AND COALESCE(r.gsis_id,t.gsis_id)=d.gsis_id
""").format(RUSH_BIN=RUSH_BIN, TGT_BIN=TGT_BIN, DB_BIN=DB_BIN))

con.execute("""
CREATE TABLE fact_player_week_xfp AS
SELECT season, week, gsis_id, team,
       ROUND(rush_fp + rec_fp + pass_fp, 2) AS actual_fp_pbp,
       ROUND(rush_xfp + rec_xfp + pass_xfp, 2) AS xfp,
       ROUND((rush_fp + rec_fp + pass_fp) - (rush_xfp + rec_xfp + pass_xfp), 2) AS fpoe
FROM fact_player_week_opp
""")

con.execute("CREATE INDEX ix_fpw ON fact_player_week (gsis_id, season, week)")
con.execute("CREATE INDEX ix_fpwo ON fact_player_week_opp (gsis_id, season, week)")

# ---- reconciliation: pbp fp vs official-stats fp (independent paths) ---------
recon = con.execute("""
SELECT COUNT(*) AS n,
       ROUND(AVG(ABS(x.actual_fp_pbp - w.std_fp)), 3) AS mean_abs_diff,
       ROUND(SUM(CASE WHEN ABS(x.actual_fp_pbp - w.std_fp) <= 1.0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS pct_within_1,
       ROUND(MAX(ABS(x.actual_fp_pbp - w.std_fp)), 1) AS worst
FROM fact_player_week_xfp x
JOIN fact_player_week w USING (gsis_id, season, week)
WHERE w.position IN ('QB','RB','WR','TE')
""").fetchdf().to_dict("records")[0]

counts = {}
for t in ("dim_nfl_player", "fact_player_week", "fact_player_week_opp", "fact_player_week_xfp", "stg_pbp"):
    counts[t] = con.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]

REPORTS.mkdir(parents=True, exist_ok=True)
report = {"counts": counts, "fp_reconciliation_pbp_vs_official": recon}
json.dump(report, open(REPORTS / "nfl_build_report.json", "w"), indent=2, default=str)
print(json.dumps(report, indent=2, default=str))
con.close()
