#!/usr/bin/env python3
"""AFFL Savant — build affl.db (canonical league warehouse) from raw ESPN snapshots.

Identity canon (binding):
  - Franchise identity follows OWNERS, never ESPN slot ids. ESPN recycles slots.
  - Owner identity cannot key on SWID (one human, several SWIDs); grouping keys
    on normalized owner display-name overlap, merged with union-find so
    cross-slot moves connect.
  - Team names are stored verbatim (inner whitespace, emoji, profanity intact).

Evidence canon (binding):
  - 2018+  : teams[].roster @ scoringPeriodId is the full weekly roster
             (starters + bench), slots Observed.
  - 2014-17: schedule[].rosterForMatchupPeriod is starter membership only;
             ESPN zero-fills slots -> lineup_slot_id NULL, evidence Unavailable.
  - 2026   : pre-draft planning field only; no facts contribute to history.
"""
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "espn"
DB = ROOT / "data" / "affl.db"
REPORTS = ROOT / "data" / "reports"

BENCH_SLOTS = {20, 21}
MODERN_FROM = 2018
SEASONS = list(range(2014, 2027))
PLAYED = [s for s in SEASONS if s <= 2025]

SLOT_NAMES = {0: "QB", 1: "TQB", 2: "RB", 3: "RB/WR", 4: "WR", 5: "WR/TE", 6: "TE",
              7: "OP", 8: "DT", 9: "DE", 10: "LB", 11: "DL", 12: "CB", 13: "S",
              14: "DB", 15: "DP", 16: "D/ST", 17: "K", 18: "P", 19: "HC",
              20: "BE", 21: "IR", 22: "", 23: "FLEX", 24: "ER", 25: "Rookie"}


def team_name(t):
    name = (t.get("name") or "").strip()
    if name:
        return name
    loc = (t.get("location") or "").strip()
    nick = (t.get("nickname") or "").strip()
    return (loc + " " + nick).strip()


def norm_name(raw):
    return " ".join(raw.split()).lower()


class UnionFind(object):
    def __init__(self, n):
        self.parent = list(range(n))

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def load_season(season):
    p = RAW / str(season) / "league.json"
    return json.load(open(p)) if p.exists() else None


def week_applied(player, week):
    """(actual, projected) appliedTotal for a scoring period from player.stats."""
    actual = None
    projected = None
    for s in player.get("stats") or []:
        if s.get("scoringPeriodId") != week or s.get("statSplitTypeId") != 1:
            continue
        if s.get("statSourceId") == 0:
            actual = s.get("appliedTotal")
        elif s.get("statSourceId") == 1:
            projected = s.get("appliedTotal")
    return actual, projected


