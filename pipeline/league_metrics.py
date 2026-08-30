#!/usr/bin/env python3
"""AFFL Savant - luck/skill decomposition and lineup efficiency (affl.db only).

Computes the standard fantasy league-history metrics that the nflverse/ffverse
community treats as the defensible way to separate skill from schedule luck.
Reads ONLY data/affl.db (no nflverse dependency) and writes
data/marts/luck_data.json for merge into the site payload.

Metric versions
---------------
allplay_v1   For each regular-season (season, week), every team's score is
             ranked against every other team playing that week. all-play W/L/T
             = teams scored-below / scored-above / tied. Expected wins =
             allplay_win_pct * games_played. This is the ffscrapr::ff_standings
             `allplay_wins` construction. Luck = actual wins - expected wins:
             positive means the schedule handed a team wins its scoring did not
             earn. Consolation-bracket games are excluded; regular season only.

median_v1    Weekly result vs the league median score that week (a win against
             the median = a schedule-independent win). Ties at the median are
             recorded as ties.

lineup_v1    Optimal lineup = the highest-scoring legal lineup available from
             the players actually rostered that week. Slot eligibility: QB(0),
             RB(2), WR(4), TE(6), D/ST(16), K(17) accept only their position;
             FLEX(23) accepts RB/WR/TE. IR(21) is NOT startable and is excluded
             from the candidate pool. Because FLEX is the only multi-eligible
             slot, filling dedicated slots greedily and giving FLEX the best
             remaining RB/WR/TE is provably optimal. Efficiency = actual
             starter points / optimal points. Points left on bench = optimal -
             actual. 2018+ ONLY: pre-2018 ESPN history carries no lineup slots
             (slot_evidence='Unavailable'), so no counterfactual lineup is
             observable and the metric is withheld rather than guessed.

schedluck_v1 Schedule-luck simulation. Weekly scores are held EXACTLY as played
             and only the pairing of opponents is re-drawn: each trial builds a
             random round-robin over the season's actual weeks and replays the
             real scores through it. This isolates schedule luck with zero
             scoring model - no bootstrap, no distributional assumption. Output
             per team-season: win distribution, median wins, and the share of
             trials making the playoff cut (playoff odds under a random
             schedule). Also computes the exact swap matrix: each team's record
             if it had played every other team's actual opponent sequence.

stability_v1 Reliability of each metric per the Open Source Football standard:
             split-half correlation (odd vs even weeks within a team-season)
             and year-over-year correlation (team-season t vs t+1 for the same
             franchise). Reported so metrics that are mostly noise are labelled
             as such rather than presented as skill.
"""
import json
import random
import sqlite3
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MARTS = ROOT / "data" / "marts"
REPORTS = ROOT / "data" / "reports"
MARTS.mkdir(parents=True, exist_ok=True)
REPORTS.mkdir(parents=True, exist_ok=True)

DB = ROOT / "data" / "affl.db"
if not DB.exists():
    DB = ROOT / "affl.db"

ax = sqlite3.connect(str(DB))
ax.row_factory = sqlite3.Row

N_TRIALS = 2000
SEED = 20260829
POS = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "D/ST"}
DEDICATED = {0: ("QB",), 2: ("RB",), 4: ("WR",), 6: ("TE",), 16: ("D/ST",), 17: ("K",)}
FLEX_SLOT = 23
FLEX_OK = ("RB", "WR", "TE")
IR_SLOT = 21
BENCH_SLOT = 20


def r1(x):
    return None if x is None else round(float(x), 1)


def r3(x):
    return None if x is None else round(float(x), 3)


# --------------------------------------------------------------- dims --------
seasons = {}
for r in ax.execute("SELECT season, regular_season_matchup_count AS rw, playoff_team_count AS pt,"
                    " complete, team_count FROM dim_season"):
    seasons[r["season"]] = {"regWeeks": r["rw"], "playoffTeams": r["pt"],
                            "complete": bool(r["complete"]), "teams": r["team_count"]}

