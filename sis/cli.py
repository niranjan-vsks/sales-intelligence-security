"""The `sis` command line. Each pipeline stage is a stub until its card builds it."""

from pathlib import Path

import typer

app = typer.Typer(help="Sales intelligence pipeline.", no_args_is_help=True, add_completion=False)

NOT_IMPLEMENTED_EXIT = 2


def _stub(name: str) -> None:
    typer.echo(f"not implemented: {name}")
    raise typer.Exit(code=NOT_IMPLEMENTED_EXIT)


@app.command()
def ingest(
    path: Path = typer.Argument(..., exists=True, dir_okay=False, help="Raw zstd JSONL delivery."),
    workers: int | None = typer.Option(None, help="Worker processes (default INGEST_WORKERS)."),
    force: bool = typer.Option(False, "--force", help="Re-ingest a file already ingested."),
) -> None:
    """Flatten one raw delivery into Parquet, atomically."""
    from sis.ingest.run import ingest as run_ingest

    res = run_ingest(path, workers=workers, force=force)
    typer.echo(f"status {res.status}")
    typer.echo(f"file_id {res.file_id}")
    for name in ("lines_read", "rows_written", "rows_dropped", "vuln_rows_written",
                 "wall_seconds"):
        typer.echo(f"{name} {getattr(res, name)}")
    if res.dropped_reasons:
        typer.echo(f"dropped_reasons {res.dropped_reasons}")
    for key, n in res.new_keys.items():
        typer.echo(f"new provider field: {key} ({n} records)")
    if res.error:
        typer.echo(f"error {res.error}", err=True)
    if res.status not in ("ok", "duplicate"):
        raise typer.Exit(code=1)


@app.command()
def resolve(
    file_id: str | None = typer.Argument(None, help="file_id printed by `sis ingest`."),
    merge: bool = typer.Option(False, "--merge", help="Rebuild current/entities.parquet."),
) -> None:
    """Resolve banners to entities, or merge the per-file entities into current state."""
    if merge:
        from sis.entities.resolve import merge_current

        m = merge_current()
        typer.echo(f"merged {len(m.files)} file(s): {m.n_entities} entities -> {m.path}")
        return
    if file_id is None:
        typer.echo("give a FILE_ID or --merge", err=True)
        raise typer.Exit(code=2)
    from sis.entities.resolve import resolve as run_resolve

    res = run_resolve(file_id)
    typer.echo(f"entities active {res.n_active} blocked {res.n_blocked}")
    typer.echo(f"by_kind {res.entities_by_kind}")
    typer.echo(f"banners primary {res.banners_primary} fallback {res.banners_fallback} "
               f"none {res.banners_none}")
    typer.echo(f"unattributed {res.unattributed}")
    typer.echo(f"operators derived {res.operators_derived}")


@app.command()
def score(
    file_id: str | None = typer.Argument(None, help="file_id of a resolved file."),
    merge: bool = typer.Option(False, "--merge", help="Rebuild current/scores.parquet."),
) -> None:
    """Compute peer groups, signals, evidence and scores, or merge scores into current state."""
    if merge:
        from sis.scoring.score import merge_current

        m = merge_current()
        typer.echo(f"merged {len(m.files)} file(s): {m.n_scores} scores -> {m.path}")
        return
    if file_id is None:
        typer.echo("give a FILE_ID or --merge", err=True)
        raise typer.Exit(code=2)
    from sis.scoring.score import score as run_score

    res = run_score(file_id)
    typer.echo(f"scored {res.n_scored} active entities, scoring_version {res.scoring_version}")
    typer.echo(f"segments {res.segments}")
    typer.echo(f"signals {res.n_signals} evidence {res.n_evidence}")
    typer.echo(f"peer {res.peer.model_dump()}")
    typer.echo(f"stage1_target_group {res.stage1_target_group}")
    typer.echo(f"wall_seconds {res.wall_seconds}")


@app.command()
def evaluate(
    file_id: str = typer.Argument(..., help="file_id of a scored file."),
    fixture: bool = typer.Option(
        False, "--fixture",
        help="Also rewrite tests/fixtures/eval_bundle and tests/eval_thresholds.json."),
) -> None:
    """Measure the ranking against held-out labels: labels, metrics, baselines, ablations."""
    from sis.evaluate.run import run

    res = run(file_id, fixture=fixture)
    typer.echo(f"labels {res.n_labels} active entities -> {res.out_dir}")
    typer.echo(f"report {res.report}")
    if res.fixture:
        typer.echo(f"fixture {res.fixture}")
    typer.echo(f"wall_seconds {res.wall_seconds}")


@app.command()
def delta() -> None:
    """Diff consecutive files into events (P6)."""
    _stub("delta")


@app.command()
def classify() -> None:
    """Classify top entities by industry with an LLM (P7)."""
    _stub("classify")


@app.command()
def export(
    version: str | None = typer.Option(
        None, help="Bundle version (default YYYYMMDD-HHMM-<scoring>)."),
) -> None:
    """Build the serve bundle from current state: $SIS_DATA/serve/<version>/."""
    from sis.export.bundle import MAX_BUNDLE_MB
    from sis.export.bundle import export as run_export

    res = run_export(version)
    typer.echo(f"bundle {res.bundle_version} -> {res.path}")
    typer.echo(f"accounts {res.n_accounts} evidence {res.n_evidence} signals {res.n_signals} "
               f"events {res.n_events}")
    typer.echo(f"size_mb {res.size_mb}")
    if res.size_mb > MAX_BUNDLE_MB:
        typer.echo(f"bundle is above {MAX_BUNDLE_MB} MB", err=True)
        raise typer.Exit(code=1)


@app.command()
def serve(
    bundle: Path | None = typer.Option(None, help="Bundle dir (default SIS_BUNDLE_DIR, or the "
                                                  "newest under $SIS_DATA/serve)."),
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8000),
) -> None:
    """Run the web app over 1 serve bundle."""
    import os

    import uvicorn

    from sis import paths

    if bundle is None and "SIS_BUNDLE_DIR" not in os.environ:
        built = sorted((paths.data_root() / "serve").glob("*/bundle.json"))
        if not built:
            typer.echo("no bundle; run `sis export` first", err=True)
            raise typer.Exit(code=1)
        bundle = built[-1].parent
    if bundle is not None:
        os.environ["SIS_BUNDLE_DIR"] = str(bundle)
    uvicorn.run("sis.api.app:create_app", factory=True, host=host, port=port)


@app.command()
def reportcard() -> None:
    """Generate a report card for one entity (P8)."""
    _stub("reportcard")


@app.command()
def mcp() -> None:
    """Run the MCP server (P9)."""
    _stub("mcp")


if __name__ == "__main__":
    app()