def main():
    leagues = {s: load_season(s) for s in SEASONS}
    leagues = {s: lg for s, lg in leagues.items() if lg}

    # ---- owners: SWID -> display name across all seasons -------------------
    member_names = {}
    for lg in leagues.values():
        for m in lg.get("members") or []:
            label = (" ".join(x for x in [m.get("firstName"), m.get("lastName")] if x)).strip() \
                or (m.get("displayName") or "").strip() or m.get("id")
            member_names[m.get("id")] = label

    # ---- union-find franchise grouping over (season, slot) entries ---------
    entries = []
    for season in sorted(leagues):
        lg = leagues[season]
        for t in lg.get("teams") or []:
            swids = t.get("owners") or []
            tokens = sorted(set(norm_name(member_names[s]) for s in swids if s in member_names))
            if not tokens:
                tokens = ["slot-%d-unowned" % t.get("id")]
            entries.append({
                "season": season, "slot": t.get("id"), "name": team_name(t),
                "abbrev": t.get("abbrev"), "logo": t.get("logo"),
                "swids": swids, "tokens": tokens, "team": t,
            })

    uf = UnionFind(len(entries))
    first_by_token = {}
    for i, e in enumerate(entries):
        for tok in e["tokens"]:
            if tok in first_by_token:
                uf.union(first_by_token[tok], i)
            else:
                first_by_token[tok] = i

    groups = defaultdict(list)
    for i in range(len(entries)):
        groups[uf.find(i)].append(entries[i])

    franchises = []
    for group in groups.values():
        group.sort(key=lambda e: e["season"])
        first, last = group[0], group[-1]
        seasons_active = sorted(set(e["season"] for e in group))
        aliases = defaultdict(list)
        for e in group:
            aliases[e["name"]].append(e["season"])
        owner_names = sorted(set(member_names[s] for e in group for s in e["swids"] if s in member_names))
        franchises.append({
            "franchise_id": "f%ds%d" % (first["slot"], first["season"]),
            "display_name": last["name"],
            "glyph": last["abbrev"],
            "logo": last.get("logo"),
            "owner_names": owner_names,
            "swids": sorted(set(s for e in group for s in e["swids"])),
            "first_season": seasons_active[0],
            "last_season": seasons_active[-1],
            "seasons_active": seasons_active,
            "aliases": [{"name": n, "seasons": sorted(set(ss))} for n, ss in
                        sorted(aliases.items(), key=lambda kv: min(kv[1]))],
            "slot_by_season": {e["season"]: e["slot"] for e in group},
        })
    franchises.sort(key=lambda f: (f["first_season"], f["franchise_id"]))

    # unique short codes from current name
    used = set()
    for f in franchises:
        base = "".join(w[0] for w in f["display_name"].split() if w[:1].isalnum()).upper()[:4] \
            or f["display_name"][:3].upper()
        code, n = base, 2
        while code in used:
            code = "%s%d" % (base[:3], n)
            n += 1
        used.add(code)
        f["code"] = code

    resolve = {}
    for f in franchises:
        for season, slot in f["slot_by_season"].items():
            resolve[(season, slot)] = f["franchise_id"]

    # ---- sqlite ------------------------------------------------------------
    DB.parent.mkdir(parents=True, exist_ok=True)
    if DB.exists():
        DB.unlink()
    cx = sqlite3.connect(str(DB))
    cx.executescript("""
    CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE dim_owner (owner_id INTEGER PRIMARY KEY AUTOINCREMENT,
      display_name TEXT UNIQUE, swids_json TEXT);
    CREATE TABLE dim_franchise (franchise_id TEXT PRIMARY KEY, display_name TEXT,
      code TEXT, glyph TEXT, logo_url TEXT, owner_names_json TEXT, swids_json TEXT,
      first_season INTEGER, last_season INTEGER, seasons_active_json TEXT,
      aliases_json TEXT, is_active_2026 INTEGER);
    CREATE TABLE dim_season (season INTEGER PRIMARY KEY, name TEXT, team_count INTEGER,
      drafted INTEGER, complete INTEGER, final_scoring_period INTEGER,
      regular_season_matchup_count INTEGER, playoff_team_count INTEGER,
      is_auction INTEGER, scoring_json TEXT);
    CREATE TABLE dim_team_season (season INTEGER, team_id INTEGER, franchise_id TEXT,
      name TEXT, abbrev TEXT, logo_url TEXT, wins INTEGER, losses INTEGER, ties INTEGER,
      points_for REAL, points_against REAL, playoff_seed INTEGER, final_rank INTEGER,
      division_id INTEGER, PRIMARY KEY (season, team_id));
    CREATE TABLE fact_matchup (season INTEGER, matchup_id INTEGER, matchup_period INTEGER,
      home_team_id INTEGER, away_team_id INTEGER, home_score REAL, away_score REAL,
      winner TEXT, playoff_tier TEXT, is_playoff INTEGER, is_bye INTEGER,
      PRIMARY KEY (season, matchup_id));
    CREATE TABLE fact_team_week (season INTEGER, week INTEGER, team_id INTEGER,
      matchup_id INTEGER, points REAL, PRIMARY KEY (season, week, team_id));
    CREATE TABLE fact_roster_week (season INTEGER, week INTEGER, team_id INTEGER,
      espn_player_id INTEGER, lineup_slot_id INTEGER, started INTEGER,
      applied_points REAL, projected_points REAL, injury_status TEXT,
      acquisition_type TEXT, slot_evidence TEXT, source TEXT,
      PRIMARY KEY (season, week, team_id, espn_player_id));
    CREATE TABLE fact_draft_pick (season INTEGER, overall_pick INTEGER, round_id INTEGER,
      round_pick INTEGER, team_id INTEGER, espn_player_id INTEGER, bid_amount INTEGER,
      keeper INTEGER, nominating_team_id INTEGER, PRIMARY KEY (season, overall_pick));
    CREATE TABLE fact_transaction (season INTEGER, tx_id TEXT, type TEXT, status TEXT,
      execution_type TEXT, scoring_period INTEGER, team_id INTEGER, bid_amount INTEGER,
      proposed_date INTEGER, process_date INTEGER, is_pending INTEGER, member_id TEXT,
      related_tx_id TEXT, PRIMARY KEY (season, tx_id));
    CREATE TABLE fact_transaction_item (season INTEGER, tx_id TEXT, item_idx INTEGER,
      espn_player_id INTEGER, item_type TEXT, from_team_id INTEGER, to_team_id INTEGER,
      is_keeper INTEGER, PRIMARY KEY (season, tx_id, item_idx));
    CREATE TABLE dim_player_espn (espn_player_id INTEGER PRIMARY KEY, full_name TEXT,
      default_position_id INTEGER, pro_team_id INTEGER, is_dst INTEGER,
      first_seen_season INTEGER, last_seen_season INTEGER);
    -- Pre-2018 multi-week playoff matchups: applied points exist only at
    -- matchup grain (ESPN merges the weeks). Never presented as weekly fact.
    CREATE TABLE fact_matchup_player_pre2018 (season INTEGER, matchup_id INTEGER,
      team_id INTEGER, espn_player_id INTEGER, applied_points REAL, weeks_json TEXT,
      PRIMARY KEY (season, matchup_id, team_id, espn_player_id));
    -- Evidence accounting: how much of each team-week's score is attributed to
    -- observed starters. Pre-2018 rosters omit players dropped later in the
    -- season, so some points are legitimately unattributable to a player row.
    CREATE TABLE fact_week_coverage (season INTEGER, week INTEGER, team_id INTEGER,
      observed_starters INTEGER, observed_points REAL, team_points REAL,
      unattributed_points REAL, is_multiweek_matchup INTEGER,
      PRIMARY KEY (season, week, team_id));
    CREATE INDEX ix_rw_player ON fact_roster_week (espn_player_id, season, week);
    CREATE INDEX ix_rw_team ON fact_roster_week (season, team_id, week);
    CREATE INDEX ix_tx_item_player ON fact_transaction_item (espn_player_id);
    """)

    # owners
    for name in sorted(set(member_names.values()), key=str.lower):
        swids = sorted(k for k, v in member_names.items() if v == name)
        cx.execute("INSERT INTO dim_owner (display_name, swids_json) VALUES (?,?)",
                   (name, json.dumps(swids)))

    active_2026 = set()
    lg26 = leagues.get(2026)
    if lg26:
        for t in lg26.get("teams") or []:
            active_2026.add(resolve.get((2026, t.get("id"))))

    for f in franchises:
        cx.execute("INSERT INTO dim_franchise VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
            f["franchise_id"], f["display_name"], f["code"], f["glyph"], f.get("logo"),
            json.dumps(f["owner_names"], ensure_ascii=False), json.dumps(f["swids"]),
            f["first_season"], f["last_season"], json.dumps(f["seasons_active"]),
            json.dumps(f["aliases"], ensure_ascii=False),
            1 if f["franchise_id"] in active_2026 else 0))

    # players registry accumulator
    players = {}

    def see_player(season, player, pid=None):
        pid = pid if pid is not None else player.get("id")
        if pid is None:
            return
        rec = players.get(pid)
        if rec is None:
            rec = {"name": None, "pos": None, "pro": None, "first": season, "last": season}
            players[pid] = rec
        rec["first"] = min(rec["first"], season)
        rec["last"] = max(rec["last"], season)
        if player:
            rec["name"] = player.get("fullName") or rec["name"]
            rec["pos"] = player.get("defaultPositionId") if player.get("defaultPositionId") is not None else rec["pos"]
            rec["pro"] = player.get("proTeamId") if player.get("proTeamId") is not None else rec["pro"]

    recon = {"pre2018": {"ok": 0, "bad": 0, "worst": 0.0},
             "modern": {"ok": 0, "bad": 0, "worst": 0.0}}

    for season in sorted(leagues):
        lg = leagues[season]
        status = lg.get("status") or {}
        settings = lg.get("settings") or {}
        sched_set = settings.get("scheduleSettings") or {}
        drafted = bool((lg.get("draftDetail") or {}).get("drafted"))
        complete = drafted and (status.get("currentMatchupPeriod") or 0) > 1 and season <= 2025
        reg_count = sched_set.get("matchupPeriodCount")
        draft_type = ((settings.get("draftSettings") or {}).get("type") or "").upper()

        cx.execute("INSERT INTO dim_season VALUES (?,?,?,?,?,?,?,?,?,?)", (
            season, (settings.get("name") or "").strip() or None,
            len(lg.get("teams") or []), int(drafted), int(complete),
            status.get("finalScoringPeriod"), reg_count,
            sched_set.get("playoffTeamCount"),
            1 if draft_type == "AUCTION" else 0,
            json.dumps((settings.get("scoringSettings") or {}).get("scoringItems") or [])))

        for t in lg.get("teams") or []:
            rec = ((t.get("record") or {}).get("overall")) or {}
            cx.execute("INSERT INTO dim_team_season VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                season, t.get("id"), resolve.get((season, t.get("id"))),
                team_name(t), t.get("abbrev"), t.get("logo"),
                rec.get("wins"), rec.get("losses"), rec.get("ties"),
                rec.get("pointsFor"), rec.get("pointsAgainst"),
                t.get("playoffSeed"), t.get("rankCalculatedFinal"),
                t.get("divisionId")))

        if not complete:
            continue

        # matchups + team-week points
        for e in lg.get("schedule") or []:
            home, away = e.get("home") or {}, e.get("away") or {}
            is_bye = not home.get("teamId") or not away.get("teamId")
            mp = e.get("matchupPeriodId")
            cx.execute("INSERT INTO fact_matchup VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
                season, e.get("id"), mp, home.get("teamId"), away.get("teamId"),
                home.get("totalPoints"), away.get("totalPoints"), e.get("winner"),
                e.get("playoffTierType"),
                1 if (reg_count and mp and mp > reg_count) else 0, int(is_bye)))
            for side in (home, away):
                tid = side.get("teamId")
                if not tid:
                    continue
                for wk, pts in (side.get("pointsByScoringPeriod") or {}).items():
                    cx.execute("INSERT OR REPLACE INTO fact_team_week VALUES (?,?,?,?,?)",
                               (season, int(wk), tid, e.get("id"), pts))

        # weekly rosters
        final_sp = status.get("finalScoringPeriod") or 0
        for w in range(1, final_sp + 1):
            wp = RAW / str(season) / ("week_%02d.json" % w)
            if not wp.exists():
                continue
            wj = json.load(open(wp))
            if season >= MODERN_FROM:
                for t in wj.get("teams") or []:
                    tid = t.get("id")
                    for en in (t.get("roster") or {}).get("entries") or []:
                        ppe = en.get("playerPoolEntry") or {}
                        pl = ppe.get("player") or {}
                        pid = en.get("playerId") or pl.get("id")
                        slot = en.get("lineupSlotId")
                        actual, projected = week_applied(pl, w)
                        see_player(season, pl, pid)
                        cx.execute("INSERT OR REPLACE INTO fact_roster_week VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
                            season, w, tid, pid, slot,
                            0 if slot in BENCH_SLOTS else 1,
                            actual, projected, en.get("injuryStatus"),
                            en.get("acquisitionType"), "Observed", "weekly_roster"))
            else:
                for e in wj.get("schedule") or []:
                    for side in (e.get("home") or {}, e.get("away") or {}):
                        tid = side.get("teamId")
                        pbs = side.get("pointsByScoringPeriod") or {}
                        if not tid or str(w) not in pbs:
                            continue
                        multiweek = len(pbs) > 1
                        weeks_json = json.dumps(sorted(int(k) for k in pbs))
                        total = 0.0
                        n_obs = 0
                        for en in (side.get("rosterForMatchupPeriod") or {}).get("entries") or []:
                            ppe = en.get("playerPoolEntry") or {}
                            pl = ppe.get("player") or {}
                            pid = en.get("playerId") or pl.get("id")
                            applied = ppe.get("appliedStatTotal")
                            total += applied or 0.0
                            n_obs += 1
                            see_player(season, pl, pid)
                            if multiweek:
                                # weekly membership evidence only; points live at
                                # matchup grain (roster is the union of the
                                # matchup's started lineups)
                                cx.execute("INSERT OR REPLACE INTO fact_roster_week VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
                                    season, w, tid, pid, None, 1,
                                    None, None, en.get("injuryStatus"),
                                    en.get("acquisitionType"), "Unavailable",
                                    "matchup_roster_multiweek"))
                                cx.execute("INSERT OR REPLACE INTO fact_matchup_player_pre2018 VALUES (?,?,?,?,?,?)", (
                                    season, e.get("id"), tid, pid, applied, weeks_json))
                            else:
                                cx.execute("INSERT OR REPLACE INTO fact_roster_week VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
                                    season, w, tid, pid, None, 1,
                                    applied, None, en.get("injuryStatus"),
                                    en.get("acquisitionType"), "Unavailable", "matchup_roster"))
                        wk_pts = pbs.get(str(w)) or 0.0
                        if multiweek:
                            # matchup-grain reconciliation happens after the loop
                            cx.execute("INSERT OR REPLACE INTO fact_week_coverage VALUES (?,?,?,?,?,?,?,?)", (
                                season, w, tid, n_obs, None, wk_pts, None, 1))
                        else:
                            diff = abs(total - wk_pts)
                            recon["pre2018"]["worst"] = max(recon["pre2018"]["worst"], diff)
                            recon["pre2018"]["ok" if diff <= 0.6 else "bad"] += 1
                            cx.execute("INSERT OR REPLACE INTO fact_week_coverage VALUES (?,?,?,?,?,?,?,?)", (
                                season, w, tid, n_obs, total, wk_pts,
                                round(wk_pts - total, 2), 0))

        # draft
        dj = RAW / str(season) / "draft.json"
        if dj.exists():
            dd = (json.load(open(dj)).get("draftDetail")) or {}
            for p in dd.get("picks") or []:
                see_player(season, None, p.get("playerId"))
                cx.execute("INSERT OR REPLACE INTO fact_draft_pick VALUES (?,?,?,?,?,?,?,?,?)", (
                    season, p.get("overallPickNumber"), p.get("roundId"),
                    p.get("roundPickNumber"), p.get("teamId"), p.get("playerId"),
                    p.get("bidAmount"), int(bool(p.get("keeper"))),
                    p.get("nominatingTeamId")))

        # transactions (2018+)
        if season >= MODERN_FROM:
            seen_tx = set()
            for w in range(0, final_sp + 1):
                tp = RAW / str(season) / ("tx_%02d.json" % w)
                if not tp.exists():
                    continue
                for tx in json.load(open(tp)).get("transactions") or []:
                    txid = tx.get("id")
                    if txid in seen_tx:
                        continue
                    seen_tx.add(txid)
                    cx.execute("INSERT OR REPLACE INTO fact_transaction VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                        season, txid, tx.get("type"), tx.get("status"),
                        tx.get("executionType"), tx.get("scoringPeriodId"),
                        tx.get("teamId"), tx.get("bidAmount"),
                        tx.get("proposedDate"), tx.get("processDate"),
                        int(bool(tx.get("isPending"))), tx.get("memberId"),
                        tx.get("relatedTransactionId")))
                    for i, it in enumerate(tx.get("items") or []):
                        see_player(season, None, it.get("playerId"))
                        cx.execute("INSERT OR REPLACE INTO fact_transaction_item VALUES (?,?,?,?,?,?,?,?)", (
                            season, txid, i, it.get("playerId"), it.get("type"),
                            it.get("fromTeamId"), it.get("toTeamId"),
                            int(bool(it.get("isKeeper")))))

    # players
    for pid, rec in players.items():
        is_dst = 1 if pid is not None and pid <= -16000 else 0
        pro = -(pid + 16000) if is_dst else rec["pro"]
        cx.execute("INSERT OR REPLACE INTO dim_player_espn VALUES (?,?,?,?,?,?,?)", (
            pid, rec["name"], 16 if is_dst else rec["pos"], pro, is_dst,
            rec["first"], rec["last"]))

    # modern reconciliation: starters sum vs team-week points (+ coverage rows)
    rows = cx.execute("""
      SELECT rw.season, rw.week, rw.team_id, COUNT(*) AS n,
             SUM(COALESCE(rw.applied_points,0)) AS starter_pts, tw.points
      FROM fact_roster_week rw
      JOIN fact_team_week tw ON tw.season=rw.season AND tw.week=rw.week AND tw.team_id=rw.team_id
      WHERE rw.started=1 AND rw.season>=2018
      GROUP BY 1,2,3""").fetchall()
    for season, week, tid, n, sp, pts in rows:
        diff = abs((sp or 0) - (pts or 0))
        recon["modern"]["worst"] = max(recon["modern"]["worst"], diff)
        recon["modern"]["ok" if diff <= 0.6 else "bad"] += 1
        cx.execute("INSERT OR REPLACE INTO fact_week_coverage VALUES (?,?,?,?,?,?,?,?)",
                   (season, week, tid, n, sp, pts, round((pts or 0) - (sp or 0), 2), 0))

    # pre-2018 multi-week playoff matchups: matchup-grain reconciliation
    recon["pre2018_matchup"] = {"ok": 0, "bad": 0, "worst": 0.0}
    rows = cx.execute("""
      SELECT mp.season, mp.matchup_id, mp.team_id, SUM(COALESCE(mp.applied_points,0)),
             CASE WHEN m.home_team_id = mp.team_id THEN m.home_score ELSE m.away_score END
      FROM fact_matchup_player_pre2018 mp
      JOIN fact_matchup m ON m.season = mp.season AND m.matchup_id = mp.matchup_id
      GROUP BY 1,2,3""").fetchall()
    for _, _, _, sp, pts in rows:
        diff = abs((sp or 0) - (pts or 0))
        recon["pre2018_matchup"]["worst"] = max(recon["pre2018_matchup"]["worst"], diff)
        recon["pre2018_matchup"]["ok" if diff <= 0.6 else "bad"] += 1

    cx.execute("INSERT INTO meta VALUES ('built_at', datetime('now'))")
    cx.execute("INSERT INTO meta VALUES ('league_id', '51418')")
    cx.execute("INSERT INTO meta VALUES ('reconciliation', ?)", (json.dumps(recon),))
    cx.commit()

    # ---- report -------------------------------------------------------------
    REPORTS.mkdir(parents=True, exist_ok=True)
    report = {"counts": {}, "reconciliation": recon,
              "franchises": len(franchises),
              "active_2026": sorted(x for x in active_2026 if x)}
    report["pre2018_unattributed"] = cx.execute("""
      SELECT COUNT(*), ROUND(SUM(unattributed_points),1) FROM fact_week_coverage
      WHERE season < 2018 AND is_multiweek_matchup = 0 AND unattributed_points > 0.6""").fetchone()
    for tbl in ("dim_owner", "dim_franchise", "dim_season", "dim_team_season",
                "fact_matchup", "fact_team_week", "fact_roster_week",
                "fact_draft_pick", "fact_transaction", "fact_transaction_item",
                "dim_player_espn", "fact_matchup_player_pre2018", "fact_week_coverage"):
        report["counts"][tbl] = cx.execute("SELECT COUNT(*) FROM %s" % tbl).fetchone()[0]
    json.dump(report, open(REPORTS / "affl_build_report.json", "w"), indent=2)

    print(json.dumps(report["counts"], indent=2))
    print("franchises:", len(franchises))
    print("2026 active franchises:", len(report["active_2026"]))
    print("reconciliation:", json.dumps(recon))
    cx.close()


if __name__ == "__main__":
    main()
