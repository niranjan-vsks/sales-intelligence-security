# Lessons

- The brief said the assignment was pasted but it was not. Flag missing inputs up front and mark everything derived from a paraphrase as an assumption.

- 2026-11-02: User asked "why Anthropic?" and I started rewriting 5 spec files before answering fully. Rule: a why question gets an answer and a proposal. Specs change only after the user confirms, even after bullseye, when the change was not in the agreed design.

- 2026-11-02 (builder): I overwrote the architect's tasks/state.md with a shell heredoc because my earlier `ls` was stale (the file appeared after it). Recovered from the git index. Rule: before creating any file with a shell redirect, `git status --short <path>` or `ls` it in the same command; prefer the Write tool (which refuses to overwrite an unread file) for anything that might exist.
- 2026-11-02 (builder): a long multi-heredoc bash command failed to parse as a whole and created nothing. Rule: write source and config files with the Write tool; keep bash for running things.
- 2026-11-02 (builder): mutation-testing a file with `git checkout --` silently reverted an uncommitted edit to the same file (the SQL fix for fallback eligibility) and I only noticed from `git status`. Rule: commit every change before starting mutation tests; restore mutations from a copy or from a clean commit, then check `git status` is empty afterwards.
- 2026-11-02 (builder): "\n" inside a Python snippet in a bash heredoc turned into a real newline in the written source, twice. Rule: do multi-line string edits with the Edit tool, not python-in-bash.
