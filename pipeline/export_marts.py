#!/usr/bin/env python3
"""AFFL Savant — compute derived metrics and export site marts (minified JSON).

Outputs:
  data/marts/savant_data.json    artifact A payload (hub/franchises/players/...)
  data/marts/explore_data.json   artifact B payload (custody x NFL weekly rows)
  data/reports/marts_report.json sizes + validation summary

Metric versions:
  par_v1    Replacement PPG per season x position = AFFL PPG of the rank-R
            player by season AFFL points among players rostered >=4 weeks;
            R = teams * dedicated starter slots + flex allocation
            (RB +0.5/team, WR +0.4/team, TE +0.1/team). PAR = custody points
            - replacement_ppg * rostered_weeks (started-week points for
            pre-2018 where bench custody is unobservable).
            NOTE: PAR and trade alpha are AFFL-custody-points based and do
            not depend on any xFP version.
  trade_v1  Trade window = execution week through end of that season.
            Realized value = AFFL points while rostered by the receiving
            franchise inside the window. Alpha = received - sent.
  xfp_v2    Canon expected FP (ffopportunity CP+xYAC, AFFL-rescored) from
            fact_player_week_xfp2 (see build_xfp2.py). Same-scope actual
            afp2; fpoe2 = afp2 - xfp2. No fumble/kicking/ST term either side.
  adjfac_v1 Opponent factor per (season, week, defteam, position) on the
            afp2 scope: leave-one-week-out defense PG vs league PG, shrunk
            toward 1 by (g-1)/((g-1)+4). Season aFPOE = sum over weeks of
            afp2 - xfp2 * factor(opponent). Unmatched weeks factor = 1.
Privacy: no SWIDs, no member ids, no credentials in any mart.
"""
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
MARTS = ROOT / "data" / "marts"
REPORTS = ROOT / "data" / "reports"
MARTS.mkdir(parents=True, exist_ok=True)

ax = sqlite3.connect(str(ROOT / "data" / "affl.db"))
ax.row_factory = sqlite3.Row
con = duckdb.connect(str(ROOT / "data" / "nfl.duckdb"))

POS = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "D/ST"}
DATA_VERSION = "2026.08.30.2"


def r1(x):
    return None if x is None or x != x else round(float(x), 1)


def r2(x):
    return None if x is None or x != x else round(float(x), 2)


def num(x):
    """NaN/None-safe numeric: returns float or None."""
    return None if x is None or x != x else float(x)


# ---------------------------------------------------------------- dims -------
franchises = [dict(r) for r in ax.execute(
    "SELECT franchise_id, display_name, code, glyph, logo_url, owner_names_json,"
    " first_season, last_season, seasons_active_json, aliases_json, is_active_2026"
    " FROM dim_franchise ORDER BY first_season, franchise_id")]
for f in franchises:
    f["owners"] = json.loads(f.pop("owner_names_json"))
    f["seasons"] = json.loads(f.pop("seasons_active_json"))
    f["aliases"] = json.loads(f.pop("aliases_json"))

seasons = {}
for r in ax.execute("SELECT * FROM dim_season"):
    seasons[r["season"]] = {
        "teams": [], "complete": bool(r["complete"]), "auction": bool(r["is_auction"]),
        "regWeeks": r["regular_season_matchup_count"], "playoffTeams": r["playoff_team_count"],
        "finalSp": r["final_scoring_period"], "leagueName": r["name"],
    }
for r in ax.execute("SELECT * FROM dim_team_season ORDER BY season, team_id"):
    seasons[r["season"]]["teams"].append({
        "tid": r["team_id"], "fid": r["franchise_id"], "name": r["name"],
        "abbrev": r["abbrev"], "logo": r["logo_url"], "w": r["wins"], "l": r["losses"],
        "t": r["ties"], "pf": r1(r["points_for"]), "pa": r1(r["points_against"]),
        "seed": r["playoff_seed"], "finalRank": r["final_rank"], "div": r["division_id"],
    })

fid_by_st = {}
name_by_st = {}
for s, sd in seasons.items():
    for t in sd["teams"]:
        fid_by_st[(s, t["tid"])] = t["fid"]
        name_by_st[(s, t["tid"])] = t["name"]

matchups = [dict(r) for r in ax.execute(
    "SELECT season, matchup_id AS mid, matchup_period AS mp, home_team_id AS h,"
    " away_team_id AS a, home_score AS hs, away_score AS as_, winner,"
    " playoff_tier AS tier, is_playoff AS po, is_bye AS bye FROM fact_matchup"
    " ORDER BY season, matchup_id")]

