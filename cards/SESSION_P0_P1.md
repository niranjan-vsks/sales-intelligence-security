# Tonight's session: forge, then P0, then P1 (1 Sonnet 5.5 session)

Paste the block below as the first message of a fresh Claude Code session
opened in this repo with Sonnet 5.5 selected.

```
You are the BUILDER for this repo tonight. 3 steps, in order, no skipping.

STEP A: run /forge init. Launchpad documents already exist: read ASSIGNMENT.md,
DESIGN.md, DATA_MODEL.md, cards/README.md and cards/P0.md before writing
PHASE_CONFIG.md. Use these values:
  branch          main
  deploy          fly.io, app name sis (deploy happens in card P5, not tonight)
  dev             uv run sis serve
  audit           uv run ruff check . && uv run pytest -q -m "not llm"
  typecheck       uv run mypy sis
  build           docker build -t sis .      (valid only from P5 onward; "none" until then)
  scope guard     none
  invariants      uv run pytest -q -m eval   (valid from P4 onward; "none" until then)
  board           tasks/board.md          # create; 1 row per card: card, owner session, status, claimed at
  state           tasks/state.md          # exists; append newest first
  lessons         tasks/lessons.md        # exists
  bugs            none
  phase naming    P0..P9 as in cards/
  reviewer setup  dual (a fresh session reviews the card before build)
  commit          "P<N>: <subject>" · Co-Authored-By: Claude <noreply@anthropic.com>
  protected       sis_data/, data/, *.parquet, .env, docs/*.pdf, findings/ (read-only)
  release gate    strix, at P5
  quirks          repo is inside OneDrive: never write data under the repo; $SIS_DATA is
                  C:/Users/NIRANJAN VSKS/sis_data. Git Bash pipes can fail on multi-GB
                  streams ("Write error: Invalid argument"): count lines in-process, not
                  with wc -l. The raw file has no extension and is zstd.
Do not re-bootstrap if /forge reports "adopted". Create what is missing only.

STEP B: build card cards/P0.md under the builder rules in cards/README.md.
"Done" means the phase-forge gates that apply to a pipeline card with no UI:
  gate 1  the harness number: N of N tests passed, pasted verbatim
  gate 2  the full audit command above, exit 0, pasted verbatim
  gate 3  ruff and mypy clean
  gate 4  the walk: run every command in the card's acceptance tests yourself and
          paste the real output
  gate 5  live: not applicable before P5. Write "gate 5: n/a until P5" and nothing else.
Write the handoff report in the card's format. Write a resume point to the state
file BEFORE marking done.

STEP C: build card cards/P1.md the same way. The full ingest of the 16.4 GB file
takes hours: start it in the background as soon as the pre-flight and unit tests
pass, keep working on the equivalence check code while it runs, and do not
report done until the md5 equivalence with $SIS_DATA/full/banners passes.
If the run is still going when you reach your context limit, write the resume
point with the exact command to check progress and the exact command to run
the equivalence check, and stop cleanly.

Never touch findings/. Never commit anything under $SIS_DATA. Do not push.
```

## Why not P1 and P2 in parallel

- P0 is not built yet, and both P1 and P2 add commands to `sis/cli.py`
  and functions to `sis/paths.py`. 2 sessions editing the same scaffold
  at the same time produce merge conflicts, not speed.
- P2 reads `$SIS_DATA/<file_id>/banners`, which P1 creates. P2 could be
  pointed at the explorer's `$SIS_DATA/full/` copy, but then its paths
  are wrong for every later card and someone has to rework them.
- The ingest itself is the long pole and runs in the background anyway.
  The session is free to finish P1's code while it runs.

## Tomorrow morning

1. Read P1's handoff. Run the P0 and P1 acceptance tests yourself.
2. Open a fresh session, Opus 5.5, and run `/phase review cards/P2.md`
   before building it. P2 and P3 carry the most judgement; a non-author
   review of the card is cheap insurance.
3. Then build P2 in that session (or a fresh one after the review).
