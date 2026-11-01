# PHASE CONFIG

branch          main
deploy          fly.io, app "sis" (first deploy in card P5; nothing deploys before)
dev             uv run sis serve
audit           uv run ruff check . && uv run pytest -q -m "not llm"
typecheck       uv run mypy sis
build           none                         # docker build -t sis .  valid from P5 onward
scope guard     none
invariants      none                         # uv run pytest -q -m eval  valid from P4 onward

board           tasks/board.md               # plan checklist: tasks/todo.md
state           tasks/state.md               # newest first; resume points live here
lessons         tasks/lessons.md
bugs            none

phase naming    P0..P9, one card each in cards/P<N>.md
reviewer setup  dual (a fresh session reviews the card before build)
commit          "P<N>: <subject>" · Co-Authored-By: Claude <noreply@anthropic.com>

protected       sis_data/, data/, *.parquet, .env, docs/*.pdf, findings/ (read-only)
release gate    strix, at P5
pre-flight      do not start a card in a nearly full context; write the resume point first

skills          repo-local .claude/skills (copied from global, scoped 2026-11-02):
                python-pro python-patterns python-testing-patterns fastapi-pro data-engineer
                pydantic-models-py uv-package-manager test-driven-development
                verification-before-completion phase-forge code-reviewer security-auditor
                debugger shodan-reconnaissance
hooks           global (~/.claude/settings.json): SessionStart PreToolUse PreCompact SessionEnd
                PostToolUse already configured; none added per repo

quirks          repo is inside OneDrive: never write data under the repo. $SIS_DATA is
                C:/Users/NIRANJAN VSKS/sis_data
                Git Bash pipes can fail on multi-GB streams ("Write error: Invalid argument"):
                count lines in-process, not with wc -l
                the raw file C:\Users\NIRANJAN VSKS\Downloads\b2_download_file_by_id has no
                extension and is zstd (16.4 GB, 14,608,406 lines, 1 malformed)
                shell is Git Bash on Windows; use forward slashes and quote paths with spaces
