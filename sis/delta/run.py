"""`sis delta FROM TO`: events, history, truth check and report in 1 call."""

from pathlib import Path

from pydantic import BaseModel

from sis import paths
from sis.delta import diff as diff_mod
from sis.delta import report
from sis.delta.truth import truth_for
from sis.delta.verify import TypeStats, verify

REPORT_DIR = paths.REPO_ROOT / "docs"


class DeltaResult(BaseModel):
    diff: diff_mod.DiffResult
    stats: list[TypeStats] | None
    history_rows: dict[str, int]
    report: str


def run(from_file: str, to_file: str, write_report: bool = True,
        report_dir: Path | None = None) -> DeltaResult:
    res = diff_mod.diff(from_file, to_file)
    history = {f: diff_mod.append_history(f) for f in (from_file, to_file)}
    found = truth_for(to_file)
    truth = found[1] if found and found[1]["source_file_id"] == from_file else None
    stats = verify(from_file, to_file, truth) if truth else None
    out = (report_dir or REPORT_DIR) / f"DELTA_REPORT_{from_file}_{to_file}.md"
    if write_report:
        report.write_report(res, stats, truth, history, out)
    return DeltaResult(diff=res, stats=stats, history_rows=history, report=str(out))
