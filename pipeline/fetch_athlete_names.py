#!/usr/bin/env python3
"""AFFL Savant — resolve ESPN player ids that appear in league history but in
no held snapshot (drafted-then-cut players, mostly 2014-2017 where ESPN's
historical rosters omit dropped players).

Source: ESPN's PUBLIC athlete endpoint (no league auth, no cookies):
  https://site.web.api.espn.com/apis/common/v3/sports/football/nfl/athletes/{id}

Writes data/raw/athlete_names_patch.json:
  { "<espn_player_id>": {"name": ..., "pos": ..., "source": "espn_athlete_api"} }

The patch is display data ONLY (names/positions for rendering) — it never
feeds joins, custody, or metrics. export_marts.py folds it into the player
mart as draft-only identities with zero custody.
"""
import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
import sqlite3

OUT = ROOT / "data" / "raw" / "athlete_names_patch.json"
API = "https://site.web.api.espn.com/apis/common/v3/sports/football/nfl/athletes/%d"

# ESPN position abbreviations -> AFFL display positions
POS_MAP = {"QB": "QB", "RB": "RB", "FB": "RB", "WR": "WR", "TE": "TE",
           "PK": "K", "K": "K"}


def missing_ids():
    ax = sqlite3.connect(str(ROOT / "data" / "affl.db"))
    named = {r[0] for r in ax.execute(
        "SELECT espn_player_id FROM dim_player_espn WHERE full_name IS NOT NULL")}
    drafted = {r[0] for r in ax.execute(
        "SELECT DISTINCT espn_player_id FROM fact_draft_pick WHERE espn_player_id IS NOT NULL")}
    refd = set(drafted)
    for r in ax.execute("SELECT DISTINCT espn_player_id FROM fact_transaction_item"
                        " WHERE espn_player_id IS NOT NULL"):
        refd.add(r[0])
    return sorted(e for e in refd if e not in named and e > 0), drafted


def main():
    existing = {}
    if OUT.exists():
        existing = json.load(open(OUT))
    miss, drafted = missing_ids()
    todo = [e for e in miss if str(e) not in existing]
    print("missing ids to resolve: %d (cached: %d)" % (len(todo), len(existing)))
    fails = 0
    draft_fails = 0
    for eid in todo:
        try:
            r = requests.get(API % eid, timeout=15)
            if r.status_code != 200:
                print("  %d -> HTTP %d%s" % (eid, r.status_code,
                      "" if eid in drafted else " (transaction-only id; phantom slots like 100001 are expected to 404)"))
                fails += 1
                draft_fails += eid in drafted
                continue
            a = r.json().get("athlete", r.json())
            name = a.get("displayName")
            pos = POS_MAP.get(((a.get("position") or {}).get("abbreviation") or "").upper())
            if not name:
                print("  %d -> no displayName" % eid)
                fails += 1
                continue
            existing[str(eid)] = {"name": name, "pos": pos, "source": "espn_athlete_api"}
            print("  %d -> %s (%s)" % (eid, name, pos or "?"))
            time.sleep(0.4)
        except requests.RequestException as ex:
            print("  %d -> %s" % (eid, type(ex).__name__))
            fails += 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    json.dump(existing, open(OUT, "w"), indent=1, sort_keys=True)
    print("patch entries: %d, failures: %d (drafted-player failures: %d) -> %s"
          % (len(existing), fails, draft_fails, OUT))
    # only drafted players render on boards; transaction-only phantoms may 404
    sys.exit(1 if draft_fails else 0)


if __name__ == "__main__":
    main()
