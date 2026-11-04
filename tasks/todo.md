# Plan

## Stage 1: exploration spec
- [x] Confirm assignment text availability (not in repo, not in paste; working from the brief's paraphrase)
- [x] Answer the 4 pre-flight questions
- [x] Write EXPLORATION.md (plan to execute, not to read)
- [x] Exploration executed on the full file (2026-11-01); findings/ complete, start at findings/REPORT.md

## Stage 2: platform spec
- [x] DESIGN.md
- [x] DATA_MODEL.md
- [x] cards/P0..P9.md + cards/README.md (builder prompt)
- [x] docs/PRIMER.md, docs/NOTEBOOKLM_PROMPTS.md

## Stage 3: build (builder sessions, human verifies between cards)
- [ ] P0 scaffold
- [ ] P1 ingest
- [ ] P2 resolve
- [ ] P3 score
- [ ] P4 evaluate
- [ ] P5 app + deploy
- [ ] P6 delta (optional)
- [ ] P7 classifier (optional)
- [ ] P8 report card (optional)
- [ ] P9 MCP (optional)
- [ ] Architect fills every [P<n> fills] in DESIGN.md from handoff reports; updates docs/PRIMER.md

## Review
- Stage 1 and 2 delivered by the architect. No application code written by the architect.

## P6: delta and change detection (builder, Sonnet 5.5, 2026-11-03)
Another session deploys P5 in the same tree: stage by explicit path only; do not touch docs/DEPLOY.md, DESIGN.md section 9, fly.toml, Dockerfile.
- [ ] config/delta.yaml + sis/delta_config.py; paths helpers; sis/delta/truth.py (truth file, synthetic_file_ids)
- [ ] Guards so a synthetic file never reaches the real state: resolve write_back skipped, both merge_current skip synthetic files
- [ ] sis/delta/synth.py: select (DuckDB, md5 order, disjoint sets), stream (orjson, ordered pool, zstd), truth; tests first
- [ ] sis/delta/diff.py + sql: events, history, deterministic ids, detected_at = received_at of the to file
- [ ] sis/delta/verify.py + report.py: recall/precision per type, explained misses, 10 examples, wall time
- [ ] CLI synth/delta (remove delta from the stub test)
- [ ] Bundle: events + max_event_severity + delta block in bundle.json; API sort recent_change; detail page "Changes (simulated second delivery)"
- [ ] tests/test_delta.py (4 card tests + more), audit, mypy
- [ ] Real run: synth seed 42 -> ingest -> resolve -> score -> delta; DELTA_REPORT; DESIGN 8 wall time
- [ ] State resume point, board, lessons, handoff

## P5.1: UI readability pass and overview dashboard (builder, Opus 5.5, 2026-11-04)
- [ ] tokens.css (both themes, OKLCH) + app.css (components); old CSS removed; palettes run through the dataviz validator
- [ ] sis/api/labels.py: signal, fact, segment, event labels and sentences; test every catalogue id and event type has one
- [ ] /api/stats: exposure_hist (10 counts) and signal_fire_counts, cached on app.state; shape tests
- [ ] Templates: base (sticky header, nav, theme toggle, bundle), overview (/), accounts (/accounts), _rows, account, about
- [ ] Tests updated for the route move (/ -> overview, list at /accounts)
- [ ] Audit, mypy; Playwright walk 1280 and 390, dark and light; docs/ui/*.png; docs/UI_REPORT.md; console clean; Lighthouse a11y >= 90
- [ ] Redeploy (feedback.jsonl copied out first) with the P6 bundle; live smoke; DESIGN.md 11 sentence
- [ ] State resume point, board, handoff
