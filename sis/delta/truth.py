"""The truth file of a synthetic delivery: every perturbation applied, so the diff can be scored.

$SIS_DATA/synth/<seed>_truth.json is written last, after the delivery itself, so its presence
means the delivery is complete. The pipeline reads the file ids it names to keep synthetic data
out of the real state (current/, the operator list)."""

import os
from pathlib import Path
from typing import Any

import orjson

from sis import paths

PERTURBATIONS = ("drop_banner", "new_banner", "expire_cert", "remove_waf", "add_waf", "add_vuln")


def write_truth(path: Path, truth: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(orjson.dumps(truth, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS))
    os.replace(tmp, path)


def read_truth(path: Path) -> dict[str, Any]:
    loaded = orjson.loads(path.read_bytes())
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} is not a truth file")
    return loaded


def truth_files() -> list[Path]:
    return sorted(paths.synth_dir().glob("*_truth.json"))


def synthetic_file_ids() -> set[str]:
    """The file_id of every completed synthetic delivery under $SIS_DATA/synth."""
    ids: set[str] = set()
    for p in truth_files():
        fid = read_truth(p).get("synthetic_file_id")
        if isinstance(fid, str):
            ids.add(fid)
    return ids


def truth_for(file_id: str) -> tuple[Path, dict[str, Any]] | None:
    """The truth file whose synthetic delivery is `file_id`, if there is one."""
    for p in truth_files():
        t = read_truth(p)
        if t.get("synthetic_file_id") == file_id:
            return p, t
    return None
