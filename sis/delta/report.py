"""docs/DELTA_REPORT_<from>_<to>.md: every number comes from the run that wrote it."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from sis import db, paths
from sis.delta.diff import EVENT_TYPES, DiffResult, _lit, read_events
from sis.delta.truth import PERTURBATIONS
from sis.delta.verify import TypeStats

N_EXAMPLES = 10
SIGNAL_EVENTS_B = ("signal_appeared", "cert_expired_since", "protection_added")
SIGNAL_EVENTS_A = ("signal_cleared", "protection_removed")


def pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


def pick_examples(events: list[dict[str, Any]], n: int = N_EXAMPLES) -> list[dict[str, Any]]:
    """1 event per type first (highest severity types first), then more of the same until n.
    Deterministic: events arrive sorted by event_id."""
    by_type: dict[str, list[dict[str, Any]]] = {}
    for e in events:
        by_type.setdefault(e["event_type"], []).append(e)
    order = sorted(by_type, key=lambda t: (-max(e["severity"] for e in by_type[t]), t))
    picked: list[dict[str, Any]] = []
    depth = 0
    while len(picked) < n and any(len(by_type[t]) > depth for t in order):
        for t in order:
            if len(by_type[t]) > depth and len(picked) < n:
                picked.append(by_type[t][depth])
        depth += 1
    return picked


def _evidence(con: duckdb.DuckDBPyConnection, file_id: str, entity_id: str,
              signal_id: str) -> list[str]:
    path = _lit((paths.file_dir(file_id) / "evidence.parquet").as_posix())
    rows = con.execute(
        f"SELECT ip, port, module, field, value FROM read_parquet({path}) "
        "WHERE entity_id = ? AND signal_id = ? ORDER BY banner_id LIMIT 3",
        [entity_id, signal_id]).fetchall()
    return [f"{ip}:{port} {module} {field} = {value}" for ip, port, module, field, value in rows]


def _top_signals(con: duckdb.DuckDBPyConnection, file_id: str, entity_id: str) -> str:
    path = _lit((paths.file_dir(file_id) / "scores.parquet").as_posix())
    r = con.execute(f"SELECT top_signals FROM read_parquet({path}) WHERE entity_id = ?",
                    [entity_id]).fetchall()
    return ", ".join(r[0][0]) if r and r[0][0] else "none"


def _names(con: duckdb.DuckDBPyConnection, file_id: str) -> dict[str, str]:
    path = _lit((paths.file_dir(file_id) / "entities.parquet").as_posix())
    return {r[0]: r[1] for r in con.execute(
        f"SELECT entity_id, key_value FROM read_parquet({path})").fetchall()}


def example_evidence(con: duckdb.DuckDBPyConnection, e: dict[str, Any]) -> list[str]:
    """The lines that show why the event was raised, read from the file that holds them."""
    t, eid, subj = e["event_type"], e["entity_id"], e["subject"]
    if t in SIGNAL_EVENTS_B:
        return _evidence(con, e["to_file"], eid, subj) or [f"{subj} in the new file"]
    if t in SIGNAL_EVENTS_A:
        return _evidence(con, e["from_file"], eid, subj) or [f"{subj} in the old file"]
    if t == "service_new":
        return [f"{subj} {e['to_value']} seen in the new file, not in the old"]
    if t == "service_gone":
        return [f"{subj} {e['from_value']} seen in the old file, not in the new"]
    if t in ("exposure_up", "exposure_down", "segment_changed"):
        return [f"{e['from_value']} -> {e['to_value']}",
                f"top signals before: {_top_signals(con, e['from_file'], eid)}",
                f"top signals after: {_top_signals(con, e['to_file'], eid)}"]
    return [f"{subj} ({e['to_value'] or e['from_value']})"]


def write_report(res: DiffResult, stats: list[TypeStats] | None, truth: dict[str, Any] | None,
                 history_rows: dict[str, int], out: Path) -> None:
    events = read_events(res.from_file, res.to_file)
    con = db.connect()
    names = {**_names(con, res.from_file), **_names(con, res.to_file)}
    simulated = truth is not None
    L: list[str] = []
    title = "simulated second delivery" if simulated else "consecutive deliveries"
    L += [f"# Delta report: {title}", ""]
    L += [f"Generated {datetime.now(UTC).strftime('%Y-%m-%d %H:%M')} UTC by `sis delta`.", ""]
    if truth is not None:
        L += ["**The second file is synthetic.** It was manufactured by `sis synth` from the "
              "first file's own raw lines (seed " + str(truth["seed"]) + "): a seeded subset of "
              "banners dropped, copied to a new port, or changed, every timestamp moved forward "
              f"{truth['params']['shift_days']} days, and `_shodan.id` left unchanged on "
              "surviving banners (the diff keys on entity and ip:port, so that changes nothing it "
              "reads). It gives the diff a known answer. It is not evidence about how real "
              "services change.", ""]
    L += ["| | file_id |", "|---|---|", f"| from | `{res.from_file}` |",
          f"| to | `{res.to_file}` |", ""]
    L += [f"Active entities: {res.n_active_from:,} -> {res.n_active_to:,}. "
          f"Events: {res.n_events:,} (severity 3: {res.by_severity.get(3, 0):,}, "
          f"2: {res.by_severity.get(2, 0):,}, 1: {res.by_severity.get(1, 0):,}).", ""]
    L += [f"**Diff wall time: {res.wall_seconds} s** (load both files' tables, compute and write "
          "the events). History rows written: "
          + ", ".join(f"{n:,} for `{f[:12]}`" for f, n in history_rows.items()) + ".", ""]

    if truth is not None and stats is not None:
        L += ["## Perturbations applied", "",
              "Percent of the eligible banners of active entities, in this order; a banner takes "
              "part in at most 1 perturbation.", "",
              "| perturbation | percent | eligible banners | selected | applied | entities |",
              "|---|---|---|---|---|---|"]
        for s in stats:
            p = truth["params"]["percent"][s.ptype]
            L.append(f"| {s.ptype} | {p} | {s.eligible:,} | {s.selected:,} | {s.applied:,} | "
                     f"{s.perturbed_entities:,} |")
        L += ["", f"Lines read {truth['lines_in']:,}, written {truth['lines_out']:,}; "
              f"passed through unchanged (malformed) {truth['passthrough']:,}; "
              f"timestamp not shifted {truth['unshifted']:,}.", ""]

    L += ["## Events by type", "", "| event type | events |", "|---|---|"]
    L += [f"| {t} | {res.by_type.get(t, 0):,} |" for t in EVENT_TYPES]
    L += [""]

    if stats is not None:
        L += ["## Precision and recall against the truth", "",
              "Recall = perturbed entities with at least 1 matching event / perturbed entities. "
              "Precision = matching events on perturbed entities / all matching events. "
              "Detected by: " + "; ".join(
                  f"{p} -> " + "/".join(_det(p)) for p in PERTURBATIONS) + ".", "",
              "| perturbation | entities | detected | recall | bar | precision | "
              "recall excluding explained misses |", "|---|---|---|---|---|---|---|"]
        for s in stats:
            bar = "" if s.recall_min is None else (
                f"{pct(s.recall_min)} {'met' if s.passed else 'NOT met'}")
            L.append(f"| {s.ptype} | {s.perturbed_entities:,} | {s.detected_entities:,} | "
                     f"{pct(s.recall)} | {bar} | {pct(s.precision)} "
                     f"({s.events_on_perturbed:,} of {s.events_of_type:,}) | "
                     f"{pct(s.recall_detectable)} |")
        L += ["", "### Misses, by category", "",
              "A perturbation is at banner grain and an event at entity grain, so some cannot "
              "map 1:1 to an event. Each missed entity is put in the first category that fits, "
              "found by a query on the 2 files' own tables. `unexplained` is what no category "
              "covers.", "",
              "| perturbation | category | entities |", "|---|---|---|"]
        for s in stats:
            for name, n in s.misses.items():
                L.append(f"| {s.ptype} | {name} | {n:,} |")
            L.append(f"| {s.ptype} | **unexplained** | {s.unexplained:,} |")
        L += ["", "Precision is below 100% for 2 reasons that are not errors. The perturbations "
              "have side effects the scorer sees: a banner that gains a WAF becomes an edge "
              "banner and its software, certificate and service signals stop counting "
              "(`signal_cleared`, exposure and segment events); one that loses it starts "
              "counting. And dropping or adding banners moves an entity's IP coverage across "
              "the roll-up cutoff, so entities appear and vanish (`entity_new`, `entity_gone`) "
              "and take their services with them.", ""]

    L += [f"## {N_EXAMPLES} example events", ""]
    for e in pick_examples(events):
        name = names.get(e["entity_id"], e["entity_id"][:12])
        L += [f"- **{e['event_type']}** (severity {e['severity']}) on `{name}`, subject "
              f"`{e['subject']}`, from `{e['from_value']}` to `{e['to_value']}`"]
        L += [f"    - {line}" for line in example_evidence(con, e)]
    L += [""]

    L += ["## What a real second delivery would add", "",
          "This file differs from the first only where `sis synth` changed it, so every event "
          "has a cause that is written down. A real delivery would add what a simulation "
          "cannot: re-observation gaps (a service the scanner missed this time, which looks "
          "like `service_gone` and is not), banners that were never in the first file, "
          "genuinely new entities and domains, certificates renewed rather than expired, and "
          "changes nobody planned. The diff logic is the same; what changes is how much of its "
          "output is noise, and the first real pair is where that is measured. Only 2 files are "
          "compared at a time; windows of 3 or more files (to treat a missed observation as "
          "still present) are described in DESIGN.md section 8 and not built.", ""]
    con.close()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L), encoding="utf-8", newline="\n")


def _det(ptype: str) -> tuple[str, ...]:
    from sis.delta.verify import DETECTED_BY

    types, subject = DETECTED_BY[ptype]
    return tuple(f"{t}[{subject}]" if subject else t for t in types)