# ------------------------------------------------------------- custody -------
cust = con.execute("""
SELECT b.season, b.week, b.franchise_id, b.team_id, b.espn_player_id,
       b.gsis_id, b.dst_team, b.started, b.lineup_slot_id, b.slot_evidence,
       b.affl_points, b.acquisition_type, b.source
FROM bridge_affl_player_week b ORDER BY b.season, b.week
""").fetchdf()

players_dim = {r["espn_player_id"]: dict(r) for r in ax.execute(
    "SELECT espn_player_id, full_name, default_position_id, pro_team_id, is_dst"
    " FROM dim_player_espn")}

nfl_meta = {r[0]: {"headshot": r[1], "college": r[2], "rookie": r[3], "team": r[4], "pos": r[5]}
            for r in con.execute(
    "SELECT gsis_id, headshot, college_name, rookie_season, latest_team, position"
    " FROM dim_nfl_player").fetchall()}

# --------------------------------------------------- replacement + PAR -------
# season AFFL points per player (weekly-attributable custody points)
season_pts = defaultdict(lambda: defaultdict(float))
season_weeks = defaultdict(lambda: defaultdict(int))
for row in cust.itertuples():
    v = num(row.affl_points)
    if v is not None:
        season_pts[row.season][row.espn_player_id] += v
    season_weeks[row.season][row.espn_player_id] += 1

FLEX_ALLOC = {"RB": 0.5, "WR": 0.4, "TE": 0.1}
SLOTS = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "K": 1, "D/ST": 1}
replacement = {}
for s, sd in seasons.items():
    if not sd["complete"]:
        continue
    teams_n = len(sd["teams"])
    by_pos = defaultdict(list)
    for eid, pts in season_pts[s].items():
        wk = season_weeks[s][eid]
        if wk < 4:
            continue
        p = players_dim.get(eid)
        pos = POS.get((p or {}).get("default_position_id"), None)
        if pos:
            by_pos[pos].append(pts / wk)
    replacement[s] = {}
    for pos, ppgs in by_pos.items():
        ppgs.sort(reverse=True)
        rank = int(round(teams_n * (SLOTS.get(pos, 0) + FLEX_ALLOC.get(pos, 0.0))))
        rank = max(1, min(rank, len(ppgs)))
        replacement[s][pos] = round(ppgs[rank - 1], 2)

# custody stints per (eid, season, fid): consecutive weeks
cust_sorted = cust.sort_values(["espn_player_id", "season", "week"])
stints = []
cur = None
for row in cust_sorted.itertuples():
    key = (row.espn_player_id, row.season, row.franchise_id)
    if cur is None or cur["key"] != key or row.week > cur["w1"] + 1:
        if cur:
            stints.append(cur)
        cur = {"key": key, "eid": row.espn_player_id, "s": row.season,
               "fid": row.franchise_id, "w0": row.week, "w1": row.week,
               "weeks": 0, "starts": 0, "pts": 0.0, "acq": row.acquisition_type}
    cur["w1"] = row.week
    cur["weeks"] += 1
    cur["starts"] += int(row.started or 0)
    cur["pts"] += num(row.affl_points) or 0.0
if cur:
    stints.append(cur)
for st in stints:
    st.pop("key")
    p = players_dim.get(st["eid"])
    pos = POS.get((p or {}).get("default_position_id"))
    rep = replacement.get(st["s"], {}).get(pos)
    st["pts"] = r1(st["pts"])
    st["par"] = r1(st["pts"] - rep * st["weeks"]) if rep is not None and st["pts"] is not None else None

stints_by_eid = defaultdict(list)
for st in stints:
    stints_by_eid[st["eid"]].append(st)

# ----------------------------------------------------------- drafts ----------
draft_rows = [dict(r) for r in ax.execute(
    "SELECT season, overall_pick, round_id, round_pick, team_id, espn_player_id,"
    " bid_amount, keeper FROM fact_draft_pick ORDER BY season, overall_pick")]
drafts = []
for d in draft_rows:
    s, eid = d["season"], d["espn_player_id"]
    fid = fid_by_st.get((s, d["team_id"]))
    my_stints = [st for st in stints_by_eid.get(eid, []) if st["s"] == s and st["fid"] == fid]
    weeks = sum(st["weeks"] for st in my_stints)
    starts = sum(st["starts"] for st in my_stints)
    pts = round(sum(st["pts"] or 0 for st in my_stints), 1)
    p = players_dim.get(eid) or {}
    pos = POS.get(p.get("default_position_id"))
    rep = replacement.get(s, {}).get(pos)
    par = r1(pts - rep * weeks) if rep is not None else None
    drafts.append({"s": s, "pick": d["overall_pick"], "rd": d["round_id"],
                   "fid": fid, "eid": eid, "bid": d["bid_amount"],
                   "keeper": d["keeper"], "weeks": weeks, "starts": starts,
                   "pts": pts, "par": par})

