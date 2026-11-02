# Session: review P2 as a non-author, then build P3 (1 Opus 5.5 session)

Paste the block below as the first message of a fresh Claude Code session
with Opus 5.5 selected.

```
You are a fresh session with no memory of building anything in this repo.
2 jobs, in order.

JOB 1: REVIEW P2 AS A NON-AUTHOR. Read tasks/state.md (the P2 handoff and
its 6 deviations), cards/P2.md, DATA_MODEL.md section 2, DESIGN.md section
4, then the diff `git diff 6c96317..e1eca2e -- sis/ config/ tests/`. The
architect has already accepted deviations 1 to 5 (DATA_MODEL 2.1 items 5
and 6 record them). Your review is about correctness, not the spec:
  a. Run `uv run pytest -q` and the P2 acceptance commands in cards/P2.md
     yourself. Paste the numbers.
  b. With DuckDB over $SIS_DATA/<file_id>/ (file_id is in tasks/state.md),
     check 5 things and paste the query and result for each:
     1. no entity key_value appears in config/operator_domains.txt
     2. no banner has both a primary and a fallback row
     3. every fallback key_value that also exists as a domain-kind entity
        was re-keyed to that entity (0 rows with the same key_value under
        2 key_kinds)
     4. the 20 largest entities by n_banners: print them with org_mode and
        say for each whether it is a customer or an operator that slipped
        through
     5. 20 random active entities (seed 13) with 3 banners each: say for
        each whether the grouping looks right
  c. Read sis/entities/normalise.py and the SQL in sis/entities/sql/ for
     bugs a test would not catch: wildcard handling, IP literals in Host
     headers, trailing dots, IDNA/punycode names, case.
  Write the findings to docs/REVIEW_P2.md with a verdict: PASS, PASS WITH
  FIXES (list them, each with a 1-line repro), or FAIL. Append 1 line to
  tasks/state.md. If PASS WITH FIXES, apply the fixes, rerun pytest and
  `sis resolve <file_id>` and `--merge`, commit as "P2: review fixes", and
  update the handoff numbers in state.md. If FAIL, stop and report.

JOB 2: BUILD cards/P3.md under the rules in cards/README.md. Read, in
order: cards/README.md, cards/P3.md (note the section "Facts from the P1
and P2 builds that change this card"), DESIGN.md sections 5 and 6,
DATA_MODEL.md section 3, config/what_we_sell_map.csv (copy it from
findings/07_what_we_sell_map.csv if config/ does not have it yet). Done
means the phase-forge gates as cards/SESSION_P0_P1.md defines them for a
pipeline card: real test counts, real command output, a resume point in
tasks/state.md before marking done, gate 5 n/a until P5. Claim P3 on
tasks/board.md first.

Never touch findings/. Never commit anything under $SIS_DATA. Do not push.
Do not run /forge init again; the repo is adopted.
```
