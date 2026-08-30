#!/usr/bin/env python3
"""AFFL Savant — strip ESPN member identifiers from the committed affl.db.

ESPN SWIDs (account UUIDs) appear in dim_owner.swids_json,
dim_franchise.swids_json, and fact_transaction.member_id. They exist for
import provenance only: the identity canon groups on OWNER DISPLAY NAME
(one owner holds three SWIDs, so SWID was never a join key), and no build
step downstream of build_affl_db.py reads any of these columns — verified
by regenerating every mart before/after and diffing byte-identical.

Run AFTER build_affl_db.py, BEFORE committing affl.db anywhere.
Idempotent. The full-fidelity import lives only in the private snapshots.
"""
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "affl.db"

ax = sqlite3.connect(str(DB))
before = {
    "owner_swids": ax.execute("SELECT COUNT(*) FROM dim_owner WHERE swids_json IS NOT NULL AND swids_json != '[]'").fetchone()[0],
    "franchise_swids": ax.execute("SELECT COUNT(*) FROM dim_franchise WHERE swids_json IS NOT NULL AND swids_json != '[]'").fetchone()[0],
    "tx_member_ids": ax.execute("SELECT COUNT(*) FROM fact_transaction WHERE member_id IS NOT NULL").fetchone()[0],
}
ax.execute("UPDATE dim_owner SET swids_json = '[]'")
ax.execute("UPDATE dim_franchise SET swids_json = '[]'")
ax.execute("UPDATE fact_transaction SET member_id = NULL")
ax.commit()
ax.execute("VACUUM")
ax.close()
print(json.dumps({"stripped": before, "db": str(DB)}, indent=1))