# ----------------------------------------------------------- trades ----------
# Consummation events (TRADE_UPHOLD / TRADE_ACCEPT) carry relatedTransactionId
# pointing at the item-bearing TRADE_PROPOSAL. Each candidate is then validated
# against observed custody movement (trade_v1).
consummations = [dict(r) for r in ax.execute("""
  SELECT season, tx_id, type, status, scoring_period, process_date,
         proposed_date, related_tx_id
  FROM fact_transaction
  WHERE (type = 'TRADE_UPHOLD' AND status = 'EXECUTED')
     OR (type = 'TRADE_ACCEPT' AND (status IS NULL OR status = 'EXECUTED'))
  ORDER BY season, COALESCE(process_date, proposed_date)""")]
vetoed = set((r["season"], r["related_tx_id"]) for r in ax.execute(
    "SELECT season, related_tx_id FROM fact_transaction"
    " WHERE type = 'TRADE_VETO' AND status = 'EXECUTED' AND related_tx_id IS NOT NULL"))
proposal_items = defaultdict(list)
for r in ax.execute("SELECT season, tx_id, espn_player_id, item_type, from_team_id,"
                    " to_team_id FROM fact_transaction_item WHERE item_type='TRADE'"):
    proposal_items[(r["season"], r["tx_id"])].append(dict(r))

cust_idx = defaultdict(float)
cust_member = set()
for row in cust.itertuples():
    v = num(row.affl_points)
    if v is not None:
        cust_idx[(row.season, row.espn_player_id, row.franchise_id, row.week)] = v
    cust_member.add((row.season, int(row.espn_player_id), row.franchise_id, int(row.week)))

# custody moves 2018+: (season, eid, arrival_week, from_fid, to_fid)
cust18 = cust[cust.season >= 2018].sort_values(["season", "espn_player_id", "week"])
moves = []
prev = {}
for row in cust18.itertuples():
    key = (row.season, int(row.espn_player_id))
    p = prev.get(key)
    if p is not None and p[1] != row.franchise_id and row.week == p[0] + 1:
        moves.append({"s": row.season, "eid": int(row.espn_player_id),
                      "wk": int(row.week), "frm": p[1], "to": row.franchise_id})
    prev[key] = (int(row.week), row.franchise_id)

# executed pickup transactions explain waiver/FA arrivals
add_tx = set()
for r in ax.execute("""
  SELECT t.season, i.espn_player_id, t.scoring_period, i.to_team_id
  FROM fact_transaction t
  JOIN fact_transaction_item i ON i.season=t.season AND i.tx_id=t.tx_id AND i.item_type='ADD'
  WHERE t.type IN ('FREEAGENT','WAIVER') AND t.status='EXECUTED'"""):
    fid = fid_by_st.get((r[0], r[3]))
    for w in (r[2], (r[2] or 0) + 1):
        add_tx.add((r[0], r[1], w, fid))

unexplained = [m for m in moves
               if (m["s"], m["eid"], m["wk"], m["to"]) not in add_tx
               and (m["s"], m["eid"], m["wk"] - 1, m["to"]) not in add_tx]

# distinct executed trade events, deduped by related proposal id
events = {}
for t in consummations:
    s, rel = t["season"], t["related_tx_id"]
    if not rel:
        continue
    k = (s, rel)
    if (k in vetoed) and t["type"] != "TRADE_UPHOLD":
        continue
    cur = events.get(k)
    if cur is None or (t["type"] == "TRADE_ACCEPT" and cur["type"] != "TRADE_ACCEPT"):
        events[k] = {"s": s, "rel": rel, "type": t["type"],
                     "sp": t["scoring_period"] or 0,
                     "date": t["process_date"] or t["proposed_date"],
                     "team_id": None if t["type"] == "TRADE_UPHOLD" else None}
# accepting team ids for anchor franchises
accept_team = {}
for r in ax.execute("""SELECT season, related_tx_id, team_id FROM fact_transaction
    WHERE type='TRADE_ACCEPT' AND related_tx_id IS NOT NULL"""):
    accept_team[(r[0], r[1])] = r[2]

assigned = set()
trades = []
trade_validation = {"events": len(events), "items_direct": 0, "items_inferred": 0,
                    "unresolved": 0, "custody_confirmed": 0}
