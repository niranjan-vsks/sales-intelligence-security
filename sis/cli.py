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
def resolve() -> None:
    """Resolve banners to entities (P2)."""
    _stub("resolve")


@app.command()
def score() -> None:
    """Compute signals, evidence and scores (P3)."""
    _stub("score")


@app.command()
def evaluate() -> None:
    """Measure the ranking against held-out labels (P4)."""
    _stub("evaluate")


@app.command()
def delta() -> None:
    """Diff consecutive files into events (P6)."""
    _stub("delta")


@app.command()
def classify() -> None:
    """Classify top entities by industry with an LLM (P7)."""
    _stub("classify")


@app.command()
def export() -> None:
    """Build the serve bundle (P5)."""
    _stub("export")


@app.command()
def serve() -> None:
    """Run the web app (P5)."""
    _stub("serve")


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