fid_by_st = {}
for r in ax.execute("SELECT season, team_id, franchise_id FROM dim_team_season"):
    fid_by_st[(r["season"], r["team_id"])] = r["franchise_id"]

player_pos = {}
for r in ax.execute("SELECT espn_player_id, default_position_id FROM dim_player_espn"):
    player_pos[r["espn_player_id"]] = POS.get(r["default_position_id"])

# regular-season matchup periods, and the actual opponent pairing per period
reg_mp = defaultdict(set)
pairs = defaultdict(list)          # (season, mp) -> [(tid_a, tid_b)]
byes = defaultdict(list)
for r in ax.execute("SELECT season, matchup_period AS mp, home_team_id AS h, away_team_id AS a,"
                    " is_playoff, is_bye FROM fact_matchup ORDER BY season, matchup_period"):
    if r["is_playoff"]:
        continue
    reg_mp[r["season"]].add(r["mp"])
    if r["is_bye"] or r["a"] is None:
        byes[(r["season"], r["mp"])].append(r["h"])
    else:
        pairs[(r["season"], r["mp"])].append((r["h"], r["a"]))

# Official ESPN outcomes per regular-season pairing (2026-08-30 audit fix).
# ESPN's tiebreaker settles equal-score games — the AFFL has four (2014 MP3,
# 2015 MP11, 2016 MP11, 2018 MP5), all officially decided, all to the away
# side — so the official winner is NOT always derivable from the scores.
# Actual records, streaks, big-loss/small-win extremes, and ELO follow the
# official ledger below; the counterfactual layers (all-play, median,
# schedule sim, swap matrix) stay score-based, because a game that was never
# actually paired has no tiebreaker.
official = {}
for r in ax.execute("SELECT season, matchup_period AS mp, home_team_id AS h,"
                    " away_team_id AS a, winner FROM fact_matchup"
                    " WHERE is_playoff = 0 AND is_bye = 0"):
    official[(r["season"], r["mp"], r["h"], r["a"])] = r["winner"]


def official_res(s, mp, h, a, hv, av):
    """Official result 'HOME'|'AWAY'|'TIE'; score-compare fallback if unset."""
    w = official.get((s, mp, h, a))
    if w in ("HOME", "AWAY", "TIE"):
        return w
    return "TIE" if hv == av else ("HOME" if hv > av else "AWAY")


# team scores by (season, matchup_period). fact_team_week is week-grain; for
# 2014-16 the playoff matchups span two weeks but regular season is 1:1.
score = {}                          # (season, mp, tid) -> points
for r in ax.execute("SELECT season, week, team_id, points FROM fact_team_week"):
    if r["points"] is None:
        continue
    if r["week"] in reg_mp[r["season"]]:
        score[(r["season"], r["week"], r["team_id"])] = float(r["points"])

# ------------------------------------------------- all-play / median ---------
# per team-season accumulators
ts = defaultdict(lambda: {"g": 0, "apw": 0, "apl": 0, "apt": 0, "medw": 0, "medl": 0,
                          "medt": 0, "pf": 0.0, "pa": 0.0, "w": 0, "l": 0, "t": 0,
                          "luckyW": 0, "unluckyL": 0, "oppPf": 0.0, "wkRanks": [],
                          "scores": []})

