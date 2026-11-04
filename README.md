# Sales intelligence for a cybersecurity vendor

**Live app: https://sis-niranjan.fly.dev/**

Turns a 16 GB Shodan banner export (14.6 million service banners) into a
ranked list of 487,133 named businesses, each with a security exposure
score, a sales segment, and the verbatim evidence behind the score. Built
in 5 days for the Firmable take-home.

- Short write-up: [WRITEUP.md](WRITEUP.md). Demo guide: [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md)
- Full design: [DESIGN.md](DESIGN.md) (approach, key decisions, how it was
  measured, scale, cost, dev loop)
- Tables: [DATA_MODEL.md](DATA_MODEL.md)
- How the data was understood before any code: [EXPLORATION.md](EXPLORATION.md)
  and [findings/REPORT.md](findings/REPORT.md)
- Build order and the per-phase specs: [cards/README.md](cards/README.md)
- Build reports with the measured numbers: [docs/](docs/)

## 2-minute tour of the app

1. Open the live URL. The overview shows the book of accounts: how many
   are untouched by any security vendor, how many already have one, the
   exposure distribution, the most common reasons, and 10 accounts to
   start with.
2. Click **Accounts**. The list is sorted by priority. Filter by segment
   (Untouched is the first call list; Has a vendor is the displacement
   list), by country, by minimum exposure, or search a name.
3. Open an account. The header gives the exposure score and rank; the 4
   bars show which of the 4 facts drive it (visibly old software, neglected
   certificates, exposed surface, protection present); the Why panel
   gives the top reasons in plain words with the raw banner evidence
   collapsed under each.
4. Click **Mark as prospect** or **Not a fit**. That feedback is the first
   real label the system collects.
5. The **Changes** section on an account shows what moved between 2
   deliveries. The second delivery is simulated, and the page says so.

## What is in it

| Stage | What it does | Where |
|---|---|---|
| Ingest | streams the zstd JSONL into Parquet, idempotent on re-delivery, quarantines malformed files | `sis/ingest` |
| Resolve | turns banners into businesses by customer domain, drops operators, honeypots and hosting zones | `sis/entities` |
| Score | 24 deterministic signals, 4 facts, peer-relative scoring, 4 sales segments, evidence per signal | `sis/signals`, `sis/scoring` |
| Evaluate | held-out provider labels, precision at k, lift, rank-biserial, baselines, ablations, CI threshold | `sis/evaluate` |
| Delta | diff between deliveries, events per account | `sis/delta` |
| Serve | FastAPI + DuckDB over a 160 MB bundle; server-rendered pages | `sis/api` |

No LLM runs in the product. The 2 LLM features that were designed are
described in DESIGN.md section 7 with their status.

## Run it yourself

Requires Python 3.12 or later and [uv](https://docs.astral.sh/uv/).
Data lives outside the repo in `$SIS_DATA` (see `sis/config.py`; set it in
`.env`).

```
uv sync
uv run sis ingest <delivery.zst>        # about 12 minutes for the 16 GB file on a laptop
uv run sis resolve <file_id> && uv run sis resolve --merge
uv run sis score <file_id>   && uv run sis score --merge
uv run sis evaluate <file_id>
uv run sis export
uv run sis serve                        # http://localhost:8000
```

Tests and checks:

```
uv run ruff check . && uv run pytest -q -m "not llm"     # 169 tests
uv run mypy sis
uv run pytest -q -m eval                                  # ranking-quality threshold on a committed fixture
```

Deploy: [docs/DEPLOY.md](docs/DEPLOY.md). Cost: 1 Fly.io machine, about
7.73 USD a month.

## Status

- Built and live: ingest, entity resolution, scoring, evaluation,
  multi-file delta, hosted app.
- Designed, not built: LLM industry classification and LLM report-card
  explanations (cards P7 and P8), an MCP server (P9).
- Known limits, with numbers, in DESIGN.md section 12.

## How it was built

An architect session wrote the exploration plan before seeing the data,
an explorer session profiled the full file and wrote every number to
`findings/` with the query that produced it, and builder sessions took 1
spec card each with acceptance tests and a handoff report. The human ran
the acceptance tests between cards. `tasks/state.md` is the build log;
`tasks/lessons.md` the corrections. DESIGN.md section 10 has the detail.
