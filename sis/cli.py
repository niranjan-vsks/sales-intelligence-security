"""The `sis` command line. Each pipeline stage is a stub until its card builds it."""

import typer

app = typer.Typer(help="Sales intelligence pipeline.", no_args_is_help=True, add_completion=False)

NOT_IMPLEMENTED_EXIT = 2


def _stub(name: str) -> None:
    typer.echo(f"not implemented: {name}")
    raise typer.Exit(code=NOT_IMPLEMENTED_EXIT)


@app.command()
def ingest() -> None:
    """Flatten one raw delivery into Parquet (P1)."""
    _stub("ingest")


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
