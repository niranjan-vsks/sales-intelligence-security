# Build cards

Build in this order. P0 to P5 are the complete submission. P6 to P9 add
depth and each one is independently skippable.

| Card | Builds | Model | Day | Skippable |
|---|---|---|---|---|
| P0 | scaffold, config, CLI stubs, fixtures, CI | Sonnet 5.5 | 1 am | no |
| P1 | idempotent ingest, malformed handling, throughput numbers | Sonnet 5.5 | 1 pm | no |
| P2 | entity resolution, operators, blocked, fallbacks | Opus 5.5 | 2 am | no |
| P3 | signals, evidence, peer-relative scores, segments | Opus 5.5 | 2 pm | no |
| P4 | evaluation harness, baselines, ablations, CI threshold | Opus 5.5 | 3 am | no |
| P3.1 | hotfix after P4's eval: hosting zones as operators, wider prerequisite, label scope | Opus 5.5 | 3 pm | no |
| P5 | bundle export, FastAPI, minimal UI, Fly deploy, Logfire | Sonnet 5.5 | 3 pm to 4 am | no |
| P6 | synthetic second file, delta, events, "Changes" in UI | Sonnet 5.5 | 4 | yes |
| P7 | LLM industry classifier, labelled eval, cost | Sonnet 5.5 | 4 pm | yes |
| P8 | report card, LLM explanations, faithfulness check, judge | Sonnet 5.5 | 5 am | yes |
| P9 | MCP server, trajectory evals | Sonnet 5.5 | 5 pm | yes |

If day 4 runs out: ship P0 to P5. DESIGN.md already describes P6 to P9 as
design; mark them "designed, not built" in the write-up.

## Prompt to start a builder session

Paste this as the first message of a fresh Claude Code session in the
repo, replacing `<N>`.

```
You are the BUILDER for card cards/P<N>.md in this repo. Read, in this order:
cards/README.md, cards/P<N>.md, DESIGN.md, DATA_MODEL.md, and the files the
card lists under "Read first". Then build exactly what the card specifies.

Rules:
1. The card is the contract. If it is ambiguous, pick the reading that is
   simplest and write the choice under "Deviations" in your handoff report.
   If it is wrong (a column does not exist, a number does not reconcile),
   stop and report; do not improvise a different design.
2. Do not touch findings/. Do not commit anything under $SIS_DATA.
3. Constants live in config/, never in code. Paths come from sis/paths.py.
4. Every acceptance test in the card must pass before you report. Paste
   the actual command output for each, not a summary.
5. Write tests first for pure functions; integration tests may come after.
6. Numbers in reports come from queries you ran, never from memory or
   estimate. If a number cannot be measured, write "not measured" and why.
7. Keep tasks/lessons.md updated: any time the human corrects you, add the
   pattern and the rule that prevents it.
8. Commit in small steps with messages prefixed "P<N>:". Do not push.
9. When done, print the handoff report in the card's exact format.
```

## Verification by the human between cards

Run the acceptance tests listed in the card yourself. Read the handoff
report. If anything says "deviation", decide whether to accept it. Only
then start the next card. Paste the handoff report to the architect
session when a decision is needed.