for (s, mp), plist in sorted(pairs.items()):
    week_scores = {tid: score.get((s, mp, tid)) for pair in plist for tid in pair}
    week_scores = {k: v for k, v in week_scores.items() if v is not None}
    for tid in byes.get((s, mp), []):
        v = score.get((s, mp, tid))
        if v is not None:
            week_scores[tid] = v
    if len(week_scores) < 2:
        continue
    vals = sorted(week_scores.values())
    med = statistics.median(vals)
    n = len(week_scores)
    for tid, v in week_scores.items():
        rec = ts[(s, tid)]
        below = sum(1 for o, ov in week_scores.items() if o != tid and ov < v)
        above = sum(1 for o, ov in week_scores.items() if o != tid and ov > v)
        equal = n - 1 - below - above
        rec["apw"] += below
        rec["apl"] += above
        rec["apt"] += equal
        rec["wkRanks"].append(above + 1)
        rec["scores"].append(v)
        if v > med:
            rec["medw"] += 1
        elif v < med:
            rec["medl"] += 1
        else:
            rec["medt"] += 1
    # actual H2H results for the same games — OFFICIAL outcomes, not score
    # comparison: ESPN's tiebreaker decides equal-score games.
    for (h, a) in plist:
        hv, av = week_scores.get(h), week_scores.get(a)
        if hv is None or av is None:
            continue
        res = official_res(s, mp, h, a, hv, av)
        for me, opp, mv, ov, side in ((h, a, hv, av, "HOME"), (a, h, av, hv, "AWAY")):
            rec = ts[(s, me)]
            rec["g"] += 1
            rec["pf"] += mv
            rec["pa"] += ov
            rec["oppPf"] += ov
            if res == side:
                rec["w"] += 1
                if mv < med:
                    rec["luckyW"] += 1
            elif res == "TIE":
                rec["t"] += 1
            else:
                rec["l"] += 1
                if mv > med:
                    rec["unluckyL"] += 1

team_season = []
for (s, tid), rec in sorted(ts.items()):
    ap_games = rec["apw"] + rec["apl"] + rec["apt"]
    ap_pct = (rec["apw"] + 0.5 * rec["apt"]) / ap_games if ap_games else None
    exp_w = ap_pct * rec["g"] if ap_pct is not None else None
    act_w = rec["w"] + 0.5 * rec["t"]
    team_season.append({
        "s": s, "tid": tid, "fid": fid_by_st.get((s, tid)),
        "g": rec["g"], "w": rec["w"], "l": rec["l"], "t": rec["t"],
        "pf": r1(rec["pf"]), "pa": r1(rec["pa"]),
        "apw": rec["apw"], "apl": rec["apl"], "apt": rec["apt"],
        "apPct": r3(ap_pct), "expW": r1(exp_w),
        "luck": r1(act_w - exp_w) if exp_w is not None else None,
        "medW": rec["medw"], "medL": rec["medl"], "medT": rec["medt"],
        "luckyW": rec["luckyW"], "unluckyL": rec["unluckyL"],
        "oppPf": r1(rec["oppPf"]),
        "sos": r1(rec["oppPf"] / rec["g"]) if rec["g"] else None,
        "ppg": r1(rec["pf"] / rec["g"]) if rec["g"] else None,
        "stdev": r1(statistics.pstdev(rec["scores"])) if len(rec["scores"]) > 1 else None,
        "hi": r1(max(rec["scores"])) if rec["scores"] else None,
        "lo": r1(min(rec["scores"])) if rec["scores"] else None,
    })

# ------------------------------------------------- lineup efficiency --------
roster = defaultdict(list)
for r in ax.execute("SELECT season, week, team_id, espn_player_id, lineup_slot_id,"
                    " started, applied_points, slot_evidence FROM fact_roster_week"
                    " WHERE slot_evidence = 'Observed'"):
    roster[(r["season"], r["week"], r["team_id"])].append(r)


def optimal_lineup(rows):
    """Exact optimum: dedicated slots take their position's best, FLEX takes the
    best remaining RB/WR/TE. Valid because FLEX is the only multi-eligible slot."""
    need = defaultdict(int)
    for rr in rows:
        sl = rr["lineup_slot_id"]
        if sl in DEDICATED:
            need[DEDICATED[sl][0]] += 1
        elif sl == FLEX_SLOT:
            need["FLEX"] += 1
    pool = defaultdict(list)
    for rr in rows:
        if rr["lineup_slot_id"] == IR_SLOT:
            continue
        pos = player_pos.get(rr["espn_player_id"])
        if pos:
            pool[pos].append(float(rr["applied_points"] or 0.0))
    for p in pool:
        pool[p].sort(reverse=True)
    total = 0.0
    used = {p: 0 for p in pool}
    for pos, k in need.items():
        if pos == "FLEX":
            continue
        avail = pool.get(pos, [])
        take = avail[:k]
        total += sum(take)
        used[pos] = len(take)
    for _ in range(need.get("FLEX", 0)):
        best, bp = None, None
        for p in FLEX_OK:
            arr = pool.get(p, [])
            i = used.get(p, 0)
            if i < len(arr) and (best is None or arr[i] > best):
                best, bp = arr[i], p
        if bp is None:
            break
        total += best
        used[bp] += 1
    return total