for k, ev in sorted(events.items(), key=lambda kv: (kv[1]["s"], kv[1]["sp"])):
    s, sp = ev["s"], ev["sp"]
    final_sp = seasons[s]["finalSp"] or 17
    sides = defaultdict(list)
    method = None
    items = proposal_items.get((s, ev["rel"]), [])
    self_items = proposal_items.get((s, k[1]), [])
    if items or self_items:
        for it in (items or self_items):
            to_fid = fid_by_st.get((s, it["to_team_id"]))
            sides[to_fid].append(it["espn_player_id"])
        method = "direct"
    else:
        anchor_tid = accept_team.get(k)
        anchor_fid = fid_by_st.get((s, anchor_tid)) if anchor_tid else None
        window = [m for m in unexplained if m["s"] == s and sp <= m["wk"] <= sp + 2
                  and id(m) not in assigned]
        cand = [m for m in window if anchor_fid in (m["frm"], m["to"])] if anchor_fid else window
        if cand:
            partners = defaultdict(int)
            for m in cand:
                other = m["to"] if m["frm"] == anchor_fid else m["frm"]
                partners[other] += 1
            partner = max(partners, key=partners.get) if partners else None
            pair = {anchor_fid, partner}
            picked = [m for m in cand if {m["frm"], m["to"]} == pair]
            for m in picked:
                sides[m["to"]].append(m["eid"])
                assigned.add(id(m))
            if picked:
                method = "custody_inferred"
    if not sides:
        trade_validation["unresolved"] += 1
        continue
    trade_validation["items_direct" if method == "direct" else "items_inferred"] += 1
    # custody confirmation
    moved = 0
    for fid, eids in sides.items():
        for eid in eids:
            if any((s, eid, fid, w) in cust_member for w in range(sp, min(sp + 4, final_sp + 1))):
                moved += 1
    if moved:
        trade_validation["custody_confirmed"] += 1
    outcome = {}
    for fid, eids in sides.items():
        got = 0.0
        for eid in eids:
            for w in range(sp, final_sp + 1):
                got += cust_idx.get((s, eid, fid, w), 0.0)
        outcome[fid] = round(got, 1)
    fids = list(sides.keys())
    alpha = {}
    if len(fids) == 2:
        alpha = {fids[0]: round(outcome[fids[0]] - outcome[fids[1]], 1),
                 fids[1]: round(outcome[fids[1]] - outcome[fids[0]], 1)}
    trades.append({"s": s, "id": k[1], "week": sp,
                   "date": ev["date"], "method": method,
                   "sides": {str(kk): v for kk, v in sides.items()},
                   "recv": outcome, "alpha": alpha})

# ------------------------------------------------- franchise aggregates ------
frec = {f["franchise_id"]: {"w": 0, "l": 0, "t": 0, "pf": 0.0, "pa": 0.0,
                            "pw": 0, "pl": 0, "titles": [], "seasonsPlayed": 0,
                            "bestFinish": None} for f in franchises}
h2h = defaultdict(lambda: {"w": 0, "l": 0, "t": 0, "pf": 0.0, "pa": 0.0})
for m in matchups:
    if m["bye"] or m["hs"] is None or m["winner"] in (None, "UNDECIDED"):
        continue
    s = m["season"]
    hf, af = fid_by_st.get((s, m["h"])), fid_by_st.get((s, m["a"]))
    if not hf or not af:
        continue
    playoff_real = m["po"] and (m["tier"] in (None, "WINNERS_BRACKET"))
    consolation = m["po"] and m["tier"] not in (None, "WINNERS_BRACKET")
    for me, opp, my_s, op_s, side in ((hf, af, m["hs"], m["as_"], "HOME"),
                                      (af, hf, m["as_"], m["hs"], "AWAY")):
        won = m["winner"] == side
        tie = m["winner"] == "TIE"
        if consolation:
            continue
        if m["po"]:
            if playoff_real:
                frec[me]["pw" if won else "pl"] += int(not tie)
        else:
            frec[me]["w" if won else ("t" if tie else "l")] += 1
            frec[me]["pf"] += my_s or 0
            frec[me]["pa"] += op_s or 0
            k = (me, opp)
            h2h[k]["w" if won else ("t" if tie else "l")] += int(1)
            h2h[k]["pf"] += my_s or 0
            h2h[k]["pa"] += op_s or 0

for s, sd in seasons.items():
    if not sd["complete"]:
        continue
    for t in sd["teams"]:
        fr = frec.get(t["fid"])
        if fr is None:
            continue
        fr["seasonsPlayed"] += 1
        if t["finalRank"] == 1:
            fr["titles"].append(s)
        if t["finalRank"] and (fr["bestFinish"] is None or t["finalRank"] < fr["bestFinish"]):
            fr["bestFinish"] = t["finalRank"]

for f in franchises:
    f.update(frec[f["franchise_id"]])
    f["pf"] = r1(f["pf"])
    f["pa"] = r1(f["pa"])

