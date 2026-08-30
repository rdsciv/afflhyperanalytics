#!/usr/bin/env python3
"""AFFL Savant — ESPN v3 raw snapshot fetcher (resumable).

Fetches league 51418 history 2014-2025 plus the 2026 pre-draft state into
data/raw/espn/{season}/. Never prints or writes credentials; cookies come from
env (ESPN_SWID, ESPN_S2) injected by the credential runner.

Endpoint routing measured against the live API (prior project):
  2014-2017  /leagueHistory only   (cookies REQUIRED)
  2018       both                  (cookies REQUIRED)
  2019-2025  both                  (mostly public)
  2026       /seasons only         (cookies REQUIRED, pre-draft)

Files per season:
  league.json   mTeam,mSettings,mStandings,mStatus,mNav,mMatchup,mMatchupScore
  draft.json    mDraftDetail
  week_{w}.json mMatchup,mMatchupScore,mRoster @ scoringPeriodId=w
  tx_{w}.json   mTransactions2 @ scoringPeriodId=w   (2018+ only)

Usage:
  python3 fetch_espn.py --probe          # auth sanity check only
  python3 fetch_espn.py                  # full resumable fetch
  python3 fetch_espn.py --season 2019    # one season
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

def _load_env_file():
    """Load credentials from the protected env file when not already in env."""
    p = Path("/agent/secrets/espn.env")
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


_load_env_file()

BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
LEAGUE_ID = os.environ.get("ESPN_LEAGUE_ID", "51418")
FIRST, LAST = 2014, 2026
MODERN_FROM = 2018
RAW = Path(__file__).resolve().parent.parent / "data" / "raw" / "espn"

session = requests.Session()
session.headers.update({"accept": "application/json"})


def cookies():
    c = {}
    swid = os.environ.get("ESPN_SWID", "").strip()
    s2 = os.environ.get("ESPN_S2", "").strip()
    if swid:
        c["SWID"] = swid
    if s2:
        c["espn_s2"] = s2
    return c


def url_for(season):
    if season >= MODERN_FROM:
        return "%s/seasons/%d/segments/0/leagues/%s" % (BASE, season, LEAGUE_ID)
    return "%s/leagueHistory/%s" % (BASE, LEAGUE_ID)


def fetch(season, views, extra=None, tries=4):
    params = [("view", v) for v in views]
    if season < MODERN_FROM:
        params.append(("seasonId", str(season)))
    for k, v in (extra or {}).items():
        params.append((k, str(v)))
    last_status = None
    for attempt in range(tries):
        try:
            r = session.get(url_for(season), params=params, cookies=cookies(), timeout=60)
        except requests.RequestException as e:
            last_status = "EXC:%s" % type(e).__name__
            time.sleep(1.5 * (attempt + 1))
            continue
        last_status = r.status_code
        if r.status_code == 200:
            data = r.json()
            return data[0] if isinstance(data, list) else data
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(2.0 * (attempt + 1))
            continue
        break  # 401/403/404: not retryable
    raise RuntimeError("season %d views=%s -> HTTP %s" % (season, ",".join(views), last_status))


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(obj, f, separators=(",", ":"))
    tmp.rename(path)


def probe():
    ok = True
    for season in (2014, 2025, 2026):
        try:
            lg = fetch(season, ["mTeam", "mStatus"])
            teams = len(lg.get("teams", []))
            drafted = (lg.get("draftDetail") or {}).get("drafted")
            print("  %d ok  teams=%d drafted=%s" % (season, teams, drafted))
        except Exception as e:
            ok = False
            print("  %d FAILED  %s" % (season, e))
    print("cookies present: %s" % bool(cookies()))
    return ok


def fetch_season(season):
    d = RAW / str(season)
    league_p = d / "league.json"
    if league_p.exists():
        league = json.load(open(league_p))
        print("  %d league.json cached" % season)
    else:
        league = fetch(season, ["mTeam", "mSettings", "mStandings", "mStatus", "mNav", "mMatchup", "mMatchupScore"])
        save(league_p, league)
        print("  %d league.json fetched (%d teams)" % (season, len(league.get("teams", []))))

    draft_p = d / "draft.json"
    if not draft_p.exists():
        save(draft_p, fetch(season, ["mDraftDetail"]))
        print("  %d draft.json fetched" % season)

    status = league.get("status") or {}
    final_sp = status.get("finalScoringPeriod") or 0
    drafted = (league.get("draftDetail") or {}).get("drafted")
    current_mp = status.get("currentMatchupPeriod") or 0
    complete = bool(drafted) and current_mp > 1
    if not complete:
        print("  %d pre-draft/incomplete: skipping weeks + transactions" % season)
        return

    for w in range(1, final_sp + 1):
        wp = d / ("week_%02d.json" % w)
        if wp.exists():
            continue
        save(wp, fetch(season, ["mMatchup", "mMatchupScore", "mRoster"], {"scoringPeriodId": w}))
        time.sleep(0.15)
    print("  %d weeks 1-%d snapshotted" % (season, final_sp))

    if season >= MODERN_FROM:
        for w in range(0, final_sp + 1):
            tp = d / ("tx_%02d.json" % w)
            if tp.exists():
                continue
            save(tp, fetch(season, ["mTransactions2"], {"scoringPeriodId": w}))
            time.sleep(0.15)
        print("  %d transactions snapshotted (periods 0-%d)" % (season, final_sp))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--season", type=int)
    args = ap.parse_args()

    if args.probe:
        sys.exit(0 if probe() else 1)

    seasons = [args.season] if args.season else list(range(FIRST, LAST + 1))
    failed = []
    for season in seasons:
        try:
            fetch_season(season)
        except Exception as e:
            failed.append(season)
            print("  %d FAILED: %s" % (season, e))
    manifest = {"fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "league_id": LEAGUE_ID, "failed": failed}
    save(RAW / "fetch_manifest.json", manifest)
    print("done. failed seasons: %s" % (failed or "none"))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