lineup_ts = defaultdict(lambda: {"wks": 0, "act": 0.0, "opt": 0.0, "perfect": 0})
lineup_weeks = []
for (s, w, tid), rows in sorted(roster.items()):
    if w not in reg_mp[s]:
        continue
    act = sum(float(rr["applied_points"] or 0.0) for rr in rows if rr["started"])
    opt = optimal_lineup(rows)
    if opt <= 0:
        continue
    rec = lineup_ts[(s, tid)]
    rec["wks"] += 1
    rec["act"] += act
    rec["opt"] += opt
    if opt - act < 0.05:
        rec["perfect"] += 1
    lineup_weeks.append({"s": s, "w": w, "fid": fid_by_st.get((s, tid)),
                         "act": r1(act), "opt": r1(opt), "left": r1(opt - act)})

lineup_season = []
for (s, tid), rec in sorted(lineup_ts.items()):
    lineup_season.append({
        "s": s, "tid": tid, "fid": fid_by_st.get((s, tid)), "wks": rec["wks"],
        "act": r1(rec["act"]), "opt": r1(rec["opt"]),
        "left": r1(rec["opt"] - rec["act"]),
        "eff": r3(rec["act"] / rec["opt"]) if rec["opt"] else None,
        "perfect": rec["perfect"],
    })

# ------------------------------------------------- schedule luck sim --------
rng = random.Random(SEED)
sched_sim = []
swap_matrix = []
swap_order = {}
for s, sd in sorted(seasons.items()):
    if not sd["complete"]:
        continue
    mps = sorted(reg_mp[s])
    tids = sorted({tid for mp in mps for pair in pairs[(s, mp)] for tid in pair}
                  | {t for mp in mps for t in byes.get((s, mp), [])})
    wk_scores = {mp: {t: score.get((s, mp, t)) for t in tids} for mp in mps}
    wk_scores = {mp: {t: v for t, v in d.items() if v is not None} for mp, d in wk_scores.items()}
    playoff_cut = sd["playoffTeams"] or 6

    # exact swap matrix: my scores vs each other team's actual opponent sequence
    opp_seq = defaultdict(dict)
    for mp in mps:
        for (h, a) in pairs[(s, mp)]:
            opp_seq[h][mp] = a
            opp_seq[a][mp] = h
    order = [fid_by_st.get((s, t)) for t in tids]
    swap_order[s] = order
    for me in tids:
        row = {"s": s, "fid": fid_by_st.get((s, me)), "tid": me, "u": []}
        for other in tids:
            w = l = t = 0
            for mp in mps:
                mv = wk_scores.get(mp, {}).get(me)
                opp = opp_seq.get(other, {}).get(mp)
                if opp is None or mv is None:
                    continue
                if opp == me:
                    opp = other        # can't play yourself: use schedule owner
                ov = wk_scores.get(mp, {}).get(opp)
                if ov is None:
                    continue
                if mv > ov:
                    w += 1
                elif mv < ov:
                    l += 1
                else:
                    t += 1
            row["u"].append([w, l, t] if t else [w, l])
        swap_matrix.append(row)

    # random round-robin trials with real scores
    wins_dist = {t: [] for t in tids}
    playoff_hits = {t: 0 for t in tids}
    n_teams = len(tids)
    for _ in range(N_TRIALS):
        wins = {t: 0.0 for t in tids}
        for mp in mps:
            avail = [t for t in tids if t in wk_scores.get(mp, {})]
            rng.shuffle(avail)
            for i in range(0, len(avail) - 1, 2):
                a, b = avail[i], avail[i + 1]
                av, bv = wk_scores[mp][a], wk_scores[mp][b]
                if av > bv:
                    wins[a] += 1
                elif bv > av:
                    wins[b] += 1
                else:
                    wins[a] += 0.5
                    wins[b] += 0.5
        for t in tids:
            wins_dist[t].append(wins[t])
        pf_tot = {t: sum(wk_scores.get(mp, {}).get(t, 0) for mp in mps) for t in tids}
        rank = sorted(tids, key=lambda t: (-wins[t], -pf_tot[t]))
        for t in rank[:playoff_cut]:
            playoff_hits[t] += 1
    for t in tids:
        d = sorted(wins_dist[t])
        sched_sim.append({
            "s": s, "tid": t, "fid": fid_by_st.get((s, t)),
            "medW": r1(statistics.median(d)),
            "p10": r1(d[int(0.10 * len(d))]), "p90": r1(d[int(0.90 * len(d))]),
            "minW": r1(d[0]), "maxW": r1(d[-1]),
            "poOdds": r3(playoff_hits[t] / N_TRIALS),
            "trials": N_TRIALS,
        })