# --------------------------------------------- opponent factors (adjfac_v1) --
# LOO defense-vs-position factor on afp2 scope; adjusted season FPOE per player.
con.execute("""
CREATE OR REPLACE TEMP VIEW v_opp_factor AS
SELECT dw.season, dw.week, dw.defteam, dw.position,
       1 + (((d.afp2_tot - dw.afp2_allowed) / (d.g - 1)) / (d.lg_afp2_tot / d.lg_g) - 1)
           * ((d.g - 1.0) / ((d.g - 1.0) + 4.0)) AS fac
FROM fact_def_pos_week dw
JOIN fact_def_pos_season d USING (season, defteam, position)
WHERE d.g > 1
""")

# --------------------------------------------------------- player mart -------
pw_nfl = con.execute("""
SELECT w.gsis_id, w.season, COUNT(*) AS g, SUM(w.std_fp) AS fp,
       SUM(w.passing_yards) AS pyd, SUM(w.passing_tds) AS ptd, SUM(w.passing_interceptions) AS pint,
       SUM(w.carries) AS car, SUM(w.rushing_yards) AS ryd, SUM(w.rushing_tds) AS rtd,
       SUM(w.targets) AS tgt, SUM(w.receptions) AS rec, SUM(w.receiving_yards) AS recyd,
       SUM(w.receiving_tds) AS rectd, ANY_VALUE(w.team) AS team,
       SUM(x.xfp) AS xfp, SUM(x.fpoe) AS fpoe,
       SUM(x2.xfp2) AS xfp2, SUM(x2.fpoe2) AS fpoe2
FROM fact_player_week w
LEFT JOIN fact_player_week_xfp x USING (gsis_id, season, week)
LEFT JOIN fact_player_week_xfp2 x2 USING (gsis_id, season, week)
GROUP BY 1, 2
""").fetchall()
nfl_seasons_by_gsis = defaultdict(list)
for r in pw_nfl:
    nfl_seasons_by_gsis[r[0]].append({
        "s": r[1], "g": r[2], "fp": r1(r[3]), "pyd": r[4], "ptd": r[5], "pint": r[6],
        "car": r[7], "ryd": r[8], "rtd": r[9], "tgt": r[10], "rec": r[11],
        "recyd": r[12], "rectd": r[13], "tm": r[14], "xfp": r1(r[15]), "fpoe": r1(r[16]),
        "xfp2": r1(r[17]), "fpoe2": r1(r[18])})

bridge_rows = {r[0]: r[1] for r in con.execute(
    "SELECT espn_player_id, gsis_id FROM bridge_player_external WHERE ever_rostered=1").fetchall()}

players_mart = []
for eid, gsis in bridge_rows.items():
    p = players_dim.get(eid) or {}
    meta = nfl_meta.get(gsis, {}) if gsis else {}
    sts = sorted(stints_by_eid.get(eid, []), key=lambda x: (x["s"], x["w0"]))
    total_pts = round(sum(x["pts"] or 0 for x in sts), 1)
    players_mart.append({
        "eid": eid, "gsis": gsis, "name": p.get("full_name"),
        "pos": POS.get(p.get("default_position_id")),
        "dst": bool(p.get("is_dst")),
        "img": meta.get("headshot"), "college": meta.get("college"),
        "rookie": meta.get("rookie"), "team": meta.get("team"),
        "stints": [{k: v for k, v in st.items() if k != "eid"} for st in sts],
        "afflPts": total_pts,
        "nfl": sorted([x for x in nfl_seasons_by_gsis.get(gsis, []) if 2014 <= x["s"] <= 2025],
                      key=lambda x: x["s"]) if gsis else [],
    })
# draft-only identities: drafted (or traded) players who never appear in any
# held snapshot — mostly 2014-2017 drafted-then-cut players whose names ESPN's
# historical rosters omit. Names come from the public athlete API patch
# (fetch_athlete_names.py); display data only, zero custody, no joins.
patch_path = ROOT / "data" / "raw" / "athlete_names_patch.json"
name_patch = json.load(open(patch_path)) if patch_path.exists() else {}
known_eids = {p["eid"] for p in players_mart}
draft_eids = {d["espn_player_id"] for d in draft_rows}
patched = 0
for eid in sorted(draft_eids - known_eids):
    entry = name_patch.get(str(eid))
    players_mart.append({
        "eid": eid, "gsis": None,
        "name": (entry or {}).get("name") or ("ESPN id %d" % eid),
        "pos": (entry or {}).get("pos"),
        "dst": False, "img": None, "college": None, "rookie": None, "team": None,
        "stints": [], "afflPts": 0.0, "nfl": [], "draftOnly": True,
    })
    patched += 1
players_mart.sort(key=lambda x: -(x["afflPts"] or 0))

# --------------------------------------------------------- records -----------
# Regular-season-only record book (see records_scope.py for the audit rationale:
# consolation blowouts, two-week playoff totals, and 2022 commissioner
# adjustments all polluted the unscoped version).
from records_scope import build_records
records = build_records(ax, fid_by_st, matchups)

