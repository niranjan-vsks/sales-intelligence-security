# Sales intelligence for a cybersecurity vendor

Ranks the businesses most likely to need security help from a Shodan banner export, and shows the
evidence behind each rank. Design: [DESIGN.md](DESIGN.md). Tables: [DATA_MODEL.md](DATA_MODEL.md).
Build order: [cards/README.md](cards/README.md).

## Run the pipeline

```
uv sync
uv run sis --help                       # every stage; stages not yet built print "not implemented"
uv run sis ingest <delivery.zst>        # P1
uv run sis resolve <file_id>            # P2
uv run sis score <file_id>              # P3
uv run sis evaluate <file_id>           # P4
uv run sis export                       # P5
```

Data lives outside the repo, in `$SIS_DATA` (default `C:/Users/NIRANJAN VSKS/sis_data`). Put
overrides in `.env`; every setting is in [sis/config.py](sis/config.py).

## Run the app

```
uv run sis serve                        # P5
```

## Test

```
uv run ruff check . && uv run pytest -q -m "not llm"
uv run mypy sis
```

Tests marked `eval` (ranking quality, P4) and `llm` (live model calls, costs money) are skipped by a
plain `pytest`. Repo conventions and gates: [PHASE_CONFIG.md](PHASE_CONFIG.md).