# ------------------------------------------------- franchise rollups --------
fr = defaultdict(lambda: {"g": 0, "w": 0, "l": 0, "t": 0, "apw": 0, "apl": 0, "apt": 0,
                          "expW": 0.0, "medW": 0, "medL": 0, "medT": 0,
                          "luckyW": 0, "unluckyL": 0, "seasons": 0})
for r in team_season:
    if not seasons.get(r["s"], {}).get("complete"):
        continue
    f = fr[r["fid"]]
    f["seasons"] += 1
    for k in ("g", "w", "l", "t", "apw", "apl", "apt", "medW", "medL", "medT",
              "luckyW", "unluckyL"):
        f[k] += r[k] or 0
    f["expW"] += r["expW"] or 0
franchise = []
for fid, f in fr.items():
    apg = f["apw"] + f["apl"] + f["apt"]
    franchise.append({
        "fid": fid, "seasons": f["seasons"], "g": f["g"], "w": f["w"], "l": f["l"],
        "t": f["t"], "apw": f["apw"], "apl": f["apl"], "apt": f["apt"],
        "apPct": r3((f["apw"] + 0.5 * f["apt"]) / apg) if apg else None,
        "expW": r1(f["expW"]),
        "luck": r1((f["w"] + 0.5 * f["t"]) - f["expW"]),
        "medW": f["medW"], "medL": f["medL"], "medT": f["medT"],
        "luckyW": f["luckyW"], "unluckyL": f["unluckyL"],
        "winPct": r3((f["w"] + 0.5 * f["t"]) / f["g"]) if f["g"] else None,
    })
franchise.sort(key=lambda x: -(x["apPct"] or 0))

lf = defaultdict(lambda: {"wks": 0, "act": 0.0, "opt": 0.0, "perfect": 0})
for r in lineup_season:
    f = lf[r["fid"]]
    f["wks"] += r["wks"]
    f["act"] += r["act"] or 0
    f["opt"] += r["opt"] or 0
    f["perfect"] += r["perfect"]
lineup_franchise = [{
    "fid": fid, "wks": v["wks"], "act": r1(v["act"]), "opt": r1(v["opt"]),
    "left": r1(v["opt"] - v["act"]), "perfect": v["perfect"],
    "eff": r3(v["act"] / v["opt"]) if v["opt"] else None,
} for fid, v in lf.items()]
lineup_franchise.sort(key=lambda x: -(x["eff"] or 0))


# ------------------------------------------------- stability (OSF) ----------
def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sx = sum((a - mx) ** 2 for a in xs) ** 0.5
    sy = sum((b - my) ** 2 for b in ys) ** 0.5
    if sx == 0 or sy == 0:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / (sx * sy)