# --------------------------------------------------------- coverage ----------
coverage = [dict(r) for r in ax.execute(
    "SELECT season, COUNT(*) AS team_weeks, SUM(CASE WHEN unattributed_points > 0.6 THEN 1 ELSE 0 END) AS gaps,"
    " ROUND(SUM(CASE WHEN unattributed_points > 0 THEN unattributed_points ELSE 0 END),1) AS unattributed"
    " FROM fact_week_coverage GROUP BY season ORDER BY season")]

savant = {
    "meta": {"version": DATA_VERSION, "league": "AFFL", "leagueId": "51418",
             "seasons": "2014-2025 complete; 2026 pre-draft planning",
             "scoring": "ESPN standard non-PPR"},
    "franchises": franchises, "seasons": seasons, "matchups": matchups,
    "h2h": {"%s|%s" % k: v for k, v in h2h.items()},
    "players": players_mart, "drafts": drafts, "trades": trades,
    "records": records, "replacement": replacement, "coverage": coverage,
}

# --------------------------------------------------------- explore mart ------
opp = con.execute("""
SELECT b.season, b.week, b.franchise_id, b.espn_player_id, b.started,
       b.lineup_slot_id, b.slot_evidence, b.affl_points,
       w.team, w.opponent, w.std_fp,
       o.targets, o.receptions, o.rec_yards, o.rec_tds, o.air_yards, o.yac,
       o.adot, o.rz_targets, o.ez_targets, o.rec_epa,
       o.carries, o.rush_yards, o.rush_tds, o.gl_carries, o.rz_carries, o.rush_epa,
       o.dropbacks, o.pass_yards, o.pass_tds, o.ints, o.sacks_taken, o.pass_epa, o.cpoe,
       x.xfp, x.fpoe,
       w.target_share, w.air_yards_share, w.wopr,
       x2.xfp2, x2.fpoe2
FROM bridge_affl_player_week b
LEFT JOIN fact_player_week w ON w.gsis_id = b.gsis_id AND w.season = b.season AND w.week = b.week
LEFT JOIN fact_player_week_opp o ON o.gsis_id = b.gsis_id AND o.season = b.season AND o.week = b.week
LEFT JOIN fact_player_week_xfp x ON x.gsis_id = b.gsis_id AND x.season = b.season AND x.week = b.week
LEFT JOIN fact_player_week_xfp2 x2 ON x2.gsis_id = b.gsis_id AND x2.season = b.season AND x2.week = b.week
ORDER BY b.season, b.week
""").fetchdf()

fid_list = [f["franchise_id"] for f in franchises]
fid_idx = {fid: i for i, fid in enumerate(fid_list)}
eids = sorted(set(int(x) for x in opp.espn_player_id))
eid_idx = {e: i for i, e in enumerate(eids)}

explore_players = []
for e in eids:
    p = players_dim.get(e) or {}
    g = bridge_rows.get(e)
    meta = nfl_meta.get(g, {}) if g else {}
    explore_players.append([e, p.get("full_name"), POS.get(p.get("default_position_id")),
                            1 if p.get("is_dst") else 0, meta.get("headshot")])

import pandas as pd


def miss(v):
    try:
        return v is None or pd.isna(v)
    except (TypeError, ValueError):
        return False


def as_int(v):
    return None if miss(v) else int(v)


def as_r2(v):
    return None if miss(v) else round(float(v), 2)


def as_str(v):
    return v if isinstance(v, str) else None


cols = ["s", "w", "f", "p", "st", "slot", "affl", "tm", "opp", "fp",
        "tgt", "rec", "recyd", "rectd", "air", "yac", "adot", "rztgt", "eztgt", "recepa",
        "car", "ryd", "rtd", "gl", "rzc", "repa",
        "db", "pyd", "ptd", "int", "sk", "pepa", "cpoe",
        "xfp", "fpoe", "tshare", "ashare", "wopr", "ev",
        "xfp2", "fpoe2"]
rows = []
for r in opp.itertuples():
    rows.append([
        int(r.season), int(r.week), fid_idx[r.franchise_id], eid_idx[int(r.espn_player_id)],
        int(r.started or 0), as_int(r.lineup_slot_id), as_r2(r.affl_points),
        as_str(r.team), as_str(r.opponent), as_r2(r.std_fp),
        as_int(r.targets), as_int(r.receptions), as_int(r.rec_yards), as_int(r.rec_tds),
        as_int(r.air_yards), as_int(r.yac), as_r2(r.adot), as_int(r.rz_targets),
        as_int(r.ez_targets), as_r2(r.rec_epa),
        as_int(r.carries), as_int(r.rush_yards), as_int(r.rush_tds), as_int(r.gl_carries),
        as_int(r.rz_carries), as_r2(r.rush_epa),
        as_int(r.dropbacks), as_int(r.pass_yards), as_int(r.pass_tds), as_int(r.ints),
        as_int(r.sacks_taken), as_r2(r.pass_epa), as_r2(r.cpoe),
        as_r2(r.xfp), as_r2(r.fpoe),
        as_r2(r.target_share), as_r2(r.air_yards_share), as_r2(r.wopr),
        0 if r.slot_evidence == "Observed" else 1,
        as_r2(r.xfp2), as_r2(r.fpoe2),
    ])

