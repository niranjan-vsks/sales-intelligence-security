# DESIGN.md

Sales intelligence platform for a cybersecurity software vendor, built from
a Shodan banner export. This is the architecture and the write-up the
assignment asks for. Every number here comes from `findings/` (the
full-file profile done before any code) or from a build report under
`docs/`, each of which names the script or command that produced it.

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

Specified in cards/P2.md. The rule, and why it fits this data:

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
  malware tags, operator domains. The `*-rat` probe modules are not
  detections (16 of 31,763 such rows on Google IPs carry any payload) and
  are ignored.

What is lost: entities that are only reachable through a CDN
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
prerequisite = C_live_web or C_admin_services > 0 or C_asset_tags > 0 or C_any_service

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

Labels use the same banner scope as scoring: the vulnerability labels skip
CDN and WAF edge banners, whose findings are the edge vendor's (P3.1).

| Label | Entities with it (P3.1, of 487,133 active) | What it says | What it cannot say |
|---|---|---|---|
| label_kev | 49,844 (10.23%) | a version-inferred CVE is on the CISA exploited list | whether the host is exploitable; downstream of fact A, partly circular |
| label_verified | 669 (0.14%) | the provider tested and confirmed a CVE | nothing about the 99 percent untested |
| label_heartbleed | 44 (0.01%) | an active test found Heartbleed | 1 CVE only |
| label_opts_vulns | 669 (0.14%); 657 of them also verified | provider-run vulnerability probes hit | tiny coverage |
| label_any_tested | 681 (0.14%), union of the 3 above | the honest exam: labels that came from a test, not a version string | small, so wide confidence intervals |
| label_has_vendor | 77,530 (15.92%); Stage 1 counted 83,779 before the edge rule | already a customer of someone | budget, satisfaction, product |

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

Measured on the first file at scoring_version 1.1.0 (P3.1,
`docs/EVAL_REPORT_<file_id>.md` and `docs/P3_1_REPORT.md`), ranking by
`priority`, Wilson 95 percent intervals:

| label | p@100 | p@1,000 | p@10,000 | lift@1,000 | rank-biserial |
|---|---|---|---|---|---|
| label_any_tested | 3.0% [1.0, 8.5] | 3.9% [2.9, 5.3] | 1.6% [1.3, 1.8] | 27.9 | 0.597 |
| label_kev | 55.0% [45.2, 64.4] | 49.1% [46.0, 52.2] | 62.6% [61.6, 63.5] | 4.8 | 0.917 |

At k = 1,000 on label_any_tested: random 0.12%, breadth_only 3.4%,
cve_count_only 3.3%; ablations no_A 2.8%, no_B 2.3%, no_C 2.3%, no_D
4.5%. The top of the list is about 28 times richer in
tested vulnerabilities than chance. The full model now edges past
breadth_only (3.9% against 3.4%), but the intervals overlap, so on
precision@1,000 it still does not clearly beat it; it separates on
rank-biserial, 0.597 against 0.124, which means it orders the whole list
far better than counting services does. Removing D (the segment
multipliers) still raises precision@1,000 (4.5% against 3.9%), so the
multipliers still cost precision on tested labels, though less than at
1.0.0 (6.6% against 5.1%). The P3.1 fixes lowered the headline
precision: the hosting zones they removed held many tested positives,
which is why they ranked high, and they were not prospects. Untouched
only, p@1,000 on label_any_tested is 3.4% [2.4, 4.7] against a 0.19%
base rate.

Limits: label_kev is downstream of the
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
row, and free to run. The assignment asks us to prove any LLM right and
to state its cost; the cleanest proof is not needing one where rules
suffice. An LLM would have added cost, nondeterminism and an
explainability gap to a step that regexes and provider tags already do
with 100 percent reproducibility.

**As submitted, the product makes no LLM calls.** 2 uses were designed,
specified as build cards and left unbuilt inside the 5 days, by choice:
the ranking, its evaluation, the hosted app and the multi-file diff came
first, because they are what the assignment grades. What exists in the
repo is the model gateway configuration (`config/llm_tiers.yaml`, its
validated loader `sis/llm/tiers_config.py`) and the 2 cards
(cards/P7.md, cards/P8.md) with their validation protocols and cost
accounting.

### 7.1 The tiered model gateway (configured, not exercised)

No code would name a model. Every LLM call names a task, and
`config/llm_tiers.yaml` maps the task to a tier and the tier to a short
ordered list of models reached through 1 OpenAI-compatible router:

| Tier | Intended for | Models (2 per tier, ids verified on OpenRouter on 2026-11-02) | Rate limit | Budget |
|---|---|---|---|---|
| reasoning | judging report cards | frontier class | 20 rpm, 2 concurrent | 2.5 USD |
| mid | writing report card explanations | Sonnet or DeepSeek class | 60 rpm, 4 concurrent | 4.0 USD |
| errand | classifying 5,000 businesses | Haiku class or a free route | 120 rpm, 8 concurrent | 3.5 USD |

The gateway design adds 5 things a bare API call lacks: client-side rate
limiting per tier; a hard budget per tier plus a reserve, where a
projected overrun stops the run rather than shrinking it; provider-side
fallback to the tier's 2nd model; 1-step escalation to the next tier
when output fails schema validation twice; and a log row per attempt
with tier, model used, tokens, cost, latency and status.

### 7.2 What does this business do (designed, cards/P7.md)

