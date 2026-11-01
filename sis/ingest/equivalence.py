"""Check a P1 ingest against the explorer's run, which P1 must reproduce exactly.

    uv run python -m sis.ingest.equivalence <file_id>

Compares row counts and an md5 over every banner id. The explorer's output at
$SIS_DATA/full is only read.
"""

import sys
from typing import Any

from sis import db, paths

EXPLORER_BANNERS = 14_608_406
EXPLORER_VULNS = 20_988_468

_ID_HASH = "SELECT md5(string_agg(id, ',' ORDER BY id)) FROM {view}"


def _scalar(con: Any, sql: str) -> Any:
    row = con.execute(sql).fetchone()
    assert row is not None
    return row[0]


def check(file_id: str, baseline: str = "full") -> dict[str, Any]:
    con = db.connect()
    db.register(con, "new_b", paths.banners_glob(file_id))
    db.register(con, "new_v", paths.vulns_glob(file_id))
    db.register(con, "old_b", paths.banners_glob(baseline))
    db.register(con, "old_v", paths.vulns_glob(baseline))
    out: dict[str, Any] = {
        "banners": _scalar(con, "SELECT count(*) FROM new_b"),
        "vulns": _scalar(con, "SELECT count(*) FROM new_v"),
        "old_banners": _scalar(con, "SELECT count(*) FROM old_b"),
        "old_vulns": _scalar(con, "SELECT count(*) FROM old_v"),
        "id_hash": _scalar(con, _ID_HASH.format(view="new_b")),
        "old_id_hash": _scalar(con, _ID_HASH.format(view="old_b")),
    }
    out["banners_ok"] = out["banners"] == out["old_banners"] == EXPLORER_BANNERS
    out["vulns_ok"] = out["vulns"] == out["old_vulns"] == EXPLORER_VULNS
    out["id_hash_ok"] = out["id_hash"] == out["old_id_hash"]
    return out


if __name__ == "__main__":
    result = check(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "full")
    for k, v in result.items():
        print(f"{k}: {v}")
    sys.exit(0 if result["banners_ok"] and result["vulns_ok"] and result["id_hash_ok"] else 1)