# ---- season-grain NFL rows: NFL-WIDE (all QB/RB/WR/TE/K player-seasons) ------
# Rostered players keep their existing explore_players indices; NFL players
# never rostered in the AFFL are APPENDED (index >= len(eids)) with ro=0.
# Season aFPOE (adjfac_v1) folded in via v_opp_factor; unmatched weeks fac=1.
gsis_to_eid = {g: e for e, g in bridge_rows.items() if g}
season_nfl = con.execute("""
WITH afpoe AS (
  SELECT w.gsis_id, w.season,
         SUM(x2.afp2 - x2.xfp2 * COALESCE(f.fac, 1.0)) AS afpoe2
  FROM fact_player_week w
  JOIN fact_player_week_xfp2 x2 USING (gsis_id, season, week)
  LEFT JOIN v_opp_factor f
    ON f.season = w.season AND f.week = w.week
   AND f.defteam = w.opponent AND f.position = w.position
  WHERE w.position IN ('QB','RB','WR','TE')
  GROUP BY 1, 2
), opp_season AS (
  SELECT gsis_id, season, SUM(dropbacks) AS db,
         SUM(rec_epa) AS recepa, SUM(rush_epa) AS repa, SUM(pass_epa) AS pepa,
         SUM(cpoe * dropbacks) / NULLIF(SUM(dropbacks), 0) AS cpoe,
         SUM(air_yards) AS air, SUM(yac) AS yac,
         SUM(adot * targets) / NULLIF(SUM(targets), 0) AS adot,
         SUM(rz_targets) AS rztgt, SUM(ez_targets) AS eztgt,
         SUM(gl_carries) AS gl, SUM(rz_carries) AS rzc
  FROM fact_player_week_opp GROUP BY 1, 2
), usage_season AS (
  SELECT gsis_id, season,
         AVG(target_share) AS tshare, AVG(air_yards_share) AS ashare, AVG(wopr) AS wopr
  FROM fact_player_week GROUP BY 1, 2
)
SELECT w.gsis_id, ANY_VALUE(w.name) AS name, ANY_VALUE(w.position) AS position,
       w.season, COUNT(*) AS g, SUM(w.std_fp) AS fp,
       SUM(w.passing_yards) AS pyd, SUM(w.passing_tds) AS ptd, SUM(w.passing_interceptions) AS pint,
       SUM(w.carries) AS car, SUM(w.rushing_yards) AS ryd, SUM(w.rushing_tds) AS rtd,
       SUM(w.targets) AS tgt, SUM(w.receptions) AS rec, SUM(w.receiving_yards) AS recyd,
       SUM(w.receiving_tds) AS rectd, ANY_VALUE(w.team) AS team,
       SUM(x.xfp) AS xfp, SUM(x.fpoe) AS fpoe,
       SUM(x2.xfp2) AS xfp2, SUM(x2.fpoe2) AS fpoe2,
       ANY_VALUE(a.afpoe2) AS afpoe2,
       ANY_VALUE(o.db) AS db,
       ANY_VALUE(o.recepa) AS recepa, ANY_VALUE(o.repa) AS repa, ANY_VALUE(o.pepa) AS pepa,
       ANY_VALUE(o.cpoe) AS cpoe, ANY_VALUE(o.air) AS air, ANY_VALUE(o.yac) AS yac,
       ANY_VALUE(o.adot) AS adot, ANY_VALUE(o.rztgt) AS rztgt, ANY_VALUE(o.eztgt) AS eztgt,
       ANY_VALUE(o.gl) AS gl, ANY_VALUE(o.rzc) AS rzc,
       ANY_VALUE(u.tshare) AS tshare, ANY_VALUE(u.ashare) AS ashare, ANY_VALUE(u.wopr) AS wopr
FROM fact_player_week w
LEFT JOIN fact_player_week_xfp x USING (gsis_id, season, week)
LEFT JOIN fact_player_week_xfp2 x2 USING (gsis_id, season, week)
LEFT JOIN afpoe a ON a.gsis_id = w.gsis_id AND a.season = w.season
LEFT JOIN opp_season o ON o.gsis_id = w.gsis_id AND o.season = w.season
LEFT JOIN usage_season u ON u.gsis_id = w.gsis_id AND u.season = w.season
WHERE w.position IN ('QB','RB','WR','TE','K') AND w.gsis_id IS NOT NULL
GROUP BY w.gsis_id, w.season
ORDER BY w.gsis_id, w.season
""").fetchdf()

