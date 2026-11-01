# State (past tense, newest first)

- 2026-11-02  Builder (Sonnet 5.5): P0 done, commit 0947a3e (forge init 96db3ba). 32 of 32 tests passed,
  ruff and mypy clean, every acceptance command run (output in the P0 handoff). Scaffold: sis/{config,paths,db,log,cli,
  scoring_config}.py, sis/llm/tiers_config.py, config/*, tests/, CI, Makefile, README. LLM model ids verified on
  OpenRouter 2026-11-02 (ids use dots: anthropic/claude-sonnet-5.5). gate 5: n/a until P5.
- 2026-11-02  Builder (Sonnet 5.5): /forge init. Found tasks/board.md and tasks/state.md already present,
  so adopted them; wrote PHASE_CONFIG.md, CLAUDE.md, 14 repo-local skills in .claude/skills. Global hooks
  already existed, none added. No application code yet. Next: build cards/P0.md.
- 2026-11-02  Architect (Fable): specs complete. DESIGN.md, DATA_MODEL.md, cards/P0..P9, cards/README.md
  (builder prompt), cards/SESSION_P0_P1.md (tonight's kickoff). Tiered model gateway added to P0/P7/P8/P9
  and DESIGN 7.0 after discussion: OpenRouter router, 3 tiers x 2 models, per-tier rpm and budget,
  12 USD total with top-up rather than scope cuts. Staged, not committed. Next: builder session runs
  /forge init, P0, P1.
- 2026-11-02  Architect: docs/PRIMER.md and docs/NOTEBOOKLM_PROMPTS.md written for the user's
  NotebookLM study material. Resume PDF placed in docs/ and git-ignored.
- 2026-11-01  Explorer (Opus): Stage 1 complete on the full file, findings/ committed b8e35d0.
  Key facts: 14,608,406 banners, 485,089 customer-domain entities, 1 scan window, no buying outcome,
  17 candidates + 3 disqualifiers.
- 2026-11-01  Architect: identified the file (zstd JSONL, Shodan export), patched EXPLORATION.md
  section 0a, wrote PROMPT_EXPLORER.md.
- 2026-10-30  Architect: EXPLORATION.md written before any data was seen. ASSIGNMENT.md saved.

## Resume point
P0 done and committed (0947a3e). Next action: build cards/P1.md. P1 not started; board row P1 unclaimed.
Launchpad docs (DESIGN, DATA_MODEL, cards/*, docs/*, EXPLORATION, ASSIGNMENT, PROMPT_EXPLORER) are still staged,
not committed: that was the architect's call, left alone.
