#!/usr/bin/env python3
"""AFFL Savant — nflverse raw asset downloader (resumable).

Downloads into data/raw/nflverse/:
  players.csv                         cross-source ID map (espn_id -> gsis_id)
  roster_{y}.csv        2014-2025     season rosters (espn_id backfill)
  stats_player_week_{y}.csv 2014-2025 weekly player stats (all season types; build filters REG)
  play_by_play_{y}.parquet 2014-2025  full pbp corpus (opportunity metrics)
"""
import sys
import time
from pathlib import Path

import requests

RAW = Path(__file__).resolve().parent.parent / "data" / "raw" / "nflverse"
DL = "https://github.com/nflverse/nflverse-data/releases/download"
YEARS = list(range(2014, 2026))

# FIX: teams/teams.csv 404s on nflverse-data and was never read by any build
# step (NFL team identity comes from pbp posteam/defteam + rosters). Dropped.
ASSETS = [("players/players.csv", "players.csv")]
for y in YEARS:
    ASSETS.append(("rosters/roster_%d.csv" % y, "roster_%d.csv" % y))
    # FIX: build_nfl_db.py needs WEEK grain. stats_player_reg_*.csv is a
    # SEASON-grain aggregate (872KB, no `week` column) and does not match the
    # stats_player_week_*.csv glob the build reads -- following the README as
    # written fetched the wrong asset and left fact_player_week empty.
    ASSETS.append(("stats_player/stats_player_week_%d.csv" % y, "stats_player_week_%d.csv" % y))
    ASSETS.append(("pbp/play_by_play_%d.parquet" % y, "play_by_play_%d.parquet" % y))


def download(rel, name, tries=3):
    dest = RAW / name
    if dest.exists() and dest.stat().st_size > 1000:
        return "cached", dest.stat().st_size
    url = "%s/%s" % (DL, rel)
    for attempt in range(tries):
        try:
            with requests.get(url, stream=True, timeout=300) as r:
                if r.status_code != 200:
                    if attempt < tries - 1:
                        time.sleep(2 * (attempt + 1))
                        continue
                    return "http %d" % r.status_code, 0
                tmp = dest.with_suffix(dest.suffix + ".tmp")
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
                tmp.rename(dest)
                return "ok", dest.stat().st_size
        except requests.RequestException as e:
            if attempt < tries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            return "exc %s" % type(e).__name__, 0
    return "failed", 0


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    failures = 0
    total = 0
    for rel, name in ASSETS:
        status, size = download(rel, name)
        total += size
        flag = "" if status in ("ok", "cached") else "  <-- FAIL"
        print("%-34s %-8s %10.1f MB%s" % (name, status, size / 1e6, flag))
        if flag:
            failures += 1
    print("total on disk: %.1f MB, failures: %d" % (total / 1e6, failures))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