# split-half: odd vs even weeks within a team-season
half = defaultdict(lambda: {"odd": [], "even": []})
for (s, mp), plist in sorted(pairs.items()):
    week_scores = {}
    for pair in plist:
        for tid in pair:
            v = score.get((s, mp, tid))
            if v is not None:
                week_scores[tid] = v
    if len(week_scores) < 2:
        continue
    n = len(week_scores)
    for tid, v in week_scores.items():
        below = sum(1 for o, ov in week_scores.items() if o != tid and ov < v)
        equal = sum(1 for o, ov in week_scores.items() if o != tid and ov == v)
        apw = (below + 0.5 * equal) / (n - 1)
        half[(s, tid)]["odd" if mp % 2 else "even"].append((v, apw))

sh_ppg_x, sh_ppg_y, sh_ap_x, sh_ap_y = [], [], [], []
for k, d in half.items():
    if len(d["odd"]) < 4 or len(d["even"]) < 4:
        continue
    sh_ppg_x.append(sum(a for a, _ in d["odd"]) / len(d["odd"]))
    sh_ppg_y.append(sum(a for a, _ in d["even"]) / len(d["even"]))
    sh_ap_x.append(sum(b for _, b in d["odd"]) / len(d["odd"]))
    sh_ap_y.append(sum(b for _, b in d["even"]) / len(d["even"]))

by_fid_season = {(r["fid"], r["s"]): r for r in team_season
                 if seasons.get(r["s"], {}).get("complete")}
lin_by = {(r["fid"], r["s"]): r for r in lineup_season}


def yoy(getter, src):
    xs, ys = [], []
    for (fid, s), row in src.items():
        nxt = src.get((fid, s + 1))
        if nxt is None:
            continue
        a, b = getter(row), getter(nxt)
        if a is not None and b is not None:
            xs.append(a)
            ys.append(b)
    return pearson(xs, ys), len(xs)


def sh_corr(xs, ys):
    r = pearson(xs, ys)
    if r is None:
        return None, 0
    # Spearman-Brown correction to full-season reliability
    return (2 * r / (1 + r)) if r > -1 else None, len(xs)


sh_ppg, n_sh = sh_corr(sh_ppg_x, sh_ppg_y)
sh_ap, _ = sh_corr(sh_ap_x, sh_ap_y)
yoy_ppg, n_ppg = yoy(lambda r: r["ppg"], by_fid_season)
yoy_ap, n_ap = yoy(lambda r: r["apPct"], by_fid_season)
yoy_luck, n_luck = yoy(lambda r: r["luck"], by_fid_season)
yoy_eff, n_eff = yoy(lambda r: r["eff"], lin_by)
yoy_win, n_win = yoy(lambda r: (r["w"] + 0.5 * r["t"]) / r["g"] if r["g"] else None,
                     by_fid_season)

stability = {
    "splitHalf": [
        {"metric": "Points per game", "r": r3(sh_ppg), "n": n_sh,
         "read": "skill" if (sh_ppg or 0) >= 0.5 else "noisy"},
        {"metric": "All-play win %", "r": r3(sh_ap), "n": n_sh,
         "read": "skill" if (sh_ap or 0) >= 0.5 else "noisy"},
    ],
    "yoy": [
        {"metric": "Points per game", "r": r3(yoy_ppg), "n": n_ppg},
        {"metric": "All-play win %", "r": r3(yoy_ap), "n": n_ap},
        {"metric": "Actual win %", "r": r3(yoy_win), "n": n_win},
        {"metric": "Luck (W - expected W)", "r": r3(yoy_luck), "n": n_luck},
        {"metric": "Lineup efficiency", "r": r3(yoy_eff), "n": n_eff},
    ],
    "note": ("Split-half is odd vs even regular-season weeks within a team-season, "
             "Spearman-Brown corrected to full-season length. Year-over-year pairs a "
             "franchise's season t with t+1. A luck metric SHOULD be near zero "
             "year-over-year - that is the evidence it is luck and not a repeatable "
             "skill. Lineup efficiency is 2018+ only."),
}