idx_by_gsis = {}
for e, g in bridge_rows.items():
    if g and e in eid_idx:
        idx_by_gsis[g] = eid_idx[e]
appended = 0
for r in season_nfl.itertuples():
    if r.gsis_id in idx_by_gsis:
        continue
    idx_by_gsis[r.gsis_id] = len(explore_players)
    meta = nfl_meta.get(r.gsis_id, {})
    explore_players.append([None, r.name, r.position, 0, meta.get("headshot")])
    appended += 1
# rostered flag as 6th field (position-stable append; app reads 0-4 by index)
rostered_idx = set(eid_idx.values())
for i, p in enumerate(explore_players):
    p.append(1 if i in rostered_idx else 0)

season_cols = ["p", "s", "g", "fp", "pyd", "ptd", "pint", "car", "ryd", "rtd",
               "tgt", "rec", "recyd", "rectd", "tm", "xfp", "fpoe",
               "xfp2", "fpoe2", "afpoe2", "db", "recepa", "repa", "pepa", "cpoe",
               "air", "yac", "adot", "rztgt", "eztgt", "gl", "rzc",
               "tshare", "ashare", "wopr"]
season_rows = []
for r in season_nfl.itertuples():
    season_rows.append([
        idx_by_gsis[r.gsis_id], int(r.season), as_int(r.g), as_r2(r.fp),
        as_int(r.pyd), as_int(r.ptd), as_int(r.pint), as_int(r.car), as_int(r.ryd),
        as_int(r.rtd), as_int(r.tgt), as_int(r.rec), as_int(r.recyd), as_int(r.rectd),
        as_str(r.team), r1(r.xfp), r1(r.fpoe),
        r1(r.xfp2), r1(r.fpoe2), r1(r.afpoe2), as_int(r.db),
        r1(r.recepa), r1(r.repa), r1(r.pepa), as_r2(r.cpoe),
        as_int(r.air), as_int(r.yac), as_r2(r.adot), as_int(r.rztgt), as_int(r.eztgt),
        as_int(r.gl), as_int(r.rzc),
        as_r2(r.tshare), as_r2(r.ashare), as_r2(r.wopr)])
season_rows.sort(key=lambda x: (x[1], x[0]))

# ---- defense x position boards (display mart) --------------------------------
def_boards = []
for r in con.execute("""
SELECT season, defteam, position, g, std_fp_allowed_pg, afp2_allowed_pg,
       xfp2_allowed_pg, ROUND(afp2_allowed_pg / NULLIF(lg_afp2_pg, 0), 3) AS idx
FROM fact_def_pos_season ORDER BY season, position, defteam""").fetchall():
    def_boards.append([r[0], r[1], r[2], r[3], r2(r[4]), r2(r[5]), r2(r[6]), r[7]])

explore = {
    "meta": {"version": DATA_VERSION, "coverage": "2014-2025",
             "custodyRows": len(rows), "note": "slots pre-2018 unavailable (ev=1)",
             "seasonScope": "all NFL QB/RB/WR/TE/K player-seasons 2014-2025",
             "playersAppendedNfl": appended},
    "franchises": [[f["franchise_id"], f["display_name"], f["code"], f["logo_url"]] for f in franchises],
    "players": explore_players,
    "cols": cols,
    "rows": rows,
    "seasonCols": season_cols,
    "seasonRows": season_rows,
    "defBoardCols": ["s", "def", "pos", "g", "stdpg", "afp2pg", "xfp2pg", "idx"],
    "defBoards": def_boards,
    "replacement": replacement,
}


def dump(obj, path):
    with open(path, "w") as f:
        json.dump(obj, f, separators=(",", ":"), ensure_ascii=False, default=str)
    return Path(path).stat().st_size


s1 = dump(savant, MARTS / "savant_data.json")
s2 = dump(explore, MARTS / "explore_data.json")
report = {
    "savant_bytes": s1, "explore_bytes": s2,
    "players": len(players_mart), "stints": len(stints), "drafts": len(drafts),
    "players_draft_only_patched": patched,
    "trades": len(trades), "explore_rows": len(rows), "season_rows": len(season_rows),
    "season_players_appended_nfl": appended, "def_board_rows": len(def_boards),
    "trade_count_check": len(trades),
    "trade_validation": trade_validation,
}
json.dump(report, open(REPORTS / "marts_report.json", "w"), indent=2)
print(json.dumps(report, indent=2))
