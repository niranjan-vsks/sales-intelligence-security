# DESIGN.md

Sales intelligence platform for a cybersecurity software vendor, built from
a Shodan banner export. This is the architecture and the write-up the
assignment asks for. Every number here comes from `findings/` (Stage 1,
full-file profile) or will be filled in by the build card that measures
it; such places are marked `[P<n> fills]`.

Companion documents: DATA_MODEL.md (tables), cards/P0..P9 (build order),
EXPLORATION.md and findings/ (how the data was understood first).

---

## 1. The problem, as the data reframes it

The assignment: rank the businesses most likely to buy cybersecurity
software, from 1 raw file, and design for hundreds to thousands of such
files a month.

The file: 14,608,406 service banners from a Shodan scan, 16.4 GB zstd,
122.8 GB decompressed, 1 scan window of 18.9 hours with 95.7 percent of
rows in 1 hour. Not a company table. 62.4 percent of rows belong to 5
network operators; Incapsula alone is 31.9 percent. Only 7.36 percent of
rows (1,074,635) resolve to a named customer domain, giving 485,089
entities.

So the real tasks are, in order:

1. Turn banners into businesses (entity resolution), and refuse to score
   what is not a business.
2. Measure each business's visible security posture from what the
   scanner saw, relative to its peers.
3. Separate "has nothing" from "already bought from someone", because
   those are different sales plays.
4. Show the evidence, since a score nobody can defend on a call is
   useless.
5. Make "right now" mean something, which inside 1 file it cannot, so
   design the monthly diff.
6. Prove the ranking is better than random without any sales outcome in
   the data.

## 2. Architecture

```
 raw delivery (zstd JSONL, 1 file)
        |
        v
 [P1 ingest]  stream -> flatten -> Parquet (banners, vulns) + ingest_log
        |          idempotent on file_id, quarantine on malformed
        v
 [P2 resolve] banners -> banner_entity -> entities (+blocked, +unattributed_summary)
        |
        v
 [P3 score]   signals -> evidence -> scores   (deterministic, peer-relative)
        |
        +--> [P4 evaluate]  held-out proxies -> metrics.json, ablations, baselines; pytest -m eval in CI
        |
        +--> [P6 delta]     entity_history + events across consecutive files
        |
        +--> [P7 classify]  LLM industry/description for top-N, cached, costed
        |
        v
 [export]     serve bundle (accounts, evidence, events, signals, bundle.json)
        |
        v
 [P5 app]     FastAPI + DuckDB over the bundle, Jinja2/htmx UI, Logfire traces
        |
        +--> [P8 report card]  on-demand LLM explanations over our own evidence, faithfulness-checked, costed
        |
        +--> [P9 MCP server]   same read API as tools for an agent, trajectory evals
```

Offline versus live: layers 1 to 5 of DATA_MODEL.md are batch. The hosted
app reads 1 bundle of a few hundred MB and nothing else. The 123 GB never
leaves the pipeline machine or, in production, object storage.

Stack: Python 3.12, DuckDB, pyarrow, pydantic v2, pydantic-settings,
typer (CLI), FastAPI, Jinja2 + htmx (UI), logfire (tracing, falls back to
console OpenTelemetry if no token), pytest, ruff, uv. LLM calls through the
Anthropic SDK with structured output validated by pydantic.

## 3. Ingestion

Specified in cards/P1.md. The properties that matter at 1,000 files a
month:

- **Identity.** `file_id` = sha256 of the first 64 MiB, then the byte length.
  Computed before decompression, in seconds. A re-delivered file with the
  same `file_id` is logged `duplicate` and skipped. A file with a new
  `file_id` but identical banner ids (a renamed re-delivery) is detected at
  P2 merge time: banner ids are globally unique, so the merge upserts and
  the ingest report says "0 new banners".
- **Streaming.** zstd is decompressed as a stream into worker processes
  that each own a 60 MiB block of lines; nothing is held beyond that
  block. Measured on a 16-core, 23 GB laptop with 11 workers: 14,608,407
  lines in 712.6 seconds, 20,501 lines per second, 24.7 MB per second of
  compressed input, 2.27 GB of banner Parquet and 0.42 GB of vulns Parquet
  out. A second run of the same file prints `duplicate` and writes
  nothing. Output was verified byte-equivalent in row count and id hash
  to the independent exploration run.
