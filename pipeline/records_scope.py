"""Record-book construction with an explicit, uniform scope: REGULAR SEASON ONLY.

Why this module exists (2026-08-30 audit): the original inline records block in
export_marts.py drew from fact_team_week and the full matchup list with no tier
filter, so consolation-ladder games and playoff weeks sat unlabeled in the
record book while every other surface on the site (h2h, streaks, all-play,
rank heatmap) excludes them. Concretely: the two biggest "blowouts" of all time
were consolation games, and 2014-16 playoff "games" are two-week matchup totals
that are not comparable to weekly games at all. On top of that, ESPN's 2022
finals week carries five commissioner score adjustments that exist only in
matchup totals (not weekly team scores), so playoff team-weeks from
fact_team_week can understate the official number. Restricting the record book
to the regular season removes every one of those traps and matches the site's
labeling convention.

Used by export_marts.py on full rebuilds and by patch_savant_records.py for
surgical mart updates. Single source of truth: do not fork this logic.
"""


def r1(v):
    return None if v is None else round(float(v), 1)


def regular_team_weeks(ax, fid_by_st):
    """All regular-season team-weeks (byes included - a bye team still scores)."""
    rows = ax.execute(
        "SELECT w.season, w.week, w.team_id, w.points"
        " FROM fact_team_week w JOIN fact_matchup m"
        "   ON m.season = w.season AND m.matchup_id = w.matchup_id"
        " WHERE w.points IS NOT NULL AND m.is_playoff = 0"
        " ORDER BY w.season, w.week, w.team_id").fetchall()
    return [{"season": r["season"], "week": r["week"], "team_id": r["team_id"],
             "points": r["points"], "fid": fid_by_st.get((r["season"], r["team_id"]))}
            for r in rows]


def build_records(ax, fid_by_st, matchups):
    """records mart: regular season only, deterministic tiebreaks.

    matchups: the mart-shaped matchup dicts (keys season/mp/h/a/hs/as_/winner/po/bye).
    """
    tws = regular_team_weeks(ax, fid_by_st)
    # deterministic tiebreaks on equal points: earlier season, week, team id
    hi = sorted(tws, key=lambda t: (-t["points"], t["season"], t["week"], t["team_id"]))
    lo = sorted(tws, key=lambda t: (t["points"], t["season"], t["week"], t["team_id"]))

    games = [m for m in matchups
             if not m["po"] and not m["bye"] and m["hs"] is not None
             and m["winner"] not in (None, "UNDECIDED")]
    blow = sorted(games, key=lambda m: (-abs(m["hs"] - m["as_"]), m["season"], m["mp"]))
    close = sorted([g for g in games if abs(g["hs"] - g["as_"]) > 0],
                   key=lambda m: (abs(m["hs"] - m["as_"]), m["season"], m["mp"]))

    # regular-season scoring periods per season (mp == scoring period in REG)
    reg_wk = {}
    for r in ax.execute("SELECT season, MAX(matchup_period) mx FROM fact_matchup"
                        " WHERE is_playoff = 0 GROUP BY season"):
        reg_wk[r["season"]] = r["mx"]
    pw_rows = ax.execute(
        "SELECT season, week, team_id, espn_player_id, applied_points"
        " FROM fact_roster_week WHERE started = 1 AND applied_points IS NOT NULL"
        " ORDER BY applied_points DESC, season, week, espn_player_id").fetchall()
    player_weeks = []
    for r in pw_rows:
        if r["week"] > reg_wk.get(r["season"], 0):
            continue                     # playoff/consolation week: out of scope
        player_weeks.append({"s": r["season"], "w": r["week"],
                             "fid": fid_by_st.get((r["season"], r["team_id"])),
                             "eid": int(r["espn_player_id"]),
                             "pts": r1(r["applied_points"])})
        if len(player_weeks) == 15:
            break

    return {
        "teamWeekHigh": hi[:12],
        "teamWeekLow": lo[:12],
        "blowouts": blow[:10],
        "closest": close[:10],
        "playerWeeks": player_weeks,
        "scope": "regular season 2014+ only; playoff and consolation games excluded",
    }