# ------------------------------------------------- rank heatmap (rankheat_v1)
# Per season: franchise x regular-season week rank of that week's score
# (1 = highest score in the league that week). Byes/missing weeks -> null.
rank_heat = []
for s in sorted(reg_mp):
    mps = sorted(reg_mp[s])
    week_rank = {}                      # (mp, tid) -> rank
    n_by_mp = {}
    for mp in mps:
        week_scores = {}
        for pair in pairs.get((s, mp), []):
            for tid in pair:
                v = score.get((s, mp, tid))
                if v is not None:
                    week_scores[tid] = v
        for tid in byes.get((s, mp), []):
            v = score.get((s, mp, tid))
            if v is not None:
                week_scores[tid] = v
        n_by_mp[mp] = len(week_scores)
        for tid, v in week_scores.items():
            week_rank[(mp, tid)] = 1 + sum(1 for ov in week_scores.values() if ov > v)
    tids = sorted({tid for (mp, tid) in week_rank})
    if not tids:
        continue
    rank_heat.append({
        "s": s, "weeks": mps, "n": [n_by_mp[mp] for mp in mps],
        "teams": [{"fid": fid_by_st.get((s, tid)),
                   "ranks": [week_rank.get((mp, tid)) for mp in mps],
                   "scores": [r1(score.get((s, mp, tid))) for mp in mps]}
                  for tid in tids],
    })

# ------------------------------------------------- streaks (streaks_v1) ------
# Cross-season regular-season H2H streaks per franchise, plus game extremes.
games_by_fid = defaultdict(list)
for (s, mp), plist in sorted(pairs.items()):
    for (h, a) in plist:
        hv, av = score.get((s, mp, h)), score.get((s, mp, a))
        if hv is None or av is None:
            continue
        pair_res = official_res(s, mp, h, a, hv, av)   # official, incl. tiebreaker
        for me, opp, mv, ov, side in ((h, a, hv, av, "HOME"), (a, h, av, hv, "AWAY")):
            fid = fid_by_st.get((s, me))
            ofid = fid_by_st.get((s, opp))
            res = "T" if pair_res == "TIE" else ("W" if pair_res == side else "L")
            games_by_fid[fid].append(
                {"s": s, "w": mp, "res": res, "pts": r1(mv), "opp": r1(ov),
                 "ofid": ofid, "_raw": mv})

all_streaks = []                       # every maximal W or L run, all franchises
streak_by_fid = {}
for fid, gs in games_by_fid.items():
    runs = []
    cur = None
    for g in gs:                        # gs already (season, week) ordered
        if g["res"] == "T":
            if cur:
                runs.append(cur)
            cur = None
            continue
        if cur and cur["res"] == g["res"]:
            cur["len"] += 1
            cur["s1"], cur["w1"] = g["s"], g["w"]
        else:
            if cur:
                runs.append(cur)
            cur = {"fid": fid, "res": g["res"], "len": 1,
                   "s0": g["s"], "w0": g["w"], "s1": g["s"], "w1": g["w"]}
    if cur:
        runs.append(cur)
    all_streaks.extend(runs)
    ws = [r for r in runs if r["res"] == "W"]
    ls = [r for r in runs if r["res"] == "L"]
    live = runs[-1] if runs else None
    streak_by_fid[fid] = {
        "maxW": max(ws, key=lambda r: r["len"]) if ws else None,
        "maxL": max(ls, key=lambda r: r["len"]) if ls else None,
        "live": live,
    }

all_games = [g | {"fid": fid} for fid, gs in games_by_fid.items() for g in gs]
streaks = {
    "topW": sorted([r for r in all_streaks if r["res"] == "W"],
                   key=lambda r: (-r["len"], r["s0"], r["w0"]))[:12],
    "topL": sorted([r for r in all_streaks if r["res"] == "L"],
                   key=lambda r: (-r["len"], r["s0"], r["w0"]))[:12],
    "byFranchise": streak_by_fid,
    "bigLosses": sorted([g for g in all_games if g["res"] == "L"],
                        key=lambda g: (-g["_raw"], g["s"], g["w"], g["fid"]))[:12],
    "smallWins": sorted([g for g in all_games if g["res"] == "W"],
                        key=lambda g: (g["_raw"], g["s"], g["w"], g["fid"]))[:12],
}
for _k in ("bigLosses", "smallWins"):
    streaks[_k] = [{kk: vv for kk, vv in g.items() if kk != "_raw"} for g in streaks[_k]]