- **Malformed input.** 3 outcomes, all logged per file in `ingest_log`:
  a line that fails JSON parse or lacks `_shodan.id` is dropped and
  counted (the real file has exactly 1 such line); a file whose first 1,000
  lines contain more than 1 percent failures is quarantined before any
  output is written; a file that is not zstd or not JSONL is rejected at
  the magic-byte check.
- **Atomicity.** Output goes to `$SIS_DATA/<file_id>.tmp/` and is renamed
  to `$SIS_DATA/<file_id>/` only after row counts reconcile with lines
  read minus dropped. A crash leaves no partial file visible.
- **Schema drift.** The flattener extracts a fixed set of paths and
  stashes every unknown top-level block in `extra_json`. New provider
  fields never break ingest; they show up in a per-file key inventory the
  ingest report prints, so the next pipeline version can promote them.

## 4. Entity resolution

Specified in cards/P2.md. The rule is simple and the write-up says why it
is right for this data:

- `org` and `asn` are determined by the IP (functional dependency 100
  percent in findings/06_relationships.md). They name the landlord. Using
  them ranks Incapsula and Google.
- `domains` (reverse DNS registered domain) is the only name that is
  populated on 74.1 percent of rows and is specific to a tenant. A domain
  that covers more than 50 IPs in the file is an operator zone (incapdns.net
  covers 54,411). The cutoff is `ROLLUP_MAX_IPS`, a setting, default 50;
  the explorer's table at 10, 50 and 250 shows the entity count barely
  moves (476,598 to 487,512) while the attributed rows grow, so the
  choice trades precision for recall at the margin only.
- Fallbacks recover some of the 92.6 percent: certificate subject names
  (populated on 6.7 percent of rows, 91 percent functionally consistent
  with `domains`) and `http_host` (29.5 percent) when it is a name. As
  built: 481,186 domain entities, plus 12,643 from certificate names and
  1,600 from Host headers, for 495,429 active entities and 532 blocked;
  fallbacks attributed 38,433 more banners. 92.46 percent of banners
  remain unattributed: 9.73 million are operator-only names and 3.78
  million have no name at all.
- A known weakness, found in the eyeball check: a tenant behind a shared
  Incapsula edge is named correctly but its banners describe the edge,
  not the tenant. The scoring layer therefore treats "edge banners" (CDN
  tag or a W01 WAF name) as evidence of protection only, never of
  exposure (section 5.5).
- Blocked, never scored: honeypot or scanner tags (250,530 rows), C2 or
  malware tags, operator domains. The write-up states explicitly that the
  `*-rat` probe modules are not detections (16 of 31,763 such rows on
  Google IPs carry any payload) and are ignored.

What is lost and said so: entities that are only reachable through a CDN
show up as the CDN. For those, the only recoverable fact is "this domain
is behind Incapsula or Cloudflare", which is itself the negative signal
(section 5, fact D), and it is attributed to the customer domain when
reverse DNS or the certificate names it.

## 5. The signal and scoring model

Specified in cards/P3.md. 17 candidates and 3 disqualifiers from Stage 1
collapse into 4 facts, because the correlation clusters (findings/
07_clusters.md) show they encode 4 underlying things. Scoring 17 columns
would count the same fact up to 6 times.

| Fact | Plain meaning | Signals (DATA_MODEL 3.1) | Stage 1 evidence |
|---|---|---|---|
| A | visibly old or vulnerable software | A_fingerprinted, A_inferred_cves, A_max_cvss, A_eol, A_os_leak, A_cpe_per_header | eol tag lifts r_vuln 25.8; cpe present lifts r_vuln 4.8; n_cpe/n_headers top decile lifts r_vuln 13.0 |
| B | neglected certificates | B_self_signed, B_expired, B_legacy_tls, B_cert_age_days | self-signed tag lifts r_certexpired 36.4; old-for-peers cert lifts r_certexpired 88.4 |
| C | exposed surface | C_admin_services, C_windows_internals, C_asset_tags, C_breadth_modules, C_breadth_ports, C_components_vs_peers, C_live_web | entity lifts r_vuln: smb 3.65, ssh 2.37; ntlm r_selfsigned 19.6; breadth top decile r_selfsigned 3.25 |
| D | protection already present | D_waf, D_security_appliance, D_edge_substitute, D_vpn, D_hardening_headers | waf present lifts r_vuln 0.18, r_eol 0.09 |

### 5.1 Peer groups

