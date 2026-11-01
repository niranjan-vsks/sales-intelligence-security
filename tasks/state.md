# State (past tense, newest first)

- 2026-11-02  Builder (Sonnet 5.5): P1 done. Handoff report:
    P1 done. Commit f037b6c (+ handoff commit). file_id 8e252f8fadb5f0887ac6f7c59a757fc5ffc17324311b06c818abe87755a611ee-17619943483.
    Wall seconds 712.6, lines/s 20,501, compressed MB/s 24.7, workers 11, CPU 16 logical cores, RAM 23.3 GB.
    Parquet out: banners 2,269,098,353 bytes, vulns 424,266,236 bytes.
    Equivalence with explorer run: banners count ok (14,608,406), vulns count ok (20,988,468), id hash ok (3a1f30c3583da83ab2ad1c5ec994be5f both).
    Dropped: json_parse: 1 (the same "no low surrogate" line the explorer found). Second run printed status duplicate, exit 0.
    New provider fields seen: none.
    Gates: audit exit 0 (58 of 58 passed), ruff clean, mypy clean (17 files), gate 5: n/a until P5.
    Guards mutation-tested (broke, saw red, restored): parquet-vs-worker count check, tmp cleanup on failure, duplicate check, quarantine threshold.
    Deviations / spec objections:
      1. file_id is "<sha256 hex>-<byte length>", not "...:<length>": ':' is illegal in a Windows directory name and file_id names a directory.
      2. cards and DATA_MODEL say 96 banner columns; findings/02_columns.csv and the explorer output have 93. P1 emits 93 + file_id = 94. Test asserts against the csv.
      3. vulns kept the explorer's 13 columns + file_id (card: do not change the schema). DATA_MODEL 1.2 names banner_id, cvss_version VARCHAR and ransomware_campaign; the real columns are id, cvss_version DOUBLE, and ransomware_campaign lives inside other_keys JSON. P3/P4 must read id and extract it from other_keys, or the architect should rule.
      4. ingest_log status gained 'rejected' (non-zstd). read_ingest_log() returns a pyarrow Table, not a DataFrame (no pandas dep). pyyaml added as a dependency (P0).
      5. Parquet parts are one per 60 MiB block (1,9xx files of ~8k rows), not 100,000-row batches; row groups are capped at 100,000 like the explorer's.
      6. A single line larger than the 60 MiB buffer is dropped as "oversize"; none occurred.
      7. Explorer ran 1,473 s, P1 712.6 s; the card's "hours" estimate was wrong, no background wait was needed beyond ~12 min.
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
P1 done (handoff above). Full ingest output at $SIS_DATA/8e252f8f...-17619943483/ (banners, vulns, key_inventory.json); docs/INGEST_REPORT committed.
Next action: build cards/P2.md (the architect asked for a fresh Opus review of P2 first; the overnight instruction said to build it anyway).
Launchpad docs still staged, not committed.