The scan says a business is exposed but not what it is. The flattened
data keeps the page title, certificate organisation, detected web
components, server header, hostnames and the first 2,000 characters of
each HTTP response. A classifier on the errand tier would read those for
the top 5,000 accounts by priority and return a fixed-taxonomy industry,
a 1-line description and a confidence. Validation: 200 hand-labelled
accounts from the same inputs, a 50-account relabel for label noise, a
ship threshold of 0.80 industry accuracy, and the same labelled set run
through every errand model and the mid primary so accuracy and cost per
account are compared side by side before a tier is chosen.

### 7.3 Report card explanations (designed, cards/P8.md)

When a salesperson marks an account as a prospect, a report card is
rendered from our own findings and evidence; that part is deterministic.
The LLM's bounded job would be 2 plain sentences per finding, "what it
means" and "what to do", from the evidence JSON only. No web browsing, no
scanning of the prospect: scanning a third party is legally grey for a
security vendor, and open-ended research is where hallucination lives. A
deterministic faithfulness check rejects any output naming a product, CVE,
number or signal absent from the input; 50 cards judged on the reasoning
tier against 30 human-scored cards for judge calibration; cost per card
logged.

### 7.4 What was considered and rejected

- LLM-written outreach emails: excluded by the assignment.
- LLM-chosen weights or signals: no ground truth to validate against.
- LLM parsing of banners into signals: deterministic rules already do it.

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

Measured for P6 on the real file and its simulated successor (487,133 and
476,560 active entities, 148,368 events): the diff takes 38 to 93 seconds
over 4 runs (37.8, 43.1, 45.5 and 93.1 s; the slower ones while other
processes were using the machine), and writing the second synthetic delivery took 762 s (1,782 s on
a rerun under load), its ingest 786 s, resolve 193 s and score 267 s. The
diff reads two files' entity, score, signal and evidence tables plus the
banners' ip, port and module columns, so it scales with entities and
attributed banners, not with the 14.6 million raw rows. Both output tables
are byte-identical on a rerun, and rerunning the synth with the same seed
gave the same file_id.

## 9. Hosting and cost

Deployed: 1 Fly.io machine (shared-cpu-1x, 1 GB RAM, region fra, always on)
running the FastAPI app with the serve bundle baked into the Docker image,
live at https://sis-niranjan.fly.dev/ since 2026-11-03. Cost: 7.73 USD a
month for the started machine in fra (6.70 USD in the cheapest regions),
from https://docs.fly.io/about/pricing on 2026-11-03; the shared IPv4 and
registry image storage are free, outbound data transfer is extra and not
measured. No database service, no
object storage, no secrets (Logfire is optional and unset).

Zero-cost alternative recorded in P5: Render free web service with
spin-down after inactivity. Rejected as primary only because the first
request after idle takes tens of seconds, which is a bad demo.

Why not a hosted Postgres free tier: the evidence table alone approaches
the 0.5 GB ceiling of the common free tiers, and the API needs nothing a
Parquet file plus DuckDB cannot do.

## 10. The dev loop

The assignment says how we build is judged as much as what we ship. This
is how it was built.

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
first true labels this system has. Section 6's metrics are
designed to accept them as a 7th label without code changes.

## 11. Deliberate cuts

- Outreach email drafting: the assignment says it is not the interesting
  part. Not built.
- UI polish: server-rendered tables and 1 detail page. Enough to find,
  filter, sort, open and read evidence. Not more.
  Screenshots: docs/ui/ (listed in docs/UI_REPORT.md). The UI stays
  minimal on purpose: 1 readability pass after the first live walk
  (overview page, plain-language reasons, dark and light themes), no
  framework and no build step.
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
  exposure we cannot see. The segment is named for what we can see.
- Hosting providers at the top, found by the evaluation and fixed in
  P3.1. At scoring 1.0.0, 95 of the top 100 by priority were hosting or
  network operators (OVH per-/24 reverse-DNS zones such as
  `ip-15-235-134.net`, hosters such as hostinguk.net): each covered
  under 50 IPs, so P2 kept it as a customer, while it aggregated many
  tenants' servers. P4 also showed that `low_surface` held tested
  positives at the same rate as `untouched`, and that 1,192 kev labels
  came only from CDN or WAF edge banners. 3 rulings followed: hosting
  zones become operators (a template-zone rule, a templated-hostname
  rule, and a hand list of 129 names read from the top 100 twice); the
  prerequisite gains `C_any_service`, so `low_surface` now means nothing
  of theirs answered (163,897 to 5,613 entities); labels skip edge
  banners, as scoring does. After the fixes the top 30 holds no hosting
  provider, but 57 of the top 100 still do: the 2 rules catch names built
  from addresses, not hosters that number their servers (server123,
  vm612). The target of under 10 in 100 is not met; a wider rule is an
  open item, not built.
- 1 scan window: nothing in this submission demonstrates a real diff.
  P6 proves the diff on a synthetic second file built by perturbing the
  real one with a seed, and the UI and reports say it is a simulation.
  Recall of the planted changes at entity grain: 3 of 5 change types meet
  their bar; certificate expiry sits at 94.9 percent against a 95 percent
  bar and added vulnerabilities at 73.6 percent, every miss in a named
  category (docs/DELTA_REPORT_*.md).
- The 2 LLM features (section 7) are designed and configured, not built.
- The release security gate (strix) was not run before submission.