Entity-grain peer group = `country_code` x breadth bucket of `n_modules`
(1, 2 to 3, 4 to 9, 10 or more). A group under 30 entities falls back to
the breadth bucket alone, then to the whole population. Percent ranks of
continuous signals are computed inside the peer group. Reason: the explorer
showed `module x country` splits payload size, certificate age and
vulnerability counts more than any other pair (findings/07_num_vs_cat.csv);
at entity grain breadth stands in for module mix.

### 5.2 Fact scores (each 0 to 1)

Constants live in `config/scoring.yaml` with `scoring_version`. These are
the defaults. They are hand-set from the Stage 1 lifts, not fitted, because
there is no outcome to fit to; P4 measures them and the ablations say what
each fact contributes.

```
fact_a = clip( max(A_eol * 1.0,
                   A_inferred_cves > 0 ? 0.4 + 0.6 * A_max_cvss / 10 : 0,
                   A_fingerprinted * 0.25)
               + 0.15 * A_os_leak
               + 0.20 * pct(A_cpe_per_header), 0, 1)

fact_b = clip( 0.6 * B_self_signed + 0.6 * B_expired + 0.4 * B_legacy_tls
               + 0.3 * pct(B_cert_age_days), 0, 1)

fact_c = clip( 0.40 * min(C_admin_services, 3) / 3
               + 0.25 * C_windows_internals
               + 0.20 * min(C_asset_tags, 2) / 2
               + 0.25 * pct(C_breadth_modules)
               + 0.15 * pct(C_components_vs_peers), 0, 1)

fact_d = max( 1.0 * D_waf, 0.8 * D_security_appliance,
              0.5 * D_edge_substitute, 0.4 * D_vpn, 0.3 * D_hardening_headers)

exposure = 100 * (0.45 * fact_a + 0.20 * fact_b + 0.35 * fact_c)
```

`pct(x)` is the percent rank in the peer group, 0 when the signal is
absent. Weights: A highest because its lifts are largest and it is what a
security vendor sells against; C next because it is the only family with
100 percent coverage; B lowest because it is only observable on the 6.8
percent of banners with TLS and is partly a re-expression of neglect
already visible in A.

### 5.3 Segments and priority

```
prerequisite = C_live_web or C_admin_services > 0 or C_asset_tags > 0

segment = 'displace'          if D_waf or D_security_appliance
        = 'partially_covered' elif D_edge_substitute or D_hardening_headers or D_vpn
        = 'untouched'         elif prerequisite
        = 'low_surface'       otherwise

priority = exposure * { untouched: 1.0, partially_covered: 0.85,
                        displace: 0.6, low_surface: 0.5 }[segment]
```

Why segments and not a penalty: a sales team runs different plays. From
Stage 1, 131,104 entities are `untouched` with a live service and no
protection of any kind; 83,779 have a security vendor already, and for
those the incumbent is named in the evidence. Both lists are first-class
outputs.

### 5.4 Evidence

Every signal that fires stores up to 5 banners with ip, port, field, value
and a 300-character snippet of the raw banner. The UI shows them verbatim.
This is the "why" a salesperson reads, and it is also how a reviewer
catches us if a signal is wrong.

### 5.5 What the model deliberately does not use

- `module` values as detections (they are probes).
- `n_vulns` straight from the banner row: P3 recomputes it from the vulns
  table excluding `kev`, `verified` and `ransomware_campaign`, because
  those are the evaluation labels.
- `org`, `asn`, `isp`, geolocation beyond country: operator facts, not
  tenant facts. 28.6 percent of rows geolocate to 1 point.
- Anything from the `*-rat` modules or from `data` free text beyond the
  stored snippet.
- Edge banners for facts A, B and C. A banner is an edge banner when
  `list_contains(tags, 'cdn')` or its `http_waf` matches mapping W01. Such
  a banner describes the CDN or WAF vendor's shared infrastructure, so it
  feeds `D_waf`, `D_edge_substitute` and `C_live_web` only. Without this
  rule a small tenant behind Incapsula inherits the edge's breadth and
  software fingerprints.

## 6. How we know it works

Specified in cards/P4.md. There is no purchase, contact or churn field in
the file. We hold out the provider's tested or curated labels and ask
whether the ranking is rich in them at the top:

| Label | Entities with it (P4, of 495,419 active) | What it says | What it cannot say |
|---|---|---|---|
| label_kev | 53,287 (10.76%), from 282,801 banners | a version-inferred CVE is on the CISA exploited list | whether the host is exploitable; downstream of fact A, partly circular |
| label_verified | 791 (0.16%), from 4,808 banners | the provider tested and confirmed a CVE | nothing about the 99 percent untested |
| label_heartbleed | 50 (0.01%), from 160 banners | an active test found Heartbleed | 1 CVE only |
| label_opts_vulns | 791 (0.16%), from 5,085 banners; 777 of them also verified | provider-run vulnerability probes hit | tiny coverage |
| label_any_tested | 805 (0.16%), union of the 3 above | the honest exam: labels that came from a test, not a version string | small, so wide confidence intervals |
| label_has_vendor | 77,966 (15.74%); Stage 1 counted 83,779 before the edge rule | already a customer of someone | budget, satisfaction, product |

Metrics reported, each against random (base rate), a breadth-only
ranking and a CVE-count-only ranking:

- precision@100, @1,000, @10,000 by `priority`, per label
- lift at those k (precision divided by base rate)
- rank-biserial correlation between `priority` and each label
- the same with each fact removed (ablation), so the write-up can say
  which fact earns its weight
- `label_has_vendor` is used as a sanity check, not a target: the
  `displace` segment must contain it at a rate far above `untouched`, by
  construction, and the exposure distributions of the 2 segments are
  reported side by side

Measured on the first file (P4, docs/EVAL_REPORT_<file_id>.md), ranking
by `priority`, Wilson 95 percent intervals:

| label | p@100 | p@1,000 | p@10,000 | lift@1,000 | rank-biserial |
|---|---|---|---|---|---|
| label_any_tested | 10.0% [5.5, 17.4] | 5.1% [3.9, 6.6] | 2.0% [1.7, 2.3] | 31.4 | 0.481 |
| label_kev | 72.0% [62.5, 79.9] | 57.5% [54.4, 60.5] | 61.8% [60.8, 62.8] | 5.3 | 0.854 |

At k = 1,000 on label_any_tested: random 0.14%, breadth_only 5.1%,
cve_count_only 3.3%; ablations no_A 4.6%, no_B 3.9%, no_C 2.6%, no_D
6.6%. The full model beats cve_count_only but the intervals overlap, and
ties breadth_only. Removing D (the segment multipliers) raises precision
on every vulnerability label, likely because `low_surface` (x0.5) holds tested
positives at the same rate as `untouched`. Untouched only, p@1,000 on
label_any_tested is 4.2% [3.1, 5.6] against a 0.21% base rate.

The honest limits, stated in the write-up: label_kev is downstream of the
same version strings fact A reads, so a high score there partly proves we
can read a version string. The tested labels are independent but number
in the low thousands. Neither says anyone bought anything. The only true
test is the sales team's reply rate after a month of use, and the design
reserves a place for it (section 10).

CI: `pytest -m eval` recomputes the metrics on a committed 50,000-entity
fixture and fails if precision@1000 on label_any_tested falls below the
committed value, so a scoring change that silently degrades the ranking
cannot merge.

## 7. LLM use: where, why, how validated, what it costs

Scoring uses no LLM. Every signal is a deterministic predicate on
structured fields, which makes the ranking reproducible, explainable per
row, and free. The assignment asks us to prove any LLM right and to state
its cost; the cleanest proof is not needing one where rules suffice.

2 places genuinely need reasoning over messy text, and both are built as
bounded, cached, schema-validated, logged calls through 1 component:

### 7.0 The tiered model gateway

No code names a model. Every LLM call names a task, and
`config/llm_tiers.yaml` maps the task to a tier and the tier to a short
ordered list of models reached through OpenRouter:

| Tier | Used for | Models (2 per tier, verified on build day) | Rate limit | Budget |
|---|---|---|---|---|
| reasoning | judging report cards | frontier class (Kimi K3 or Claude Sonnet class) | 20 rpm, 2 concurrent | 2.5 USD |
| mid | writing report card explanations, driving the MCP agent | Sonnet or DeepSeek V4 class | 60 rpm, 4 concurrent | 4.0 USD |
| errand | classifying 5,000 businesses | Haiku class or a free Qwen or DeepSeek route | 120 rpm, 8 concurrent | 3.5 USD |

The gateway does 5 things that a bare API call does not: client-side
rate limiting per tier; a hard budget per tier plus a reserve, totalling
the 12 USD available for the whole assignment, where a projected overrun
stops the run and asks for a top-up rather than shrinking the work; provider-side fallback to
the tier's 2nd model when the 1st errors or is unavailable, using
OpenRouter's model fallback list; 1-step escalation to the next tier when
the output fails schema validation twice; and a log row per attempt with
tier, model actually used, tokens, cost, latency and status. The P7 eval
runs the classifier on every errand model and the mid primary and reports
accuracy and cost side by side, which is the evidence that the errand
tier is the right tier for that task.