# ------------------------------------------------- ELO rating (rating_v1) ----
# Classic ELO over regular-season H2H games in chronological order: start 1500,
# K=24, expected score 1/(1+10^((opp-me)/400)), ties count 0.5. No margin-of-
# victory term (documented choice: keeps the rating a pure W/L market).
# Season-end snapshots per franchise feed the trajectory chart.
ELO_K = 24.0
elo = defaultdict(lambda: 1500.0)
elo_series = defaultdict(list)          # fid -> [{s, r}]
for s in sorted(reg_mp):
    played = set()
    for mp in sorted(reg_mp[s]):
        for (h, a) in pairs.get((s, mp), []):
            hv, av = score.get((s, mp, h)), score.get((s, mp, a))
            if hv is None or av is None:
                continue
            hf, af = fid_by_st.get((s, h)), fid_by_st.get((s, a))
            if not hf or not af:
                continue
            rh, ra = elo[hf], elo[af]
            eh = 1.0 / (1.0 + 10 ** ((ra - rh) / 400.0))
            res = official_res(s, mp, h, a, hv, av)    # official, incl. tiebreaker
            sh = 1.0 if res == "HOME" else (0.0 if res == "AWAY" else 0.5)
            elo[hf] = rh + ELO_K * (sh - eh)
            elo[af] = ra + ELO_K * ((1.0 - sh) - (1.0 - eh))
            played.add(hf)
            played.add(af)
    for fid in sorted(played):                 # sorted: deterministic key order
        elo_series[fid].append({"s": s, "r": round(elo[fid], 1)})

out = {
    "meta": {
        "version": "luck_v1.1", "trials": N_TRIALS, "seed": SEED,
        "lineupCoverage": "2018-2025 (pre-2018 lineup slots unavailable)",
        "scope": "regular season only; consolation and playoff games excluded",
        "results": "official ESPN outcomes (four equal-score games settled by"
                   " ESPN's tiebreaker count as W/L, not ties); counterfactual"
                   " layers (all-play, median, sim, swap) remain score-based",
        "extensions": "rankheat_v1 (weekly score rank), streaks_v1 "
                      "(cross-season regular-season H2H runs), rating_v1 "
                      "(ELO K=24 base 1500, W/L only, season-end snapshots)",
    },
    "teamSeason": team_season,
    "franchise": franchise,
    "lineupSeason": lineup_season,
    "lineupFranchise": lineup_franchise,
    "lineupWeeks": sorted(lineup_weeks, key=lambda x: -(x["left"] or 0))[:40],
    "schedSim": sched_sim,
    "swap": swap_matrix,
    "swapOrder": {str(k): v for k, v in swap_order.items()},
    "stability": stability,
    "rankHeat": rank_heat,
    "streaks": streaks,
    "rating": {fid: series for fid, series in elo_series.items()},
}

with open(MARTS / "luck_data.json", "w") as f:
    json.dump(out, f, separators=(",", ":"), ensure_ascii=False)

report = {
    "bytes": (MARTS / "luck_data.json").stat().st_size,
    "teamSeasons": len(team_season), "franchises": len(franchise),
    "lineupSeasons": len(lineup_season), "schedSimRows": len(sched_sim),
    "swapRows": len(swap_matrix), "trials": N_TRIALS,
    "rankHeatSeasons": len(rank_heat),
    "streakTop": {"W": streaks["topW"][0] if streaks["topW"] else None,
                  "L": streaks["topL"][0] if streaks["topL"] else None},
    "stability": stability,
    "luckExtremes": {
        "luckiest": sorted([r for r in team_season if r["luck"] is not None],
                           key=lambda r: -r["luck"])[:3],
        "unluckiest": sorted([r for r in team_season if r["luck"] is not None],
                             key=lambda r: r["luck"])[:3],
    },
}
json.dump(report, open(REPORTS / "luck_report.json", "w"), indent=2)
print(json.dumps(report, indent=2)[:4000])
