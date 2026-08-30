#!/usr/bin/env python3
"""Surgically rebuild ONLY the records block (+ meta.version) of the existing
savant mart, so the audit's record-book scope fix ships without requiring the
full NFL warehouse (nfl.duckdb) that export_marts.py needs. Uses the exact same
records_scope module as export_marts, so a future full rebuild produces the
identical block."""
import json
import sqlite3
from pathlib import Path

from records_scope import build_records

ROOT = Path(__file__).resolve().parent.parent
ax = sqlite3.connect(str(ROOT / "data" / "affl.db"))
ax.row_factory = sqlite3.Row
fid_by_st = {(r["season"], r["team_id"]): r["franchise_id"]
             for r in ax.execute("SELECT season, team_id, franchise_id FROM dim_team_season")}

mart_path = ROOT / "data" / "marts" / "savant_data.json"
S = json.loads(mart_path.read_text())
S["records"] = build_records(ax, fid_by_st, S["matchups"])
S["meta"]["version"] = "2026.08.30.2"
with open(mart_path, "w") as f:
    json.dump(S, f, separators=(",", ":"), ensure_ascii=False, default=str)
print("records patched:", {k: len(v) if isinstance(v, list) else v for k, v in S["records"].items()})