Free routes are permitted. Their rate limits and data-use terms are
recorded in the report; the inputs are public scan data.

### 7.1 What does this business do (cards/P7.md)

The scan says a business is exposed but not what it is. The flattened
data keeps `http_title`, `cert_subject_o`, `http_components`,
`http_server`, hostnames, and the first 2,000 characters of each HTTP
response (`data`), which includes the start of the page. A classifier
reads those for 1 entity and returns `{is_business, industry (fixed
taxonomy), description <= 160 chars, confidence}`.

- Tier: errand. Runs on the top `CLASSIFY_TOP_N` entities by priority
  (default 5,000; a dry-run projection above the tier budget stops the
  run and requests a top-up, it never lowers N), not on 485,089.
- Validation: 200 entities hand-labelled by the builder from the same
  inputs (`evals/industry/labels.jsonl`). Reported: accuracy on industry,
  precision and recall on `is_business`, and agreement on a 50-entity
  re-label by a second pass 1 week later for label noise. Threshold to
  ship: industry accuracy at or above 0.80 on the labelled set; below that
  the field is shown as "unclassified".
- Cost: every call logs input and output tokens and USD at the model's
  list price into `llm_calls`. The write-up reports mean cost per entity
  and total for the run `[P7 fills]`. Cache by `input_hash` so re-runs
  cost 0.

### 7.2 Report card explanations (cards/P8.md)

When a salesperson marks a lead as a prospect, the app renders a report
card from our own evidence. The deterministic part is the findings, the
evidence rows and the peer comparison. The LLM's bounded job is 2 plain
sentences per finding, "what it means" and "what to do", for a
non-technical reader.

- Input is only the entity's evidence JSON. No web browsing, no scanning
  of the prospect, no outside sources. The write-up says why: scanning a
  third party is legally grey for a security vendor, and open-ended
  research is where hallucination lives.
- Output is a pydantic schema. A deterministic faithfulness check rejects
  any output that mentions a signal id, product name, CVE or number not
  present in the input.
- Tiers: generation on mid, judging on reasoning, and the config loader
  asserts the 2 primaries are different model families.
- Validation: 50 report cards judged on the reasoning tier on a 3-point
  rubric (faithful, specific, readable), calibrated against 30 of the same
  cards judged by the builder; judge agreement with human reported.
- Cost per report card logged and reported `[P8 fills]`. Generated on
  demand only, persisted, never regenerated for the same evidence hash.

### 7.3 What was considered and rejected

- LLM-written outreach emails: excluded by the assignment.
- LLM-chosen weights or signals: no ground truth to validate against.
- LLM parsing of banners into signals: regexes and provider tags already
  do it deterministically with 100 percent reproducibility.

## 8. Scale: 1,000 files a month

Measured on the laptop for 1 file: 712.6 seconds of ingest at 20,501
lines per second, about 3.5 minutes of entity resolution, 2.7 GB of
Parquet out. So 1 laptop-class machine ingests about 120 such files a
day, and 1,000 a month (33 a day) is within a single worker's capacity
for the per-file stages. The design is per-file isolated through P3, so
files parallelise trivially anyway; the merge to current state and the
diff are the only cross-file steps, and they are where the real limits
are.

What breaks first, and the next move for each:

1. **Single machine throughput** is not the first break: 33 files a day
   at 12 minutes each is about 7 machine-hours. It breaks when files
   cluster (a month's delivery landing in 1 day) or when the file size
   grows. Next move, needed anyway for isolation: files land in object
   storage (S3 or R2), a queue (SQS) hands 1 file to 1 worker, workers
   are stateless containers of the same image. Nothing in P1 to P3
   changes.
2. **Storage** is the first real break. 2.7 GB Parquet per file is 2.7
   TB a month of layer 1, and the 16 GB raw files are 16 TB a month.
   Next move: keep layer 1 in object storage with a 90-day lifecycle, keep
   layers 2 and 3 (tens of MB per file) indefinitely, and the history in a
   warehouse (Snowflake or ClickHouse) rather than Parquet-on-disk.
3. **Current-state merge.** Today it rebuilds `current/` from all per-file
   tables. Next move: merge is an upsert keyed by `entity_id` touching only
   entities present in the new file, with `last_seen_file` deciding
   staleness; entities unseen for `N` files are marked `stale`, not
   deleted.
4. **Serving.** DuckDB in-process over a bundle is fine to low millions of
   evidence rows. Beyond that, the bundle becomes a Postgres database
   loaded by the export step, API unchanged.
5. **Duplicates and overlap.** Hundreds of files a month will re-observe
   the same services. Banner ids are unique per observation, so the diff
   layer (P6) keys on `entity_id` + `ip:port` and treats repeated
   observations as "still present", not "new".

## 9. Hosting and cost

Target: 1 Fly.io machine (shared-cpu-1x, 1 GB RAM) running the FastAPI
app with the serve bundle baked into the Docker image. Expected cost on the
order of 5 USD a month at the published rate; P5 records the exact figure
from the pricing page on deploy day `[P5 fills]`. No database service, no
object storage, no secrets beyond the Logfire and Anthropic keys.

Zero-cost alternative recorded in P5: Render free web service with
spin-down after inactivity. Rejected as primary only because the first
request after idle takes tens of seconds, which is a bad demo.

Why not a hosted Postgres free tier: the evidence table alone approaches
the 0.5 GB ceiling of the common free tiers, and the API needs nothing a
Parquet file plus DuckDB cannot do.

## 10. The dev loop

The assignment says how we build is judged as much as what we ship. This
is how it was built, honestly.

**3 roles, 3 kinds of session.**

1. Architect (Claude Fable, this document's author). Wrote EXPLORATION.md
   before seeing any data, read only compact findings, wrote this design,
   DATA_MODEL.md and the cards. Wrote 0 lines of application code.
2. Explorer (Claude Opus). Executed EXPLORATION.md against the full file.
   Every number in findings/ traces to a script in findings/queries/.
   Caught and documented 2 of its own errors before committing (a
   placeholder rule that mislabelled `na`, and a null-handling bug in the
   lift baselines).
3. Builders (Claude Sonnet or Opus per card). Each takes 1 card, builds to
   its acceptance tests, and returns a fixed-format report. Model choice
   per card is recorded in the card.

**The rule that shaped the signals.** No signal was allowed from prior
knowledge of security buyers. Each had to come out of a measurement on the
file with a lift number attached. That is the opposite of pasting the file
into a chat and asking for signals, which the assignment warns against,
and it is why the model has 4 facts instead of a list of 20 plausible
columns.

**The card contract.** Every card states inputs, outputs with exact paths
and schemas, numbered steps, acceptance tests as runnable commands with
expected assertions, what it does NOT do, and a handoff report format.
The human runs the acceptance tests before the next card starts.

**What was automated.** Profiling (scripted, reproducible), ingestion
verification (row count reconciliation), evaluation (pytest in CI with a
threshold), LLM validation (labelled sets, judge calibration), model
routing and cost control (the tiered gateway: rate limits, budgets,
fallback, escalation, every call logged with tier, model, prompt version,
tokens, USD).

**What was not automated and why.** Choosing the 50-IP cutoff, the fact
weights and the segment multipliers. These are judgement calls on a
distribution with no outcome to fit; they are written down as settings
with the reasoning, and the ablations show what each one does.

**Lessons file.** `tasks/lessons.md` records every correction made during
the build, by whom, and the rule derived from it.

**What a month of real use would add.** The UI has a 1-click "mark as
prospect" and "mark as not a fit" per account. Those 2 buttons are the
first true labels this system will ever have. Section 6's metrics are
designed to accept them as a 7th label without code changes.

## 11. Deliberate cuts

- Outreach email drafting: the assignment says it is not the interesting
  part. Not built.
- UI polish: server-rendered tables and 1 detail page. Enough to find,
  filter, sort, open and read evidence. Not more.
- Live scanning or web research on prospects: legal exposure and
  hallucination risk; the report card uses only our own evidence.
- People data: none in the file.
- Hosting the raw 123 GB: never.

## 12. Risks and open items

- `ROLLUP_MAX_IPS` is a judgement. Recorded as a setting, shown in the UI
  footer with the bundle version.
- Fact A is partly circular with label_kev. Reported with ablations and
  with the tested labels alongside.
- Entities behind a CDN are under-observed, so `low_surface` may hide real
  exposure we cannot see. The segment is named for what we can see, and
  the write-up says so.
- 1 scan window: nothing in this submission demonstrates a real diff.
  P6 proves the diff on a synthetic second file built by perturbing the
  real one with a seed, and the write-up says it is a simulation.
