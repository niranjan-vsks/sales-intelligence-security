# Spec audit: DESIGN.md, DATA_MODEL.md and README.md against the code

Date 2026-11-04. Baseline commit a2eda12. Every line number below points at
the 3 documents as they were at that commit, before this audit corrected
them.

## Scope and method

Every concrete claim in the 3 documents was checked: each rule, formula,
threshold, table column, measured number, command, and feature described
as built. A claim is VERIFIED only when a specific line backs it. That line
can be in code (`sis/`, including SQL and templates), config (`config/`,
`pyproject.toml`, `Dockerfile`, `fly.toml`, CI), tests, a build report
under `docs/`, or, for exploration numbers, `findings/`.

Code, config, tests, templates and `findings/` were read only and not
changed. Nothing under `$SIS_DATA` was opened. Numbers from the data come
from the committed reports. The live URL was not fetched. 1 command was
run: `pytest --collect-only`, to count tests. The 3 documents were edited
only to correct FALSE claims and to mark NOT BUILT items. All 65 such rows
are corrected in this commit.

Verdicts:

- **FALSE**: the code, config or a report contradicts the claim.
- **NOT BUILT**: the claim is stated or implied as built, and no code implements it.
- **UNVERIFIED**: no line in the repo supports or contradicts the claim.
- **VERIFIED**: evidence was found.

Report names are shortened. `*_8e25...md` is the real delivery, file_id
8e25...-17619943483. `*_61ea...md` is the simulated second delivery.

## Counts

| Document | FALSE | NOT BUILT | UNVERIFIED | VERIFIED | Total |
|---|---|---|---|---|---|
| DESIGN.md | 27 | 5 | 9 | 152 | 193 |
| DATA_MODEL.md | 18 | 12 | 1 | 135 | 166 |
| README.md | 3 | 0 | 4 | 61 | 68 |
| **All** | **48** | **17** | **14** | **348** | **427** |

What matters most among the corrections:

1. **The CI eval gate cannot catch a scoring regression.** The committed
   fixture stores finished priorities. `tests/test_eval.py` re-sorts them
   and never runs scoring, so a change to `config/scoring.yaml` or the
   scoring SQL cannot fail it. DESIGN.md said such a change "cannot merge".
   Rows 19 and 45.
2. **The LLM layer was drawn and listed as if it existed.** This covered
   P7, P8 and P9 in the architecture diagram, the "what was automated"
   list, all of DATA_MODEL layer 5, and the claim that LLM calls use the
   Anthropic SDK. The dependency is in fact `openai`, pointed at
   OpenRouter. Rows 3, 49 to 51, 53 and 61 to 65.
3. **Some entity numbers predated the P3.1 rerun.** DESIGN.md section 4
   said 495,429 entities. The current figure, used everywhere else, is
   487,133. Rows 7 to 9.
4. **Several rules about what the model leaves out were wrong.**
   - Module names are read: `D_vpn` and `C_any_service`.
   - `*-rat` banners count toward breadth.
   - Edge banners still shape the peer group.
   - `ransomware_campaign` is not excluded from scoring.

   Rows 10 and 14 to 17.
5. **The "every table is traceable" convention holds only for some
   tables.** It covers the P2 and P3 per-file tables and the bundle. Rows
   54 to 60.

## Audit table

| # | Claim | Location | Verdict | Evidence |
|---|---|---|---|---|
| 1 | "16.4 GB zstd" | DESIGN.md:L20 | FALSE | `docs/INGEST_REPORT_8e25...md:8` byte length 17,619,943,483 = 17.6 GB (16.4 GiB). Same paragraph's "122.8 GB decompressed" (`findings/00_format.md:8`, 122,782,583,953 bytes) and L97 "24.7 MB per second" are decimal units, so 16.4 is the odd one out. `findings/00_format.md:4` has the same GiB/GB slip. |
| 2 | "The hosted app reads 1 bundle of a few hundred MB" | DESIGN.md:L73-74 | FALSE | `docs/DEPLOY.md:31` deployed bundle `size_mb 156.6`; `tasks/state.md:8` latest re-export 162.5 MB. About 160 MB, not a few hundred. (The "1 bundle, nothing else" part holds for data: `sis/api/app.py:31-39,63-64`; the About page also reads `DESIGN.md`, `sis/api/routes.py:333`.) |
| 3 | "LLM calls through the Anthropic SDK with structured output validated by pydantic" | DESIGN.md:L79-80 | FALSE | `pyproject.toml:12` depends on `openai>=3.42.1`; no `anthropic` dependency or import anywhere in `sis/`. `sis/config.py:423-424` `OPENROUTER_API_KEY`, `LLM_BASE_URL = "https://openrouter.ai/api/v1"`; `sis/llm/tiers_config.py:40` `router: Literal["openrouter"]`. No LLM call code exists yet (rows 49, 50). |
| 4 | "nothing is held beyond that block" | DESIGN.md:L94-95 | FALSE | `sis/ingest/run.py:220` `threading.BoundedSemaphore(workers * 2)`: up to 2 blocks per worker are in flight (22 with 11 workers), each up to 60 MiB plus a 4 MiB chunk (`sis/ingest/reader.py:36-39`). The reader itself holds at most one 64 MiB buffer (`reader.py:1`). |
| 5 | "Measured on a 16-core ... laptop" | DESIGN.md:L95 | FALSE | `docs/INGEST_REPORT_8e25...md:20` "16 logical CPUs, 23.3 GB RAM" (`os.cpu_count()`, `sis/ingest/report.py:291`). The machine reports NumberOfCores 8, NumberOfLogicalProcessors 16 (Win32_Processor query, read-only). |
| 6 | "a file that is not zstd or not JSONL is rejected at the magic-byte check" | DESIGN.md:L105-106 | FALSE | Only non-zstd is `rejected` (`sis/ingest/run.py:292-293`, `test_rejects_non_zstd` `tests/test_ingest.py:203-209`). A zstd file that is not JSONL passes the magic check and is `quarantined` by the 1,000-line preflight (`run.py:312-320`; `test_quarantines_garbage` `tests/test_ingest.py:212-219`). |
| 7 | "As built: 481,186 domain entities, plus 12,643 from certificate names and 1,600 from Host headers, for 495,429 active entities and 532 blocked" | DESIGN.md:L131-134 | FALSE | These are P2 numbers (`docs/REVIEW_P2.md:37,50-51`), superseded by the P3.1 rerun. Current `docs/RESOLVE_REPORT_8e25...md:13-17`: domain 472,508, cert_cn 12,983, http_host 1,642, active 487,133, blocked 489 (`docs/P3_1_REPORT.md:57-62` before/after). README.md:6 and SCORE_REPORT already use 487,133. |
| 8 | "fallbacks attributed 38,433 more banners" | DESIGN.md:L134 | FALSE | `docs/RESOLVE_REPORT_8e25...md:26` fallback 39,993 (38,433 is the P2 "before" value, `docs/P3_1_REPORT.md:63`). |
| 9 | "92.46 percent of banners remain unattributed: 9.73 million are operator-only" | DESIGN.md:L134-136 | FALSE | `docs/RESOLVE_REPORT_8e25...md:27` none 13,576,863 = 92.94%; `:36` operator_only 9,797,742 (9.80 million). Plus 4,745 attributed only to blocked entities (`:38`). |
| 10 | `*-rat` probe modules are not detections (16 of 31,763 rows on Google IPs carry a payload) and are ignored | DESIGN.md:L143-145 | FALSE | No code filters `*-rat` modules; `config/blocked_tags.yaml:3` only keeps them out of the block lists. `C_breadth_modules` counts them (`sis/signals/catalogue.py:98`), `C_any_service` fires on them (`catalogue.py:109`), `entities.n_modules` counts them (`sis/entities/sql/07_entities.sql:15`). Payload count verified: `findings/07_ground_truth.md:23-27`. |
| 11 | Fact C signals = 7 listed (C_admin_services ... C_live_web) | DESIGN.md:L164 | FALSE | The catalogue has 8 fact-C signals. `C_any_service` (fact "C", `sis/signals/catalogue.py:109-110`) is missing from the table, yet it is in the prerequisite (`config/scoring.yaml:47`, DESIGN L216) and fires on 80.95% of entities (`docs/SCORE_REPORT_8e25...md` fire rates). `X_small_cloud` (fact "X", `catalogue.py:121`) is not in any row either. It is unscored, so leaving it out is fine. |
| 12 | 5.1 rationale: "`module x country` splits payload size, certificate age and vulnerability counts more than any other pair (findings/07_num_vs_cat.csv)" | DESIGN.md:L172-L174 | FALSE | `findings/07_num_vs_cat.csv` holds single categoricals, not pairs. Only `product` has an n_vulns row (median 0 to 61), and `product` splits cert_age_days most (39 to 20,752). `module` has no cert_age_days row. `findings/07_clusters.md:29-35`: module x country_code was chosen as "the 2 lowest-cardinality splitters that are not K6 duplicates". |
| 13 | "From Stage 1, 131,104 entities are `untouched` with a live service and no protection" | DESIGN.md:L228-L229 | FALSE | 131,104 is the Stage 1 target group: P01-P03 and none of W01-W07 (`findings/07_negative.md:19`, `sis/scoring/score.py:26`). As built, the `untouched` segment holds 300,849 (61.76%) at 1.1.0 (`docs/SCORE_REPORT_8e25...md` Segments, `docs/P3_1_REPORT.md:73`). The Stage 1 group recomputed on P3 entities is 129,495. The score report says outright that the untouched segment "differs". |
| 14 | 5.5: the model does not use `module` values as detections (they are probes) | DESIGN.md:L242 | FALSE | `D_vpn` fires on mapping W05 `module IN ('openvpn','checkpoint-hostname','ike','ike-nat-t','l2tp','pptp')` with no payload check (`config/what_we_sell_map.csv:6`, `sis/signals/catalogue.py:116`). `C_any_service` fires on `data_len > 0 OR module NOT IN ('auto')`, so any non-`auto` probe name counts with no payload (`sis/signals/catalogue.py:109`), and it gates the prerequisite (`config/scoring.yaml:47`). Only `C_admin_services` and P02 require `data_len > 0`. |
| 15 | 5.5: P3 recomputes n_vulns excluding `kev`, `verified` **and `ransomware_campaign`** | DESIGN.md:L243-L245 | FALSE | `sis/signals/sql/01_vulns_clean.sql:13` filters only `coalesce(v.kev,false)=false AND coalesce(v.verified,false)=false`. `ransomware_campaign` is never read on the scoring side. It is read only for `label_ransomware` (`sis/evaluate/sql/01_labels.sql:11-14`). DATA_MODEL.md:250 states the code's rule (kev and verified). The Known rows are probably a subset of the kev rows (a KEV field), but the code does not check that. |
| 16 | 5.5: nothing from the `*-rat` modules is used | DESIGN.md:L248 | FALSE | No code filters `*-rat` modules. `C_breadth_modules` fires on every non-edge banner (`fires "true"`, `sis/signals/catalogue.py:98`) and counts them. `C_any_service` fires on them because they are not `auto` (`catalogue.py:109`), even though 99.9% have no payload (`config/what_we_sell_map.csv:13` note), so they can make an entity `untouched`. `entities.n_modules` counts them (`sis/entities/sql/07_entities.sql:15`), which sets the peer bucket and the breadth_only baseline. Only the blocklist leaves them out (`config/blocked_tags.yaml:3`). |
| 17 | 5.5: an edge banner "feeds `D_waf`, `D_edge_substitute` and `C_live_web` only" | DESIGN.md:L252-L253 | FALSE | True for signals: only those 3 have `edge_ok=True` (`sis/signals/catalogue.py:105-113`), and `render()` guards the rest (`:140-144`). But `entities.n_modules` and `country_code` are built over every attributed banner, edge banners included (`sis/entities/sql/07_entities.sql:4-24`). Those 2 columns pick the peer group (`sis/scoring/sql/01_peer.sql:6-17`), and the peer group sets pct() for A_cpe_per_header, B_cert_age_days, C_breadth_modules and C_components_vs_peers (`sis/signals/sql/03_pct.sql`). So a tenant behind Incapsula still takes the edge's breadth for its peer bucket. |
| 18 | "The tested labels are independent but number in the low thousands" | DESIGN.md:L315-L316 | FALSE | label_any_tested = 681 entities, label_verified 669, label_heartbleed 44 (`docs/EVAL_REPORT_8e25...md:12-15`). That is hundreds, not thousands. The generated report repeats the phrase (`sis/evaluate/report.py:191-192`). |
| 19 | CI: "a scoring change that silently degrades the ranking cannot merge" because `pytest -m eval` recomputes the metrics on the fixture | DESIGN.md:L320-L323 | FALSE | The bundle holds precomputed outputs only: `tests/fixtures/eval_bundle/eval_bundle.parquet` columns are entity_id, priority, exposure, segment, fact_a..fact_d and 7 labels (no signals, no inputs). `tests/test_eval.py:67-77` re-ranks the stored `priority` column; no scoring code runs. Changing `config/scoring.yaml` or `sis/scoring/sql/02_facts.sql` cannot change the test result. The bundle and thresholds move only via `sis evaluate FILE_ID --fixture` (`sis/evaluate/fixture.py:1-2`). |
| 20 | "2 uses were designed, specified as build cards" (section 7) | DESIGN.md:L335-336 | FALSE | A 3rd LLM use is designed as a card: `cards/P9.md:44-46` drives the mid-tier model through the gateway (task `mcp_agent`), and `config/llm_tiers.yaml:35` + `sis/llm/tiers_config.py:14` + `tests/test_scaffold.py:190-192` require that task. The 2 product features claim holds only if P9's eval agent is excluded explicitly. The L561 wording "The 2 LLM features" holds: P9's agent is an eval driver, not a feature. Corrected in section 7 only. |
| 21 | Tier table: mid tier models are "Sonnet or DeepSeek class" | DESIGN.md:L353 | FALSE | `config/llm_tiers.yaml:19-20` mid = deepseek/deepseek-v4-flash, qwen/qwen3.8-flash. No Sonnet in mid; claude-sonnet-5.5 is the reasoning tier's 2nd model (`config/llm_tiers.yaml:13`). Should read "DeepSeek or Qwen flash class". |
| 22 | Faithfulness check "rejects any output naming a product, CVE, number or signal absent from the input" | DESIGN.md:L384-386 | FALSE | Designed check per `cards/P8.md:47-50`: CVE pattern, integers >= 10, capitalised 2+ word sequences, years. No signal-id check and numbers under 10 pass. (Design-vs-card mismatch; nothing is built.) |
| 23 | About 3.5 min of entity resolution | DESIGN.md:L398 | FALSE | Stale: `docs/RESOLVE_REPORT_8e25...md:7` wall seconds 173.8 (about 2.9 min) after the P3.1 rerun; 3.5 min was the P2 run (`tasks/state.md:124`). |
| 24 | "33 files a day at 12 minutes each is about 7 machine-hours" (per-file stages) | DESIGN.md:L408-409 | FALSE | 12 min is ingest only (712.6 s, `docs/INGEST_REPORT_8e25...md:14`). Per-file stages ingest + resolve + score = 712.6 + 173.8 + 249.4 = 1,135.8 s, about 19 min (`docs/RESOLVE_REPORT_8e25...md:7`, `docs/SCORE_REPORT_8e25...md:7`); 33 files = about 10.4 machine-hours. The conclusion (fits 1 machine) still holds. |
| 25 | "layers 2 and 3 (tens of MB per file)" | DESIGN.md:L418 | FALSE | Layer 3 alone was about 152 MB per file at P3: signals 18.6 MB, evidence 111.5 MB, scores 22.0 MB (`tasks/state.md:101`); evidence then grew 4,115,664 -> 4,549,051 rows at P3.1 (`tasks/state.md:59`). The serve bundle alone is 156.6 MB (`docs/DEPLOY.md:31`). |
| 26 | 50-IP cutoff, fact weights and segment multipliers: "the ablations show what each one does" | DESIGN.md:L501-504 | FALSE | `sis/evaluate/ablation.py:4-5` ablates fact weights (no_A, no_B, no_C) and segment multipliers (no_D) only. No ablation varies ROLLUP_MAX_IPS. The cutoff's effect is shown in exploration, `findings/06_relationships.md:65-77` (cutoff table at 50 and 250). |
| 27 | Section 6 metrics "designed to accept [the 2 buttons] as a 7th label without code changes" | DESIGN.md:L511-512 | FALSE | Labels are hard-coded: `sis/evaluate/metrics.py:17-18` LABELS tuple, `sis/evaluate/sql/01_labels.sql:38-44`. Nothing in `sis/evaluate` reads feedback.jsonl. `evals/README.md` "Adding the 7th label" step 2 says to edit 01_labels.sql and LABELS. The metric functions themselves are generic (`metrics.py:33` takes any label list), so only the wiring is a code change. |
| 28 | vulns key is (`banner_id`, `cve`) | DATA_MODEL.md:L69 | FALSE | `sis/ingest/flatten.py:52` column is `id`, not `banner_id` (doc's own L74 says so). Key is (`id`, `cve`). |
| 29 | `n_references INTEGER` | DATA_MODEL.md:L84 | FALSE | `sis/ingest/flatten.py:21,53` INT = `pa.int64()`, i.e. BIGINT. |
| 30 | "P3 and P4 read `ransomware_campaign` with that extraction" | DATA_MODEL.md:L91 | FALSE | Only P4 reads it: `sis/evaluate/sql/01_labels.sql:11,14`. No read in `sis/signals`, `sis/scoring` or `config/` (grep `ransomware`, `other_keys`). |
| 31 | ingest_log `status` is 'ok' \| 'failed' \| 'duplicate' \| 'quarantined' | DATA_MODEL.md:L101 | FALSE | Also `'rejected'` for a non-zstd file: `sis/ingest/log.py:15-17`, `sis/ingest/run.py:41,292-293`, `tests/test_ingest.py:203-207`. |
| 32 | `dropped_reasons` JSON keys json_parse, missing_id, oversize | DATA_MODEL.md:L103 | FALSE | Code also emits `blank` (`run.py:103`), `flatten_error` (`run.py:115`), `type_error` (`run.py:139`); oversize at `run.py:232`. Written with sorted keys (`run.py:286`). |
| 33 | `error` "null unless failed" | DATA_MODEL.md:L106 | FALSE | Also set for `rejected` (`run.py:293`) and `quarantined` (`run.py:319-320`). |
| 34 | banner_entity `attribution`: "(domain = primary; others = fallback)" | DATA_MODEL.md:L124 | FALSE | A fallback cert/Host name that is also a primary domain entity is re-keyed to `key_kind='domain'` and keeps `attribution='fallback'`: `sis/entities/sql/06_banner_entity.sql:14-17`; `tests/test_resolve.py:200-205` (one domain entity, attributions fallback, fallback, primary). |
| 35 | entities `blocked_reason` values include `'operator_domain'` | DATA_MODEL.md:L175 | FALSE | `sis/entities/sql/07_entities.sql:37` produces only null, 'c2_or_malware', 'honeypot_or_scanner'. The doc's own rule 6 (L150) says operator_domain is never produced. |
| 36 | `peer_group = country_code \|\| '\|' \|\| breadth_bucket` | DATA_MODEL.md:L176 | FALSE | P2 writes NULL (`07_entities.sql:39`, `tests/test_resolve.py:275`). P3 fills it in place (`sis/scoring/peer.py:62-75`): `country\|bucket`, else `'*\|' \|\| bucket`, else `'*\|*'` when the group has fewer than PEER_MIN_SIZE active entities or country is null (`sis/scoring/sql/01_peer.sql:14-17`); blocked entities stay null. |
| 37 | `status='blocked'` "or the key is an operator domain" | DATA_MODEL.md:L181 | FALSE | Operators never become entities (`04_primary.sql:5`, `05_fallback.sql:11`); status is blocked only from B01/B02 tags (`07_entities.sql:8-9,36`). |
| 38 | A_cpe_per_header predicate: "http banners only" | DATA_MODEL.md:L227 | FALSE | `catalogue.py:67` fires on `http_status IS NOT NULL AND len(cpe23) > 0`. An http banner with no cpe never fires, which changes n_banners, evidence and whether the row exists. The value formula matches (`catalogue.py:68`) |
| 39 | C_breadth_modules value = `n_modules` | DATA_MODEL.md:L235 | FALSE | `sis/signals/catalogue.py:98` value is `count(DISTINCT module)` over the entity's firing banners, and `render()` (`catalogue.py:144`) adds `AND NOT is_edge` since `edge_ok` is False. So it counts modules on non-edge banners only. `entities.n_modules` counts every attributed banner (`sis/entities/sql/07_entities.sql:15`). The two differ for any entity with edge banners. This is intended (`cards/P3.md:40`), but the doc says `n_modules` |
| 40 | C_breadth_ports value = `n_ports` | DATA_MODEL.md:L236 | FALSE | `catalogue.py:100` `count(DISTINCT port)` over non-edge banners only (edge guard, `catalogue.py:144`). `entities.n_ports` counts every banner (`07_entities.sql:14`) |
| 41 | C_components_vs_peers predicate: "http banners" | DATA_MODEL.md:L237 | FALSE | `catalogue.py:103` fires on `http_status IS NOT NULL AND len(http_components) > 0` |
| 42 | events.subject is "a signal_id, 'ip:port', a cve, a waf name" | DATA_MODEL.md:L316 | FALSE | `sis/delta/sql/01_events.sql:230-281`. The subject is the entity `key_value` (entity_new/gone), `ip:port` (service_*), a signal_id (signal_*, cert_expired_since=`B_expired`, protection_*=`D_*`), the literal `'exposure'` (exposure_up/down) or `'segment'` (segment_changed). It is never a CVE: an added CVE is `signal_appeared` with subject `A_inferred_cves` (`docs/DELTA_REPORT_...md:53`). It is never a WAF name: the name goes in from_value/to_value from evidence (`01_events.sql:261-271`) |
| 43 | accounts.parquet = entities + scores + entity_profile (left join) | DATA_MODEL.md:L387 | FALSE | `sis/export/bundle.py:86-100` left-joins only 4 profile columns, and renames `confidence` to `industry_confidence`. It also drops entities `status`, `blocked_reason` and entities `file_id` (it keeps scores `file_id`), and adds `max_event_severity` |
| 44 | API serves "from a local copy of the bundle pulled at boot" | DATA_MODEL.md:L395-396 | FALSE | The bundle is baked into the image at build time: `Dockerfile:17` `COPY --from=bundle . /app/bundle`, `docs/DEPLOY.md:15-16`. At boot the app opens `/app/bundle` (`sis/api/app.py:23,63-64,72`). Nothing is pulled |
| 45 | CI `pytest -m eval` produces "the same metrics" on the fixture | DATA_MODEL.md:L418-419 | FALSE | `tests/test_eval.py:67-77` recomputes only `precision_at_1000` for `label_any_tested` and `label_kev` (`config/eval.yaml` fixture.labels, k 1000) on `tests/fixtures/eval_bundle/eval_bundle.parquet`. metrics.json, ablations and baselines are not recomputed in CI |
| 46 | Serve is "FastAPI + DuckDB over a 157 MB bundle" | README.md:L46 | FALSE | 156.6 MB was the P5 bundle 20261102-1135-1.1.0 with 0 events (docs/DEPLOY.md:30-32, tasks/state.md:44). The live bundle is 20261102-0000-p6-1.1.0, 160.1 MB with 84,313 events (tasks/state.md:28, docs/DEPLOY.md:3-5); the refreshed local re-export with 148,368 events is 162.5 MB (tasks/state.md:8). No bundle in the current chain is 157 MB. |
| 47 | Requires "`zstd` on PATH" | README.md:L53 | FALSE | No code shells out to a zstd binary. Decompression and synth use the `zstandard` Python package (pyproject.toml:22, sis/ingest/reader.py:7, sis/delta/synth.py); the only subprocess is `git rev-parse` (sis/__init__.py:12). The zstd CLI appears only in cards/P0.md:114 (one-off fixture build, fixture already committed). |
| 48 | `uv run pytest -q -m "not llm"` runs "168 tests" | README.md:L70 | FALSE | `uv run pytest --collect-only -q -m "not llm"` collects 169 (165 non-eval + 4 eval). Test files unchanged since 9ea7982 (`git log -- tests`), which added `test_recall_counts_chosen_entities_and_reports_touched_apart`; tasks/state.md:9 "168 passed" predates or undercounts it. Confirmed by `tasks/state.md:3` (P5.3 gate: "Audit 169 passed"). |
| 49 | Diagram: `[P7 classify] LLM industry/description for top-N, cached, costed` shown as a live pipeline stage, no "not built" label | DESIGN.md:L60 | NOT BUILT | `sis/cli.py:157-160` `classify` calls `_stub("classify")` (exits 2, "not implemented"); `sis/llm/` holds only `tiers_config.py` (config loader). DESIGN.md:L561 itself says the LLM features are "designed and configured, not built". |
| 50 | Diagram: `[P8 report card] on-demand LLM explanations ... faithfulness-checked, costed` | DESIGN.md:L68 | NOT BUILT | `sis/cli.py:207-210` `reportcard` is `_stub("reportcard")`; no report-card code under `sis/`. |
| 51 | Diagram: `[P9 MCP server] same read API as tools for an agent, trajectory evals` | DESIGN.md:L70 | NOT BUILT | `sis/cli.py:213-216` `mcp` is `_stub("mcp")`; no MCP module under `sis/`, no `mcp` dependency in `pyproject.toml:5-23`. |
| 52 | "A file with a new file_id but identical banner ids (a renamed re-delivery) is detected at P2 merge time: banner ids are globally unique, so the merge upserts and the ingest report says '0 new banners'" | DESIGN.md:L89-92 | NOT BUILT | No banner-level merge or upsert exists. `sis/entities/resolve.py:313-350` `merge_current` merges per-file `entities.parquet` by `entity_id` (latest file wins), never looks at banner ids. `sis/ingest/report.py:270-305` has no "new banners" line; grep for "new banners" / "0 new" finds only DESIGN.md and cards/P1.md:77. Also: a renamed file with the same bytes gets the same `file_id` (`sis/ingest/file_id.py:10-26`, content only) and is caught as `duplicate`, so "renamed" is the wrong word for the different-bytes case. |
| 53 | "What was automated": "LLM validation (labelled sets, judge calibration), model routing and cost control (the tiered gateway: rate limits, budgets, fallback, escalation, every call logged with tier, model, prompt version, tokens, USD)" | DESIGN.md:L494-499 | NOT BUILT | `sis/llm/` holds only `tiers_config.py` (loader, budget-sum check). No gateway, no client calls, no rate limiter, no fallback/escalation code; `paths.llm_calls_path()` (`sis/paths.py:92`) is defined and never written. No `evals/industry` or `evals/reportcard` (only `evals/README.md`, about P4). Contradicts L335 and L561 in the same doc. |
| 54 | Every table has `built_at` + `pipeline_version` columns or a sidecar `_meta.json`: banners and vulns | DATA_MODEL.md:L15-17 | NOT BUILT | `sis/ingest/flatten.py:23-55` SCHEMA/VSCHEMA have neither column; `sis/ingest/run.py:350-353` writes only `key_inventory.json` (top_keys, vuln_keys, new_keys), no built_at/pipeline_version. Trace exists only indirectly via ingest_log row (`run.py:287`). |
| 55 | Same convention: `ingest_log` | DATA_MODEL.md:L15-17 | NOT BUILT | `sis/ingest/log.py:12-21` has `pipeline_version` but no `built_at` (closest is `finished_at`). |
| 56 | Same convention: `current/entities.parquet` | DATA_MODEL.md:L15-17, L157 | NOT BUILT | `sis/entities/resolve.py:313-350` merge_current writes only entities.parquet; no sidecar, no built_at/pipeline_version column. |
| 57 | Convention: every table has built_at + pipeline_version, or a sidecar meta (applies to current/scores.parquet) | DATA_MODEL.md:L15-17, L274-275 | NOT BUILT | `sis/scoring/score.py:160-193` `merge_current()` writes `current/scores.parquet` with no such columns and no sidecar |
| 58 | Convention: built_at + pipeline_version (applies to history/events.parquet) | DATA_MODEL.md:L15-17, L308 | NOT BUILT | `sis/delta/diff.py:135-144` writes events with no built_at or pipeline_version column and no sidecar. `detected_at` is the delivery's arrival time, not the build time |
| 59 | Convention: built_at + pipeline_version (applies to history/entity_history.parquet) | DATA_MODEL.md:L15-17, L303 | NOT BUILT | `diff.py:154-174` writes entities + scores columns only. Neither table has those columns, and there is no sidecar |
| 60 | Convention: built_at + pipeline_version (applies to eval/labels.parquet, metrics/ablations/baselines.json) | DATA_MODEL.md:L15-17, L408-415 | NOT BUILT | `sis/evaluate/labels.py:85` writes labels with no meta. `sis/evaluate/metrics.py:139-152` metrics.json carries `scoring_version` but no built_at or pipeline_version. Same for ablation.py:75 and baselines.py:72 |
| 61 | `entity_profile` table, all 12 columns (entity_id ... classified_at) | DATA_MODEL.md:L332-349 | NOT BUILT | No code writes `current/entity_profile.parquet`. `sis/cli.py:157-160` `classify` is `_stub`. `sis/export/bundle.py:19-21,72` reads it only if it exists, and otherwise uses an empty stand-in with 5 columns. `sis/llm/` holds only `tiers_config.py` |
| 62 | `report_cards/<entity_id>.json`, "also served by the API", all fields | DATA_MODEL.md:L351-363 | NOT BUILT | No writer. `sis/cli.py:207-210` `reportcard` is `_stub`. There is no report-card route in `sis/api/routes.py` (routes: /accounts, /accounts/{id}, /stats, /health, /feedback, pages /, /accounts, /accounts/{id}, /ui/feedback, /about) |
| 63 | `llm_calls.parquet` append-only log, all 18 columns | DATA_MODEL.md:L365-376 | NOT BUILT | Only the path helper exists, `sis/paths.py:92-93` (tested `tests/test_scaffold.py:64`). Nothing writes the file |
| 64 | "Computed offline: everything in layers 1 to 5" (layer 5 part) | DATA_MODEL.md:L399 | NOT BUILT | Layer 5 does not exist (rows 61, 62, 63). Layers 1-4 are verified elsewhere in this table |
| 65 | "Generated on demand but persisted: report cards (P8), triggered from the UI, written back to the bundle directory and to layer 5.3" | DATA_MODEL.md:L401-402 | NOT BUILT | See rows 62, 63. The UI writes back only `feedback.jsonl` (`routes.py:169-180`) |
| 66 | Correlation clusters (findings/07_clusters.md) show the 17+3 candidates encode 4 underlying things | DESIGN.md:L156-L157 | UNVERIFIED | `findings/07_clusters.md` lists 11 clusters K1-K11. The grouping into 4 facts is the design's own and is not stated in findings. |
| 67 | Scoring 17 columns would count the same fact up to 6 times | DESIGN.md:L157-L158 | UNVERIFIED | No source states "6". The nearest support is K1 (6 columns) and K2 (6 columns) in `findings/07_clusters.md`. |
| 68 | Synth of second delivery took 762 s (1,782 s on a rerun under load) | DESIGN.md:L436-437 | UNVERIFIED | No report, state entry or commit message carries 762 or 1,782. `tasks/state.md:13` gives only "13 to 30 min" (780-1,800 s), which 762 s falls just outside. Likely in the synth truth file under $SIS_DATA (not read). |
| 69 | Evidence table "approaches the 0.5 GB ceiling" of Postgres free tiers | DESIGN.md:L459-460 | UNVERIFIED | Only row count (4,549,051, `docs/DEPLOY.md:30`) and Parquet sizes exist; no Postgres-size measurement anywhere. |
| 70 | Architect "Wrote 0 lines of application code" | DESIGN.md:L472 | UNVERIFIED | git author is the same user for all commits; no attribution per role. |
| 71 | "Every number in findings/ traces to a script in findings/queries/" | DESIGN.md:L474-475 | UNVERIFIED | 14 scripts exist in `findings/queries/`; not traced number by number. |
| 72 | "The human runs the acceptance tests before the next card starts" | DESIGN.md:L492 | UNVERIFIED | `tasks/state.md` records gates run by builder sessions; no record of a human rerun. |
| 73 | lessons.md records "every correction ... by whom" | DESIGN.md:L506-507 | UNVERIFIED | `tasks/lessons.md` exists with dated, role-tagged entries and a rule each (VERIFIED for format), but entry 1 (line 3) has no date or author, and "every" cannot be checked. |
| 74 | "People data: none in the file" | DESIGN.md:L526 | UNVERIFIED | No explicit statement in `findings/REPORT.md`; `evals/README.md` says no purchase, contact or churn field. |
| 75 | Size dominated by evidence | DATA_MODEL.md:L397 | UNVERIFIED | No per-file size is recorded. Row counts only: evidence 4,549,051, signals 3,189,714, accounts 487,133 (`docs/DEPLOY.md:30`) |
| 76 | Live app at https://sis-niranjan.fly.dev/ | README.md:L3 | UNVERIFIED | Not fetched during the audit. fly.toml:3 `app = "sis-niranjan"`; docs/DEPLOY.md:3 states it live, redeployed 2026-11-04. |
| 77 | Each of the 487,133 businesses has "the verbatim evidence behind the score" | README.md:L6-8 | UNVERIFIED | Evidence rows exist (4,549,051, docs/SCORE_REPORT_8e25...:7) and the account page renders raw snippet/value (sis/api/templates/account.html:4-17), but the page has an empty state "Nothing visible adds to exposure for this account." (account.html:84) and low_surface accounts (5,613) may have no evidence rows. Not checkable without reading the bundle. |
| 78 | Architect wrote the exploration plan "before seeing the data" | README.md:L88 | UNVERIFIED | EXPLORATION.md was first committed in 8203a74 (2026-11-02), after the findings commit b8e35d0 (2026-11-01); b8e35d0's message cites "sections 0a-7 of EXPLORATION.md", so the plan existed first, but git does not show it was written before the data was seen. |
| 79 | "The human ran the acceptance tests between cards" | README.md:L92 | UNVERIFIED | Stated in DESIGN.md:492 and cards/README.md:54; no log of human runs beyond the builders' own gate lines in tasks/state.md. |
| 80 | Companion docs: DATA_MODEL.md, cards/P0..P9, EXPLORATION.md, findings/ | DESIGN.md:L9-10 | VERIFIED | All present (cards/P0.md..P9.md plus P3_1, P5_1). |
| 81 | Assignment: rank businesses most likely to buy, 1 file, hundreds to thousands of files a month | DESIGN.md:L16-18 | VERIFIED | `ASSIGNMENT.md:9,17`. |
| 82 | 14,608,406 service banners | DESIGN.md:L20 | VERIFIED | `docs/INGEST_REPORT_8e25...md:10` rows written 14,608,406; `findings/06_relationships.md:14`. |
| 83 | 122.8 GB decompressed | DESIGN.md:L21 | VERIFIED | `findings/00_format.md:8` 122,782,583,953 bytes. |
| 84 | 1 scan window of 18.9 hours, 95.7 percent of rows in 1 hour | DESIGN.md:L21-22 | VERIFIED | `findings/06_relationships.md:140-143`. |
| 85 | 62.4 percent of rows belong to 5 network operators; Incapsula 31.9 percent | DESIGN.md:L22-23 | VERIFIED | `findings/06_relationships.md:54-56` (top 5 orgs 62.4 %), `:75` (Incapsula 31.9 %). |
| 86 | 7.36 percent of rows (1,074,635) resolve to a customer domain, 485,089 entities | DESIGN.md:L23-25 | VERIFIED | `findings/06_relationships.md:68,72-74` (explorer numbers; as-built differs, see rows 7, 8, 9). |
| 87 | P1: stream -> flatten -> Parquet (banners, vulns) + ingest_log; idempotent on file_id; quarantine on malformed | DESIGN.md:L48-49 | VERIFIED | `sis/ingest/run.py:146-150` (banners/vulns parts), `:280` / `sis/ingest/log.py:133-144` (ingest_log), `:296-310` (duplicate), `:312-320` (quarantine). |
| 88 | P2: banners -> banner_entity -> entities (+blocked, +unattributed_summary) | DESIGN.md:L51 | VERIFIED | `sis/entities/resolve.py:264-275` writes banner_entity, entities, unattributed_summary; `sql/07_entities.sql:36-38` status/blocked_reason. |
| 89 | P3: signals -> evidence -> scores | DESIGN.md:L54 | VERIFIED | `sis/scoring/score.py:121`, `sis/scoring/report.py:30`, `sis/scoring/explain.py:24` (scores/evidence/signals.parquet). Determinism and peer-relative claims are checked under section 5. |
| 90 | P4: metrics.json, ablations, baselines; `pytest -m eval` in CI | DESIGN.md:L56 | VERIFIED | `sis/evaluate/metrics.py:137`, `ablation.py:75`, `baselines.py:72`; `.github/workflows/ci.yml:18-25`. |
| 91 | P6: entity_history + events across consecutive files | DESIGN.md:L58 | VERIFIED | `sis/paths.py:372-377`; `sis/cli.py:136-154` `sis delta FROM TO`. |
| 92 | Export: serve bundle (accounts, evidence, events, signals, bundle.json) | DESIGN.md:L63 | VERIFIED | `sis/export/bundle.py:53`. |
| 93 | P5 app: FastAPI + DuckDB over the bundle, Jinja2/htmx UI, Logfire traces | DESIGN.md:L66 | VERIFIED | `sis/api/app.py:31-39,67-79` (DuckDB over bundle, `logfire.instrument_fastapi`); `sis/api/templates/base.html:14` htmx 1.9.12. |
| 94 | Layers 1 to 5 of DATA_MODEL.md are batch | DESIGN.md:L73 | VERIFIED | `DATA_MODEL.md:39,111,198,299,330,399` label layers 1-5 offline. Layer 5 itself is not built (rows 49, 50). |
| 95 | Stack: Python 3.12, DuckDB, pyarrow, pydantic v2, pydantic-settings, typer, FastAPI, Jinja2 + htmx, pytest, ruff, uv | DESIGN.md:L77-79 | VERIFIED | `pyproject.toml:4-33`; `Dockerfile:4` `python:3.12-slim`; `Dockerfile:6` uv. |
| 96 | logfire, falls back to console if no token | DESIGN.md:L78-79 | VERIFIED | `sis/log.py:16-19` (`send_to_logfire=False, console=...`); `sis/api/app.py:76` `send_to_logfire="if-token-present"`. |
| 97 | file_id = sha256 of the first 64 MiB, then the byte length; computed before decompression | DESIGN.md:L87-88 | VERIFIED | `sis/ingest/file_id.py:6,10-26` (separator is `-`, not `:`, documented in the docstring). |
| 98 | Re-delivered file with same file_id is logged `duplicate` and skipped | DESIGN.md:L88-89 | VERIFIED | `sis/ingest/run.py:296-310` (needs an earlier `ok` log row and the final dir); `tests/test_ingest.py:232-240`. |
| 99 | Workers each own a 60 MiB block of lines; zstd decompressed as a stream | DESIGN.md:L93-94 | VERIFIED | `sis/ingest/reader.py:36-39` `BLOCK_BYTES = 64 MiB - 4 MiB`; `:55-96` streaming reader; `run.py:222-228` spawn pool. |
| 100 | 11 workers, 14,608,407 lines in 712.6 s, 20,501 lines/s, 24.7 MB/s compressed, 2.27 GB banner Parquet, 0.42 GB vulns Parquet; 23 GB RAM | DESIGN.md:L95-98 | VERIFIED | `docs/INGEST_REPORT_8e25...md:9,14-20` (2,269,098,353 and 424,266,236 bytes; 23.3 GB RAM; workers 11; default `sis/config.py:430`). |
| 101 | A second run of the same file prints `duplicate` and writes nothing | DESIGN.md:L98-99 | VERIFIED | `sis/cli.py:27`; `run.py:296-310` writes no Parquet (it does append one ingest_log row, `run.py:304-309`); `tests/test_ingest.py:232-240`. |
| 102 | Output verified equivalent in row count and id hash to the exploration run | DESIGN.md:L99-100 | VERIFIED | `sis/ingest/equivalence.py:158-187` (count + md5 over ids); `tasks/board.md:6` "md5 equivalence ok". "Byte-equivalent" overstates it: rows and ids are compared, not bytes. |
| 103 | Malformed outcomes all logged per file in ingest_log | DESIGN.md:L101 | VERIFIED | `sis/ingest/log.py:114-123` (status, rows_dropped, dropped_reasons); `run.py:275-290`. |
| 104 | Line failing JSON parse or lacking `_shodan.id` is dropped and counted; real file has exactly 1 | DESIGN.md:L102-104 | VERIFIED | `sis/ingest/run.py:105-116`; `docs/INGEST_REPORT_8e25...md:11-12` `{"json_parse": 1}`. Other counted reasons also exist: blank, flatten_error, type_error, oversize (`run.py:103,115,139,232`). |
| 105 | First 1,000 lines with more than 1 percent failures -> quarantined before any output | DESIGN.md:L104-105 | VERIFIED | `sis/ingest/run.py:36,312-320` (`len(bad) * 100 > checked`), before `tmp` is created at `:322-325`; `tests/test_ingest.py:212-229`. |
| 106 | Non-zstd file rejected at the magic-byte check | DESIGN.md:L105-106 | VERIFIED | `sis/ingest/reader.py:35,50-52`; `run.py:292-293`. (The "not JSONL" half is row 6.) |
| 107 | Output to `$SIS_DATA/<file_id>.tmp/`, renamed to `$SIS_DATA/<file_id>/` only after row counts reconcile with lines read minus dropped; crash leaves nothing visible | DESIGN.md:L107-109 | VERIFIED | `sis/paths.py:326-332`; `sis/ingest/run.py:333-345` (two reconciliation checks), `:360` `os.replace`, `:362-367` rmtree on failure; `tests/test_ingest.py:250-280`. |
| 108 | Flattener extracts a fixed set of paths and stashes every unknown top-level block in `extra_json`; new fields show in a per-file key inventory the ingest report prints | DESIGN.md:L110-113 | VERIFIED | `sis/ingest/flatten.py:11-16,158-159,225`; `run.py:347-353` (`key_inventory.json`, `new_keys` vs `config/known_top_keys.txt`); `report.py:296-304`; `tests/test_ingest.py:154-157,282`. Note: known keys `html` and `screenshot` are deliberately dropped from extra_json (`flatten.py:17`). |
| 109 | org and asn are determined by the IP (FD 100 percent) | DESIGN.md:L119-120 | VERIFIED | `findings/06_relationships.md:47-48`. |
| 110 | `domains` populated on 74.1 percent of rows | DESIGN.md:L122-123 | VERIFIED | `findings/06_relationships.md:40`; `findings/02_columns.csv:26`. |
| 111 | A domain covering more than 50 IPs is an operator zone; incapdns.net covers 54,411 | DESIGN.md:L123-125 | VERIFIED | `sis/entities/sql/03_operators.sql:33` (`n_ips > $cutoff`), `04_primary.sql:5`; `findings/06_relationships.md:59`. Incomplete: since P3.1, 2 hosting-zone rules in `config/resolve.yaml` and a hand seed list also make some domains under 50 IPs operators (`sis/entities/sql/03_operators.sql`). |
| 112 | Cutoff is `ROLLUP_MAX_IPS`, a setting, default 50 | DESIGN.md:L125 | VERIFIED | `sis/config.py:419`; `sis/entities/resolve.py:185`. |
| 113 | Explorer's table at 10, 50, 250: entities 476,598 to 487,512 while attributed rows grow | DESIGN.md:L126-128 | VERIFIED | `findings/06_relationships.md:67-69` (rows with any small domain 842,467 -> 1,365,942). |
| 114 | Fallback: certificate subject names (6.7 percent of rows, 91 percent consistent with domains), http_host (29.5 percent) when it is a name | DESIGN.md:L129-131 | VERIFIED | `findings/06_relationships.md:42-43,52` (cn -> domain 91 %); code `sis/entities/resolve.py:201-206`, `sql/01_names.sql:9-21`, `sql/05_fallback.sql` (cert first, then Host); `normalise.py:53-62` (IP literal -> None). Code also uses cert SANs, not only subject CN. |
| 115 | 92.6 percent unattributable (explorer) | DESIGN.md:L129 | VERIFIED | `findings/06_relationships.md:74`. |
| 116 | "3.78 million have no name at all" | DESIGN.md:L135-136 | VERIFIED | `docs/RESOLVE_REPORT_8e25...md:35` no_name 3,779,121. |
| 117 | Edge banners (CDN tag or a W01 WAF name) count as protection only, never exposure | DESIGN.md:L137-141 | VERIFIED | `sis/signals/catalogue.py:135-144` (`list_contains(tags,'cdn') OR W01`, non-`edge_ok` signals get `AND NOT is_edge`); `:111-113` D signals `edge_ok=True`. |
| 118 | Blocked, never scored: honeypot or scanner tags (250,530 rows), C2 or malware tags | DESIGN.md:L142-143 | VERIFIED | `config/blocked_tags.yaml:4-5`; `sql/07_entities.sql:8-9,36-38`; `findings/07_negative.md:73-74` 250,530. |
| 119 | Operator domains never scored | DESIGN.md:L143 | VERIFIED | `sql/04_primary.sql:5`, `05_fallback.sql:11` exclude operators, so they never become entities. They are not `status='blocked'` rows (blocked_reason has only 2 values, `07_entities.sql:37`), so the 489 blocked count excludes them. |
| 120 | CDN-only entity: "behind Incapsula or Cloudflare" is the fact D negative signal, attributed to the customer domain when rDNS or the cert names it | DESIGN.md:L147-151 | VERIFIED | `sis/signals/catalogue.py:111-113` (`D_waf`, `D_edge_substitute`, `edge_ok=True`); attribution via `sql/01_names.sql`. |
| 121 | 17 candidates and 3 disqualifiers from Stage 1 | DESIGN.md:L155 | VERIFIED | `findings/08_candidates.md`: C-01..C-17, D-18..D-20 (disqualifiers at :277, :291, :305) |
| 122 | Fact A signals: A_fingerprinted, A_inferred_cves, A_max_cvss, A_eol, A_os_leak, A_cpe_per_header | DESIGN.md:L162 | VERIFIED | `sis/signals/catalogue.py:52-70`, all fact "A" |
| 123 | A evidence: eol tag lifts r_vuln 25.8; cpe present 4.8; n_cpe/n_headers top decile 13.0 | DESIGN.md:L162 | VERIFIED | `findings/08_candidates.md:74` (25.8); `findings/07_clusters.md` K2 (cpe 4.8); `08_candidates.md` C-15 (12.97) |
| 124 | Fact B signals: B_self_signed, B_expired, B_legacy_tls, B_cert_age_days | DESIGN.md:L163 | VERIFIED | `sis/signals/catalogue.py:71-86` |
| 125 | B evidence: self-signed tag r_certexpired 36.4; old-for-peers cert 88.4 | DESIGN.md:L163 | VERIFIED | `findings/08_candidates.md:88`, `:256` |
| 126 | C evidence: smb 3.65, ssh 2.37; ntlm r_selfsigned 19.6; breadth top decile r_selfsigned 3.25 | DESIGN.md:L164 | VERIFIED | `findings/08_candidates.md:116`, `:130`, `:214` |
| 127 | Fact D signals: D_waf, D_security_appliance, D_edge_substitute, D_vpn, D_hardening_headers | DESIGN.md:L165 | VERIFIED | `sis/signals/catalogue.py:111-120` |
| 128 | D evidence: waf lifts r_vuln 0.18, r_eol 0.09 | DESIGN.md:L165 | VERIFIED | `findings/08_candidates.md:172` (0.18, 0.092); `07_clusters.md` K9 |
| 129 | Peer group = country_code x breadth bucket of n_modules (1, 2-3, 4-9, 10+) | DESIGN.md:L169-L170 | VERIFIED | `config/scoring.yaml:58` `[[1,1],[2,3],[4,9],[10,null]]`; `sis/scoring/sql/01_peer.sql:6-7,15` |
| 130 | A group under 30 falls back to bucket alone, then whole population | DESIGN.md:L170-L171 | VERIFIED | `sis/config.py:18` PEER_MIN_SIZE 30; `01_peer.sql:15-17` (`n_cb >= $min_size` then `n_b >= $min_size` then `* |
| 131 | Percent ranks of continuous signals computed inside the peer group | DESIGN.md:L171-L172 | VERIFIED | `sis/signals/sql/03_pct.sql:6-12`: country |
| 132 | Constants live in config/scoring.yaml with scoring_version; hand-set, not fitted | DESIGN.md:L179-L181 | VERIFIED | `config/scoring.yaml:1-3` (version "1.1.0"); `sis/scoring/score.py:47-58` binds every constant from config |
| 133 | fact_a = clip(max(A_eol*1.0, cves>0 ? 0.4+0.6*max_cvss/10 : 0, A_fingerprinted*0.25) + 0.15*A_os_leak + 0.20*pct(A_cpe_per_header), 0, 1) | DESIGN.md:L185-L189 | VERIFIED | `sis/scoring/sql/02_facts.sql:8-13,40-41`; weights `config/scoring.yaml:8-13` (1.0, 0.4, 0.6, 0.25, 0.15, 0.20) |
| 134 | fact_b = clip(0.6 self_signed + 0.6 expired + 0.4 legacy_tls + 0.3 pct(cert_age_days), 0, 1) | DESIGN.md:L191-L192 | VERIFIED | `02_facts.sql:15-18,42-43`; `scoring.yaml:16-19` |
| 135 | fact_c = clip(0.40 min(admin,3)/3 + 0.25 windows + 0.20 min(asset_tags,2)/2 + 0.25 pct(breadth_modules) + 0.15 pct(components_vs_peers), 0, 1) | DESIGN.md:L194-L198 | VERIFIED | `02_facts.sql:20-25,44-45`; `scoring.yaml:22-29` (caps 3 and 2) |
| 136 | fact_d = max(1.0 waf, 0.8 sec_appliance, 0.5 edge_substitute, 0.4 vpn, 0.3 hardening_headers) | DESIGN.md:L200-L201 | VERIFIED | `02_facts.sql:27-29` greatest(...); `scoring.yaml:32-36` |
| 137 | exposure = 100 * (0.45 a + 0.20 b + 0.35 c) | DESIGN.md:L203 | VERIFIED | `02_facts.sql:48`; `scoring.yaml:40-42`; sum-to-1 enforced `sis/scoring_config.py:86-92` |
| 138 | pct(x) is 0 when the signal is absent | DESIGN.md:L206-L207 | VERIFIED | `sis/scoring/score.py:61-71` coalesce(p_..., 0) |
| 139 | B observable only on 6.8% of banners with TLS | DESIGN.md:L209-L210 | VERIFIED | `findings/05_semistructured.md:45` ssl 6.8% |
| 140 | C is the only family with 100% coverage | DESIGN.md:L209 | VERIFIED | Stage 1: `findings/08_candidates.md:24-25` (C-13, 100% of entities). As built, with the edge rule, fact_c > 0 on 80.88% (`docs/SCORE_REPORT_8e25...md` Facts). |
| 141 | prerequisite = C_live_web or C_admin_services>0 or C_asset_tags>0 or C_any_service | DESIGN.md:L216 | VERIFIED | `config/scoring.yaml:47`; `sis/scoring_config.py:142-145` (`v_X > 0` ORed) |
| 142 | segment rule: displace if D_waf or D_security_appliance; partially_covered elif edge_substitute/hardening_headers/vpn; untouched elif prerequisite; else low_surface | DESIGN.md:L218-L221 | VERIFIED | `02_facts.sql:31-35` |
| 143 | priority multipliers untouched 1.0, partially_covered 0.85, displace 0.6, low_surface 0.5 | DESIGN.md:L223-L224 | VERIFIED | `config/scoring.yaml:50-54`; `02_facts.sql:51-54` |
| 144 | Stage 1: 83,779 have a security vendor already | DESIGN.md:L229-L230 | VERIFIED | `findings/07_negative.md:11`. As built, displace = 77,530 (`docs/SCORE_REPORT_8e25...md`). |
| 145 | For displace, the incumbent is named in the evidence | DESIGN.md:L230 | VERIFIED | Evidence value for D_waf = `http_waf`, for D_security_appliance = `product`/cpe23 (`sis/signals/catalogue.py:111-115`) |
| 146 | Both lists (untouched, displace) are first-class outputs | DESIGN.md:L230-L231 | VERIFIED | `rank_in_segment` (`sis/scoring/sql/03_rank.sql:6-7`); API segment filter (`sis/api/routes.py:79-81,191`) |
| 147 | Every firing signal stores up to 5 banners with ip, port, field, value and a 300-char snippet | DESIGN.md:L235-L236 | VERIFIED | `sis/signals/evidence.py:11-30` (5 per entity per signal, value cut to 300); snippet `sis/signals/sql/02_eb.sql:11` = `left(regexp_replace(data, '[\r\n]+', ' |
| 148 | The UI shows evidence verbatim | DESIGN.md:L236 | VERIFIED | `sis/api/templates/account.html:9-14` prints ip:port, field: value, `<pre>` snippet |
| 149 | org, asn, isp, geolocation beyond country are not used | DESIGN.md:L246-L247 | VERIFIED | `sis/signals/sql/02_eb.sql:1-16` does not carry org/asn/isp/city/lat/long. cloud_provider is carried only for unscored X_small_cloud. |
| 150 | 28.6% of rows geolocate to 1 point | DESIGN.md:L247 | VERIFIED | `findings/04_distributions.md:37`, `findings/REPORT.md:83` |
| 151 | `data` free text not used beyond the stored snippet | DESIGN.md:L248-L249 | VERIFIED | `data` is read only in `02_eb.sql:11` (snippet). Its length `data_len` (an ingest column) gates C_admin_services and C_any_service and orders evidence. No predicate in `config/what_we_sell_map.csv` reads `data`. |
| 152 | Edge banner = `list_contains(tags,'cdn')` or http_waf matches W01 | DESIGN.md:L250-L251 | VERIFIED | `sis/signals/catalogue.py:135-137`; `02_eb.sql:17-18` |
| 153 | No purchase/contact/churn field; provider labels held out | DESIGN.md:L259-L261 | VERIFIED | kev/verified excluded `01_vulns_clean.sql:13`; opts_* not carried in `02_eb.sql` |
| 154 | Vulnerability labels skip CDN and WAF edge banners | DESIGN.md:L263-L264 | VERIFIED | `sis/evaluate/sql/01_labels.sql:4-6,28` `WHERE NOT ({edge})`, same predicate (`sis/evaluate/labels.py:34`) |
| 155 | label_kev 49,844 (10.23%) of 487,133 active | DESIGN.md:L266-L268 | VERIFIED | `docs/EVAL_REPORT_8e25...md:3,11`; definition `01_labels.sql:9,38` |
| 156 | label_verified 669 (0.14%) | DESIGN.md:L269 | VERIFIED | `EVAL_REPORT:12` |
| 157 | label_heartbleed 44 (0.01%), an active test | DESIGN.md:L270 | VERIFIED | `EVAL_REPORT:13`; `opts_heartbleed LIKE '%VULNERABLE%'` `01_labels.sql:22` |
| 158 | label_opts_vulns 669 (0.14%); 657 also verified | DESIGN.md:L271 | VERIFIED | `EVAL_REPORT:14,19` |
| 159 | label_any_tested 681 (0.14%), union of the 3 | DESIGN.md:L272 | VERIFIED | `EVAL_REPORT:15`; `01_labels.sql:42` |
| 160 | label_has_vendor 77,530 (15.92%) | DESIGN.md:L273 | VERIFIED | `EVAL_REPORT:16`; = D_waf or D_security_appliance `01_labels.sql:34-35,43` |
| 161 | "Stage 1 counted 83,779 before the edge rule" | DESIGN.md:L273 | VERIFIED | Number from `findings/07_negative.md:11` (485,089 Stage 1 entities). The drop is not shown to come from the edge rule: label_has_vendor keeps edge banners (`docs/P3_1_REPORT.md:98-100`), and the entity sets differ. |
| 162 | Metrics vs random, breadth-only and CVE-count-only baselines | DESIGN.md:L275-L276 | VERIFIED | `sis/evaluate/baselines.py:49-73` (5 seeded shuffles, n_modules, A_inferred_cves) |
| 163 | precision@100/1,000/10,000 by priority per label; lift; rank-biserial | DESIGN.md:L278-L280 | VERIFIED | `config/eval.yaml:2`; `sis/evaluate/metrics.py:33-72` (lift = precision / base; rank-biserial = 2 AUC - 1) |
| 164 | Ablation with each fact removed | DESIGN.md:L281-L282 | VERIFIED | `sis/evaluate/ablation.py:21-35` (no_A/B/C zero weight and renormalise; no_D all multipliers = untouched) |
| 165 | label_has_vendor sanity: displace rate far above untouched; exposure distributions of the 2 segments side by side | DESIGN.md:L283-L286 | VERIFIED | `metrics.py:119-132`; `EVAL_REPORT` sanity: displace 100%, untouched 0%; p10-p99 table |
| 166 | Measured at scoring_version 1.1.0, Wilson 95% intervals | DESIGN.md:L288-L290 | VERIFIED | `EVAL_REPORT:3`; `config/eval.yaml:3` z 1.96; `metrics.py:23-30` |
| 167 | label_any_tested: p@100 3.0% [1.0, 8.5], p@1,000 3.9% [2.9, 5.3], p@10,000 1.6% [1.3, 1.8], lift@1,000 27.9, rb 0.597 | DESIGN.md:L294 | VERIFIED | `EVAL_REPORT:95` (3.00 [1.03, 8.45], 3.90 [2.87, 5.29], 1.57 [1.34, 1.83], 27.90, 0.597) |
| 168 | label_kev: 55.0% [45.2, 64.4], 49.1% [46.0, 52.2], 62.6% [61.6, 63.5], 4.8, 0.917 | DESIGN.md:L295 | VERIFIED | `EVAL_REPORT:31` |
| 169 | k=1,000 any_tested: random 0.12%, breadth_only 3.4%, cve_count_only 3.3%; no_A 2.8%, no_B 2.3%, no_C 2.3%, no_D 4.5% | DESIGN.md:L297-L299 | VERIFIED | `EVAL_REPORT:97-103` |
| 170 | About 28x richer than chance; edges past breadth_only, intervals overlap; rb 0.597 vs 0.124 | DESIGN.md:L299-L304 | VERIFIED | `EVAL_REPORT:95,98` ([2.87, 5.29] vs [2.44, 4.71]) |
| 171 | Removing D raises p@1,000 (4.5% vs 3.9%), less than at 1.0.0 (6.6% vs 5.1%) | DESIGN.md:L304-L307 | VERIFIED | `docs/P3_1_REPORT.md:108,116-117` |
| 172 | P3.1 fixes lowered headline precision; removed hosting zones held tested positives | DESIGN.md:L307-L309 | VERIFIED | `docs/P3_1_REPORT.md:108-109,143-146` |
| 173 | Untouched only p@1,000 any_tested 3.4% [2.4, 4.7] vs 0.19% base | DESIGN.md:L309-L311 | VERIFIED | `EVAL_REPORT` untouched table: 3.40% [2.44, 4.71], base 0.194% |
| 174 | label_kev is downstream of the version strings fact A reads | DESIGN.md:L313-L315 | VERIFIED | `findings/07_clusters.md` K1 note; no_A rb on kev 0.334 (`EVAL_REPORT:36`) |
| 175 | Design reserves a place for sales reply rate (section 10) | DESIGN.md:L316-L318 | VERIFIED | `DESIGN.md:L508-512`; `evals/README.md:43-57` (designed, not populated) |
| 176 | CI runs `pytest -m eval` on a committed 50,000-entity fixture against a committed threshold (mechanics only; the "cannot merge" conclusion is a FALSE row) | DESIGN.md:L320-L322 | VERIFIED | `.github/workflows/ci.yml:18-25`; bundle committed (`git ls-files`), 50,000 rows (checked), `tests/test_eval.py:73-77`; `tests/eval_thresholds.json:2` = 0.0209 (0.95 x fixture 0.022, `config/eval.yaml:11`). label_kev is gated too (0.5814). |
| 177 | Product makes no LLM calls; scoring uses no LLM | DESIGN.md:L327, L335 | VERIFIED | No `openai`/httpx client use or model id anywhere in `sis/` (grep); `openai` is only a dependency (`pyproject.toml:12`). |
| 178 | Rules give 100 percent reproducibility | DESIGN.md:L333 | VERIFIED | Rescore byte-identical (md5) `tasks/state.md:101`; rescore max abs diff 0 `tasks/state.md:83`. |
| 179 | Repo holds gateway config `config/llm_tiers.yaml` and validated loader `sis/llm/tiers_config.py` | DESIGN.md:L339-341 | VERIFIED | Both exist; loader validates tiers, tasks, 2-3 distinct models, budget sum (`sis/llm/tiers_config.py:21-59`); tests `tests/test_scaffold.py:188-226`. |
| 180 | Cards P7 and P8 carry validation protocols and cost accounting | DESIGN.md:L341-342 | VERIFIED | `cards/P7.md:76-118`, `cards/P8.md:73-100`. |
| 181 | Gateway "configured, not exercised" | DESIGN.md:L344 | VERIFIED | `tiers_config.load` is called only from `tests/test_scaffold.py:189`; no runtime caller. |
| 182 | No code names a model; a task maps to a tier, tier to an ordered model list via 1 OpenAI-compatible router | DESIGN.md:L346-348 | VERIFIED | `config/llm_tiers.yaml:7,31-35` router openrouter, tasks -> tier; `sis/config.py:22` LLM_BASE_URL openrouter; no model id in `sis/`. |
| 183 | 2 models per tier, ids verified on OpenRouter 2026-11-02 | DESIGN.md:L350 | VERIFIED | `config/llm_tiers.yaml:2,6` models_verified_on 2026-11-02; 2 models each tier. |
| 184 | reasoning tier for judging, 20 rpm, 2 concurrent, 2.5 USD; "frontier class" | DESIGN.md:L352 | VERIFIED | `config/llm_tiers.yaml:9-16,34` (kimi-k3, claude-sonnet-5.5), task judge -> reasoning. |
| 185 | mid tier for report card explanations, 60 rpm, 4 concurrent, 4.0 USD | DESIGN.md:L353 | VERIFIED | `config/llm_tiers.yaml:17-23,33` reportcard -> mid. (Model class is row 21.) |
| 186 | errand tier for classifying 5,000 businesses, Haiku class or free route, 120 rpm, 8 concurrent, 3.5 USD | DESIGN.md:L354 | VERIFIED | `config/llm_tiers.yaml:24-30,32` gemma-4-31b-it:free + claude-haiku-5.5; `sis/config.py:19` CLASSIFY_TOP_N 5000. |
| 187 | Per-tier rate limiting, fallback to 2nd model, 1-step escalation after 2 schema failures, log row per attempt | DESIGN.md:L356-361 | VERIFIED | Labelled as design; configured as rpm/concurrency, 2-model lists, `escalation.max_steps: 1` (`config/llm_tiers.yaml:36-37`); behaviour specified in `cards/P7.md:37-57`. Not built, consistent with "not exercised". |
| 188 | Hard budget per tier plus a reserve | DESIGN.md:L357-358 | VERIFIED | `config/llm_tiers.yaml:39` reserve_usd 2.0; sum 12.0 checked against LLM_BUDGET_USD_TOTAL 12.0 (`sis/llm/tiers_config.py:56-59`, `sis/config.py:23`). The run-stopping behaviour is designed only (`cards/P7.md:41-42`), as labelled. |
| 189 | Flattened data keeps title, cert org, web components, server header, hostnames, first 2,000 chars of each response | DESIGN.md:L365-368 | VERIFIED | `sis/ingest/flatten.py:33,38,42,198,207,222` (`data[:2000]`). |
| 190 | Classifier on errand tier, top 5,000 by priority, fixed taxonomy, 1-line description, confidence | DESIGN.md:L368-371 | VERIFIED | `cards/P7.md:3-11,63-64,106`; `config/industry_taxonomy.yaml` (22 values, `tests/test_scaffold.py:182-185`). |
| 191 | 200 hand-labelled, 50 relabel, ship at 0.80 accuracy, same set through every errand model and mid primary | DESIGN.md:L371-374 | VERIFIED | `cards/P7.md:80-105`. |
| 192 | Report card: 2 sentences per finding from evidence only; no browsing or scanning | DESIGN.md:L377-383 | VERIFIED | `cards/P8.md:42-46,116-119`. |
| 193 | 50 cards judged on reasoning tier vs 30 human-scored; cost per card logged | DESIGN.md:L386-387 | VERIFIED | `cards/P8.md:64-67,91-95`. |
| 194 | Ingest 712.6 s at 20,501 lines/s; 2.7 GB Parquet out | DESIGN.md:L397-399 | VERIFIED | `docs/INGEST_REPORT_8e25...md:14-17` (2,269,098,353 + 424,266,236 bytes). |
| 195 | About 120 files a day on 1 laptop (ingest) | DESIGN.md:L399-400 | VERIFIED | 86,400 / 712.6 = 121. |
| 196 | 16 GB raw per file; 14.6 million raw rows | DESIGN.md:L416, L440 | VERIFIED | `findings/00_format.md:4` 17,619,943,483 bytes (16.4 GiB); 14,608,407 lines (`docs/INGEST_REPORT_8e25...md:9`). |
| 197 | Merge rebuilds current/ from all per-file tables; last_seen_file exists | DESIGN.md:L420-424 | VERIFIED | `sis/entities/resolve.py:313-350`, `sis/scoring/score.py:141-174`. Upsert/stale is a plan. |
| 198 | DuckDB in-process over a bundle | DESIGN.md:L425 | VERIFIED | `docs/DEPLOY.md:16-17`; bundle serves 4,549,051 evidence rows. |
| 199 | Diff keys on entity_id + ip:port; repeated observations not "new" | DESIGN.md:L429-431 | VERIFIED | `sis/delta/diff.py:94-100` skey = ip:port per entity. |
| 200 | 487,133 and 476,560 active entities, 148,368 events | DESIGN.md:L433-434 | VERIFIED | `docs/DELTA_REPORT_*.md` header; `tasks/state.md:6`. |
| 201 | Diff 38 to 93 s over 4 runs (37.8, 43.1, 45.5, 93.1) | DESIGN.md:L434-436 | VERIFIED | `tasks/state.md:8`. |
| 202 | Second file ingest 786 s, resolve 193 s, score 267 s | DESIGN.md:L437-438 | VERIFIED | `docs/INGEST_REPORT_61ea...md:14` 785.9; `docs/RESOLVE_REPORT_61ea...md:3` 193.2; `docs/SCORE_REPORT_61ea...md:3` 267.4. |
| 203 | Diff reads entity, score, signal, evidence tables plus banners' ip, port, module | DESIGN.md:L438-440 | VERIFIED | `sis/delta/diff.py:78-106` (also reads banner_entity.parquet to attribute banners). |
| 204 | Outputs byte-identical on rerun; same seed gave same file_id | DESIGN.md:L440-442 | VERIFIED | `tasks/state.md:8` (md5), `tasks/state.md:4`. |
| 205 | 1 Fly machine, shared-cpu-1x, 1 GB, fra, always on, bundle baked into image | DESIGN.md:L446-447 | VERIFIED | `fly.toml:4,10-12,21-23`; `Dockerfile:17`. |
| 206 | Live at https://sis-niranjan.fly.dev/ since 2026-11-03 | DESIGN.md:L448 | VERIFIED | `docs/DEPLOY.md:3-6`. |
| 207 | 7.73 USD a month in fra, 6.70 USD cheapest; IPv4 and registry free; egress not measured | DESIGN.md:L448-452 | VERIFIED | `docs/DEPLOY.md:9-11`. |
| 208 | No database, no object storage, no secrets, Logfire optional and unset | DESIGN.md:L452-453 | VERIFIED | `docs/DEPLOY.md:16,95-97`; `sis/config.py:24`. |
| 209 | Render free recorded in P5 as the zero-cost alternative | DESIGN.md:L455-456 | VERIFIED | `cards/P5.md:90-91` (as fallback if Fly fails). |
| 210 | Explorer caught 2 own errors (na placeholder, null-handling in lift baselines) | DESIGN.md:L475-477 | VERIFIED | `findings/02_population.md:7-8`; `findings/REPORT.md:131-133`. |
| 211 | Model choice per card recorded in the card | DESIGN.md:L479-480 | VERIFIED | `Model:` line 3 of every `cards/P*.md`. |
| 212 | Model has 4 facts | DESIGN.md:L486 | VERIFIED | `config/scoring.yaml:5-30` facts a, b, c, d. |
| 213 | Card contract: inputs, outputs with paths, steps, acceptance tests, does NOT do, handoff | DESIGN.md:L489-491 | VERIFIED | e.g. `cards/P7.md` sections Inputs, Outputs, Steps, Acceptance tests, Does NOT do, Handoff report. |
| 214 | Automated: profiling scripted; ingest row-count reconciliation; eval pytest in CI with a threshold | DESIGN.md:L494-496 | VERIFIED | `findings/queries/*.py`; `sis/ingest/run.py:333-335` ReconciliationError; `.github/workflows/ci.yml:18-25`, `tests/eval_thresholds.json`. |
| 215 | Cutoff, weights, multipliers written down as settings | DESIGN.md:L501-503 | VERIFIED | `sis/config.py:17` ROLLUP_MAX_IPS 50; `config/scoring.yaml:5-55`. |
| 216 | UI has 1-click "mark as prospect" and "not a fit" per account | DESIGN.md:L509-510 | VERIFIED | `sis/api/templates/account.html:48-56`; `sis/api/routes.py:219-222,302`. |
| 217 | Outreach email drafting not built | DESIGN.md:L516-517 | VERIFIED | No outreach/email code in `sis/` (grep). |
| 218 | UI: server-rendered tables and 1 detail page; 1 readability pass (overview, plain reasons, dark and light); no framework, no build step | DESIGN.md:L518-523 | VERIFIED | Jinja templates `sis/api/templates/`; `cards/P5_1.md`; `sis/api/labels.py`; `sis/api/static/tokens.css`; htmx from CDN only (`base.html:14`), no package.json. |
| 219 | Screenshots in docs/ui/, listed in docs/UI_REPORT.md | DESIGN.md:L520 | VERIFIED | 12 PNGs in `docs/ui/`; `docs/UI_REPORT.md:8-23`. |
| 220 | Raw file is 123 GB, never hosted | DESIGN.md:L527 | VERIFIED | `findings/00_format.md:7-8` 122,782,583,953 bytes; `Dockerfile` copies only the bundle. |
| 221 | ROLLUP_MAX_IPS is a setting shown in the UI footer with the bundle version | DESIGN.md:L531-532 | VERIFIED | `sis/config.py:17`; `sis/api/templates/base.html:42-43`. |
| 222 | Fact A partly circular with label_kev, reported with ablations and tested labels | DESIGN.md:L533-534 | VERIFIED | `docs/P3_1_REPORT.md` no_A 0.334; `evals/README.md` label table. |
| 223 | At 1.0.0, 95 of top 100 were hosting/network operators; each under 50 IPs | DESIGN.md:L537-542 | VERIFIED | `docs/P3_1_REPORT.md:169-171`; `cards/P3_1.md` defect 1. |
| 224 | P4 showed low_surface held tested positives at untouched's rate; 1,192 kev labels from edge banners only | DESIGN.md:L542-544 | VERIFIED | `cards/P3_1.md:52` (defect 2), `cards/P3_1.md:81`. |
| 225 | 3 rulings: template-zone rule, templated-hostname rule, hand list of 129 names from top 100 twice | DESIGN.md:L544-546 | VERIFIED | `docs/P3_1_REPORT.md:10-15,194` (57 + 72 = 129). |
| 226 | Prerequisite gains C_any_service; low_surface 163,897 -> 5,613 | DESIGN.md:L546-548 | VERIFIED | `config/scoring.yaml:47`; `docs/P3_1_REPORT.md:76`. |
| 227 | Labels skip edge banners as scoring does | DESIGN.md:L548-549 | VERIFIED | `sis/evaluate/labels.py:34` edge_predicate fragment; `cards/P3_1.md:79-90`. |
| 228 | Top 30 has no hosting provider; 57 of top 100 do; rules miss server123/vm612; target under 10 not met | DESIGN.md:L549-553 | VERIFIED | `docs/P3_1_REPORT.md:169-177`. |
| 229 | P6 synthetic second file from the real one with a seed; UI and reports say simulation | DESIGN.md:L554-556 | VERIFIED | `docs/DELTA_REPORT_*.md:5`; `sis/api/templates/account.html:97`, `overview.html:41`. |
| 230 | 3 of 5 change types meet their bar; cert expiry 94.9 vs 95; added vulns 73.6; every miss in a named category | DESIGN.md:L557-560 | VERIFIED | `config/delta.yaml:34-40` (5 bars); `docs/DELTA_REPORT_*.md` recall table and misses table (unexplained 0 everywhere). |
| 231 | Strix release gate not run before submission | DESIGN.md:L562 | VERIFIED | `tasks/state.md:20,22,39`. |
| 232 | Offline tables are Parquet under `$SIS_DATA/<file_id>/...` and `$SIS_DATA/current/...` | DATA_MODEL.md:L11-13 | VERIFIED | `sis/paths.py:21-22,55-56`. |
| 233 | `$SIS_DATA` defaults to `C:/Users/NIRANJAN VSKS/sis_data`, never in repo | DATA_MODEL.md:L13-14 | VERIFIED | `sis/config.py:11-12`. |
| 234 | Same convention for P2 per-file tables (banner_entity, entities, unattributed_summary) | DATA_MODEL.md:L15-17 | VERIFIED | `sis/entities/resolve.py:276-280` writes `resolve_meta.json` with built_at, pipeline_version, rollup_max_ips, tables list. Note: P3 rewrites entities.parquet later (`scoring/peer.py:71-74`) without updating that sidecar. |
| 235 | Convention: per-file signals/evidence/scores traceable via sidecar | DATA_MODEL.md:L15-17 | VERIFIED | `score.py:144-149` writes `score_meta.json` with built_at, pipeline_version and tables [signals, evidence, scores] |
| 236 | IDs deterministic, byte-identical on rerun, no autoincrement | DATA_MODEL.md:L18-19 | VERIFIED | entity_id = sha1 (`06_banner_entity.sql:20`), file_id = sha256 (`file_id.py:10-26`); `tests/test_resolve.py:296-306` compares parquet bytes of two runs; grep finds no autoincrement/sequence/uuid4 (synth uses uuid5, `sis/delta/synth.py:84`). |
| 237 | Timestamps are UTC | DATA_MODEL.md:L20 | VERIFIED | `run.py:71-72,271` (UTC, tz stripped); `resolve.py:277`. |
| 238 | A delivery is 1 compressed JSONL file, never modified | DATA_MODEL.md:L26 | VERIFIED | zstd magic check `run.py:292`; file opened read-only `file_id.py:19`, `sis/ingest/reader.py`. |
| 239 | file_id = sha256 of first 64 MiB, hex, '-' total byte length ('-' because Windows) | DATA_MODEL.md:L29-31 | VERIFIED | `sis/ingest/file_id.py:6,10-26`; `tests/test_ingest.py:49-77`. |
| 240 | Real value 8e252f8f...-17619943483 | DATA_MODEL.md:L31 | VERIFIED | `docs/INGEST_REPORT_8e252f8f...-17619943483.md:1,9` (byte length 17,619,943,483). |
| 241 | original_name VARCHAR, byte_length BIGINT, received_at TIMESTAMP | DATA_MODEL.md:L32-34 | VERIFIED | Not a separate table; stored as ingest_log columns `log.py:13`; set at `run.py:268-271`. received_at = file mtime in UTC, original_name = `path.name`. |
| 242 | banners path `$SIS_DATA/<file_id>/banners/part-*.parquet` | DATA_MODEL.md:L43 | VERIFIED | `run.py:147` `part-{idx:05d}.parquet`, moved to file_dir `run.py:360`. |
| 243 | banners grain 1 row per banner, key `id` = `_shodan.id`, unique | DATA_MODEL.md:L44 | VERIFIED | `flatten.py:116-118,164`; uniqueness `findings/06_relationships.md:15`, `findings/02_columns.csv:2`. Not enforced by code. |
| 244 | Exactly the 93 columns of findings/02_columns.csv, flattener at sis/ingest/flatten.py | DATA_MODEL.md:L46-48 | VERIFIED | `flatten.py:23-50` has 94 columns = the 93 CSV names + file_id (checked by script: no name differs). |
| 245 | The 53 "important" columns listed exist | DATA_MODEL.md:L52-61 | VERIFIED | All present in `flatten.py:23-50`. `data` cut to 2,000 chars `flatten.py:222`; `http_headers` JSON string `flatten.py:201`. |
| 246 | Plus 1 column `file_id VARCHAR` | DATA_MODEL.md:L64 | VERIFIED | `flatten.py:49,228`. |
| 247 | vulns path `$SIS_DATA/<file_id>/vulns/part-*.parquet` | DATA_MODEL.md:L68 | VERIFIED | `run.py:149-150,337-339`. |
| 248 | vulns grain 1 row per (banner, CVE) | DATA_MODEL.md:L69 | VERIFIED | `flatten.py:121-139` one row per key of the `vulns` dict. |
| 249 | vulns = explorer's schema, unchanged | DATA_MODEL.md:L71 | VERIFIED | `tests/test_ingest.py:118-139,192` compare against the explorer flattener. |
| 250 | vulns columns id, module, cve VARCHAR; cvss, cvss_version, cvss_v2, epss, ranking_epss DOUBLE; verified, kev BOOLEAN; summary, other_keys, file_id VARCHAR | DATA_MODEL.md:L74-88 | VERIFIED | `flatten.py:51-55`. |
| 251 | `kev` null when absent | DATA_MODEL.md:L83 | VERIFIED | `flatten.py:134`. |
| 252 | `summary` first 500 chars | DATA_MODEL.md:L85 | VERIFIED | `flatten.py:136`. |
| 253 | `other_keys` JSON of every other key; ransomware_campaign 'Known'/'Unknown'/null | DATA_MODEL.md:L86-87 | VERIFIED | `flatten.py:125-137`; values `findings/06_relationships.md:99`. |
| 254 | Join vulns to banners on `vulns.id = banners.id` | DATA_MODEL.md:L91-92 | VERIFIED | Same `rid` in both rows `flatten.py:129,164`. |
| 255 | ingest_log path `$SIS_DATA/ingest_log.parquet`, rewritten atomically per append | DATA_MODEL.md:L96-97 | VERIFIED | `paths.py:88-89`; `log.py:31-42` (tmp + os.replace); `tests/test_ingest.py:307`. |
| 256 | ingest_log columns and types (times TIMESTAMP, counts BIGINT, wall_seconds DOUBLE, pipeline_version/error VARCHAR, dropped_reasons JSON VARCHAR) | DATA_MODEL.md:L100-106 | VERIFIED | `log.py:11-21`; written `run.py:280-289`. |
| 257 | banner_entity path `$SIS_DATA/<file_id>/banner_entity.parquet` | DATA_MODEL.md:L115 | VERIFIED | `resolve.py:264-266`. |
| 258 | A banner can map to >1 entity; most map to 0 or 1 | DATA_MODEL.md:L116-117 | VERIFIED | `tests/test_resolve.py:226-229`; RESOLVE_REPORT_8e25 L26-28: 92.94% of banners map to none. |
| 259 | banner_entity columns banner_id, entity_id, key_kind, key_value, attribution, file_id (VARCHAR) | DATA_MODEL.md:L120-125 | VERIFIED | `resolve.py:264-265`; `06_banner_entity.sql:20-22`. |
| 260 | entity_id = sha1(key_kind ':' key_value), hex, 40 chars | DATA_MODEL.md:L121 | VERIFIED | `06_banner_entity.sql:20`; `tests/test_resolve.py:269`. |
| 261 | key_kind 'domain' \| 'cert_cn' \| 'http_host' | DATA_MODEL.md:L122 | VERIFIED | `01_names.sql:5,9,18`; `06_banner_entity.sql:7-8,11,15`. |
| 262 | Rule 1: lowercase, strip trailing dot, strip leading www., needs a dot, not an IP | DATA_MODEL.md:L130-131 | VERIFIED | `sis/entities/normalise.py:20-33` (also rejects '..', bad chars, numeric last label). |
| 263 | Rule 2: primary = each `domains` element with coverage <= ROLLUP_MAX_IPS (default 50); coverage = distinct coalesce(ip_str, ipv6) | DATA_MODEL.md:L132-134 | VERIFIED | `01_names.sql:6`; `02_coverage.sql:3`; `04_primary.sql:5`; `config.py:17`; `tests/test_resolve.py:111`. |
| 264 | Rule 3: fallback only with 0 primary; cert CN and each SAN first, then http_host if not IP; registered domain via tldextract; same cutoff on fallback coverage | DATA_MODEL.md:L135-140 | VERIFIED | `05_fallback.sql:6-16`; `normalise.py:36-62`; `tests/test_resolve.py:182-197`. |
| 265 | Rule 4: a name in config/operator_domains.txt never becomes an entity; seeded with incapdns.net ... akamaitechnologies.com and every domain over the cutoff | DATA_MODEL.md:L141-145 | VERIFIED | Exclusion `04_primary.sql:5`, `05_fallback.sql:11`; seed `config/operator_domains.txt:1-5`; derived section `config/operator_domains.txt:147`, written by `resolve.py:221-224`. |
| 266 | Rule 5: over-cutoff cert/Host name still attributed when it is a primary domain entity; 4,729 banners otherwise | DATA_MODEL.md:L146-149 | VERIFIED | `05_fallback.sql:10`; `tests/test_resolve.py:218-223`; RESOLVE_REPORT_8e25 L221. |
| 267 | Rule 6: operator_domain never produced; B01/B02 tags in config/blocked_tags.yaml | DATA_MODEL.md:L150-152 | VERIFIED | `07_entities.sql:37`; `config/blocked_tags.yaml:4-5`; `resolve.py:193-213`. |
| 268 | entities paths per file and `current/entities.parquet` | DATA_MODEL.md:L156-157 | VERIFIED | `resolve.py:267,334-346`; `sis resolve --merge` `sis/cli.py:43-52`. |
| 269 | entities columns entity_id..n_modules, country_code(s), org_mode, cloud_providers, first/last_seen_file, status, file_id with stated types | DATA_MODEL.md:L161-177 | VERIFIED | `07_entities.sql:12-39`; `tests/test_resolve.py:256-276`. counts are count() = BIGINT; lists VARCHAR[]. |
| 270 | country_code = mode, ties alphabetical; org_mode = mode of org | DATA_MODEL.md:L168,170 | VERIFIED | `07_entities.sql:21,26`; `tests/test_resolve.py:271-272`. |
| 271 | country_codes distinct; cloud_providers distinct non-null | DATA_MODEL.md:L169,171 | VERIFIED | `07_entities.sql:16-17,33-34` (list_distinct drops nulls); test L271,273. |
| 272 | first_seen_file / last_seen_file are file_ids | DATA_MODEL.md:L172-173 | VERIFIED | Per file both = file_id `07_entities.sql:35`; merge picks earliest/latest by received_at `resolve.py:336-346`. |
| 273 | status 'active' \| 'blocked' | DATA_MODEL.md:L174 | VERIFIED | `07_entities.sql:36`. |
| 274 | blocked when any banner matches B01 or B02 (findings/07_what_we_sell_map.csv) | DATA_MODEL.md:L180-181 | VERIFIED | `07_entities.sql:8-9,18,36`; tag lists in `config/blocked_tags.yaml:1-5` cite the CSV; `tests/test_resolve.py:232-253`. (The "or operator domain" half is row 37.) |
| 275 | Blocked entities kept, never scored or shown | DATA_MODEL.md:L182-183 | VERIFIED | Kept in entities.parquet; filtered `sis/signals/sql/01_vulns_clean.sql:8`, `sis/scoring/sql/01_peer.sql:8`, `sis/export/bundle.py:99,103`. |
| 276 | unattributed_summary path, 1 row per reason | DATA_MODEL.md:L187-188 | VERIFIED | `resolve.py:268-275`. |
| 277 | reason 'no_name' \| 'operator_only' \| 'over_cutoff' \| 'blocked'; n_banners BIGINT; pct DOUBLE | DATA_MODEL.md:L191-193 | VERIFIED | `resolve.py:255-260,273-274`; `tests/test_resolve.py:279-291`. pct is a 0-1 fraction, not a percent. |
| 278 | signals path `$SIS_DATA/<file_id>/signals.parquet` | DATA_MODEL.md:L202 | VERIFIED | `sis/signals/compute.py:74-77` |
| 279 | signals grain: 1 row per (entity, signal); only present signals stored, plus always-present breadth signals | DATA_MODEL.md:L203-204 | VERIFIED | `compute.py:43-57` (non-always rows only `WHERE f_<id>` GROUP BY entity; always rows LEFT JOIN from `peer`, value 0); `catalogue.py:98-101` `always=True` only for the 2 breadth signals |
| 280 | signals.entity_id VARCHAR | DATA_MODEL.md:L207 | VERIFIED | `compute.py:75` |
| 281 | signals.signal_id VARCHAR | DATA_MODEL.md:L208 | VERIFIED | `compute.py:50` literal |
| 282 | signals.fact VARCHAR 'A'..'X' | DATA_MODEL.md:L209 | VERIFIED | `compute.py:50`; `catalogue.py:41` Literal A/B/C/D/X |
| 283 | signals.value DOUBLE | DATA_MODEL.md:L210 | VERIFIED | `compute.py:48` `CAST(... AS DOUBLE)` |
| 284 | signals.n_banners BIGINT, banners that fire it | DATA_MODEL.md:L211 | VERIFIED | `compute.py:49` `count(*)` over firing rows (BIGINT) |
| 285 | signals.pct_in_peer DOUBLE, percent_rank within peer_group, null for 0/1 | DATA_MODEL.md:L212 | VERIFIED | `sis/signals/sql/03_pct.sql:6-12` (flag -> NULL; `* |
| 286 | signals.file_id VARCHAR | DATA_MODEL.md:L213 | VERIFIED | `compute.py:76` |
| 287 | 24 signals | DATA_MODEL.md:L216 | VERIFIED | `catalogue.py:51-123` (6 A, 4 B, 8 C, 5 D, 1 X); `tests/test_signals.py:32-37` |
| 288 | A_fingerprinted: 0/1, len(cpe23)>0 or version not null | DATA_MODEL.md:L222 | VERIFIED | `catalogue.py:52-53` |
| 289 | A_inferred_cves: max n_vulns over banners, n_vulns > 0 (from clean vulns) | DATA_MODEL.md:L223 | VERIFIED | `catalogue.py:56-57` `max(n_clean)` where `n_clean > 0`; `sql/01_vulns_clean.sql:10` |
| 290 | A_max_cvss: max max_cvss, n_vulns > 0 | DATA_MODEL.md:L224 | VERIFIED | `catalogue.py:59-60` `max(max_clean_cvss)` |
| 291 | A_eol: eol-product or eol-os tag | DATA_MODEL.md:L225 | VERIFIED | `catalogue.py:62-63` |
| 292 | A_os_leak: os not null | DATA_MODEL.md:L226 | VERIFIED | `catalogue.py:65` |
| 293 | A_cpe_per_header value: max len(cpe23)/greatest(len(http_header_names),1) | DATA_MODEL.md:L227 | VERIFIED | `catalogue.py:68` (predicate: see row 38) |
| 294 | B_self_signed: cert_self_signed or tag self-signed | DATA_MODEL.md:L228 | VERIFIED | `catalogue.py:71-72` |
| 295 | B_expired: cert_expired = true | DATA_MODEL.md:L229 | VERIFIED | `catalogue.py:74` |
| 296 | B_legacy_tls: ssl_version in (SSLv3, TLSv1.0) or ssl_versions has 'SSLv3'/'TLSv1' without leading '-' | DATA_MODEL.md:L230 | VERIFIED | `catalogue.py:76-80` exact `list_has_any(ssl_versions, ['SSLv3','TLSv1'])`; `tests/test_signals.py:80` |
| 297 | B_cert_age_days: max date_diff day cert_issued->timestamp clipped [0,7300], cert_issued > 1990-01-01 | DATA_MODEL.md:L231 | VERIFIED | `catalogue.py:83-86` |
| 298 | C_admin_services: count distinct of 10 admin modules, data_len>0, not cdn (P02) | DATA_MODEL.md:L232 | VERIFIED | `catalogue.py:23-24,87-90`; same predicate as P02 `config/what_we_sell_map.csv:10` |
| 299 | C_windows_internals: blocks has ntlm or os like Windows% | DATA_MODEL.md:L233 | VERIFIED | `catalogue.py:91-93` |
| 300 | C_asset_tags: count distinct of 6 tags | DATA_MODEL.md:L234 | VERIFIED | `catalogue.py:25,94-97` |
| 301 | C_breadth_modules / C_breadth_ports always present | DATA_MODEL.md:L235-236 | VERIFIED | `catalogue.py:98-101` `always=True` (value: see rows 39, 40) |
| 302 | C_components_vs_peers value: max len(http_components) | DATA_MODEL.md:L237 | VERIFIED | `catalogue.py:103` (predicate: see row 41) |
| 303 | C_live_web: 0/1, mapping P01 | DATA_MODEL.md:L238 | VERIFIED | `catalogue.py:105-106` `{P01}`, edge_ok; `what_we_sell_map.csv:9` |
| 304 | C_any_service: non-edge banner with data_len>0 OR module not in ('auto') | DATA_MODEL.md:L239 | VERIFIED | `catalogue.py:109-110` + edge guard `catalogue.py:144` |
| 305 | D_waf: mapping W01 | DATA_MODEL.md:L240 | VERIFIED | `catalogue.py:111` |
| 306 | D_edge_substitute: W02 | DATA_MODEL.md:L241 | VERIFIED | `catalogue.py:112-113` |
| 307 | D_security_appliance: W03 or W04 | DATA_MODEL.md:L242 | VERIFIED | `catalogue.py:114-115` |
| 308 | D_vpn: W05 or W06 | DATA_MODEL.md:L243 | VERIFIED | `catalogue.py:116-117` |
| 309 | D_hardening_headers: W07 | DATA_MODEL.md:L244 | VERIFIED | `catalogue.py:118-120` |
| 310 | X_small_cloud: cloud_provider in (DigitalOcean, Vultr, Linode), weight 0 | DATA_MODEL.md:L245 | VERIFIED | `catalogue.py:26,121-122`; no X term in `sis/scoring/sql/02_facts.sql` or `config/scoring.yaml` |
| 311 | Held out (kev, verified, ransomware_campaign, opts_heartbleed, opts_vulns) never a signal input | DATA_MODEL.md:L247-249 | VERIFIED | `sis/signals/sql/02_eb.sql:6-13` carries none of them; ransomware/opts read only in `sis/evaluate/sql/01_labels.sql:11,22-23` |
| 312 | A_inferred_cves / A_max_cvss from vulns rows with kev null/false AND verified false; banner n_vulns/max_cvss not read | DATA_MODEL.md:L249-252 | VERIFIED | `01_vulns_clean.sql:13` (`coalesce(verified,false)=false`, so a null verified counts as false); `02_eb.sql` does not select n_vulns/max_cvss; `tests/test_signals.py:54` |
| 313 | evidence path `$SIS_DATA/<file_id>/evidence.parquet` | DATA_MODEL.md:L256 | VERIFIED | `sis/signals/evidence.py:40` |
| 314 | evidence grain (entity, signal, banner), cap 5, largest data_len then lowest port | DATA_MODEL.md:L257-258 | VERIFIED | `evidence.py:11,24-25,30` (extra tie-break banner_id); `tests/test_signals.py:126` |
| 315 | evidence entity_id, signal_id, banner_id VARCHAR | DATA_MODEL.md:L261 | VERIFIED | `evidence.py:20,28` |
| 316 | evidence.ip = coalesce(ip_str, ipv6) | DATA_MODEL.md:L262 | VERIFIED | `02_eb.sql:6` |
| 317 | evidence.port BIGINT | DATA_MODEL.md:L263 | VERIFIED | `02_eb.sql:6`; `sis/ingest/flatten.py:21,25` port int64 |
| 318 | evidence.module VARCHAR | DATA_MODEL.md:L264 | VERIFIED | `evidence.py:20` |
| 319 | evidence.field = source column, e.g. http_waf, cpe23, cert_expires | DATA_MODEL.md:L265 | VERIFIED | `evidence.py:21` `source_field`; `catalogue.py:74,111` |
| 320 | evidence.value text, max 300 chars | DATA_MODEL.md:L266 | VERIFIED | `evidence.py:12,22` |
| 321 | evidence.snippet first 300 chars of data, CR/LF collapsed | DATA_MODEL.md:L267 | VERIFIED | `02_eb.sql:11` (CR/LF runs become ' \| ', then cut to 300) |
| 322 | evidence.observed_at TIMESTAMP = banners.timestamp | DATA_MODEL.md:L268 | VERIFIED | `evidence.py:23`; `flatten.py:21,25` |
| 323 | evidence.file_id | DATA_MODEL.md:L269 | VERIFIED | `evidence.py:29` |
| 324 | scores paths per file and current | DATA_MODEL.md:L274-275 | VERIFIED | `score.py:140` and `score.py:190-191` |
| 325 | scores grain: 1 row per active entity | DATA_MODEL.md:L276 | VERIFIED | `score.py:80-90` wide from `peer`; `sis/scoring/sql/01_peer.sql:8` status='active' (current: latest file per entity, `score.py:182-188`) |
| 326 | fact_a, fact_b, fact_c DOUBLE 0..1 | DATA_MODEL.md:L280-282 | VERIFIED | `02_facts.sql:40-45` clipped `least(greatest(..,0),1)` |
| 327 | fact_d DOUBLE 0..1, protection present | DATA_MODEL.md:L283 | VERIFIED | `02_facts.sql:27-29` max of D weights; max weight 1.0 `config/scoring.yaml:32` |
| 328 | exposure DOUBLE 0..100 | DATA_MODEL.md:L284 | VERIFIED | `02_facts.sql:48`; weights 0.45+0.20+0.35 = 1 `scoring.yaml:40-42` |
| 329 | segment 4 values | DATA_MODEL.md:L285 | VERIFIED | `02_facts.sql:31-35` |
| 330 | priority DOUBLE 0..100 | DATA_MODEL.md:L286 | VERIFIED | `02_facts.sql:51-54`; multipliers <= 1 `scoring.yaml:52-55` |
| 331 | rank_overall BIGINT, 1 = highest priority | DATA_MODEL.md:L287 | VERIFIED | `sis/scoring/sql/03_rank.sql:5` row_number by priority desc |
| 332 | rank_in_segment BIGINT | DATA_MODEL.md:L288 | VERIFIED | `03_rank.sql:6-7` |
| 333 | rank_in_country BIGINT | DATA_MODEL.md:L289 | VERIFIED | `03_rank.sql:8-9` |
| 334 | top_signals VARCHAR[], up to 5 by contribution | DATA_MODEL.md:L290 | VERIFIED | `score.py:102,106` |
| 335 | scoring_version from config/scoring.yaml | DATA_MODEL.md:L291 | VERIFIED | `score.py:103,108`; `scoring.yaml:3` |
| 336 | scores.file_id | DATA_MODEL.md:L292 | VERIFIED | `score.py:103`; `03_rank.sql:10` |
| 337 | Formulas fixed in config/scoring.yaml | DATA_MODEL.md:L295 | VERIFIED | `score.py:66-77` binds every constant from config |
| 338 | entity_history path `$SIS_DATA/history/entity_history.parquet` | DATA_MODEL.md:L303 | VERIFIED | `sis/paths.py:67-68`; `diff.py:166` |
| 339 | entity_history grain (entity, file), append-only | DATA_MODEL.md:L304 | VERIFIED | `diff.py:154-171` adds the file's rows and keeps other files' rows. A rerun of the same file replaces that file's rows |
| 340 | entity_history columns = entities + scores columns | DATA_MODEL.md:L304-305 | VERIFIED | `diff.py:161-165` `e.*` plus every scores column not already in entities |
| 341 | events path `$SIS_DATA/history/events.parquet` | DATA_MODEL.md:L308 | VERIFIED | `paths.py:71-72`; `diff.py:135` |
| 342 | events grain: 1 row per change between consecutive files for an entity | DATA_MODEL.md:L310 | VERIFIED | `diff.py:111-125`; `01_events.sql:229-281` |
| 343 | event_id = sha1(entity_id\|\|event_type\|\|from_file\|\|to_file\|\|subject) | DATA_MODEL.md:L313 | VERIFIED | `01_events.sql:283`; `tests/test_delta.py:99` |
| 344 | events.entity_id, event_type, subject, from_file, to_file, from_value, to_value VARCHAR | DATA_MODEL.md:L314-318 | VERIFIED | `01_events.sql:283-285`; `bundle.py:15-18` schema (subject meaning: see row 42) |
| 345 | events.detected_at TIMESTAMP | DATA_MODEL.md:L319 | VERIFIED | `01_events.sql:285`; value = to_file's received_at `diff.py:117` |
| 346 | events.severity INTEGER 1..3 | DATA_MODEL.md:L320 | VERIFIED | `01_events.sql:286`; `config/delta.yaml:309-319`; `sis/delta_config.py:366-371` |
| 347 | 12 event types | DATA_MODEL.md:L323-326 | VERIFIED | `diff.py:23-26`; each emitted in `01_events.sql:230-281`; `tests/test_delta.py:130` |
| 348 | exposure_up/down threshold 10 points | DATA_MODEL.md:L325-326 | VERIFIED | `config/delta.yaml:308` 10.0, inclusive `01_events.sql:277`; `tests/test_delta.py:496` |
| 349 | industry taxonomy file config/industry_taxonomy.yaml | DATA_MODEL.md:L340 | VERIFIED | file exists, 20 industries + 2 fallbacks (config only, no consumer) |
| 350 | llm_calls task / tier names | DATA_MODEL.md:L370-371 | VERIFIED | `config/llm_tiers.yaml` tasks classify/reportcard/judge/mcp_agent, tiers errand/mid/reasoning; `sis/llm/tiers_config.py:13-14` (config only, table not built: row 63) |
| 351 | API never reads layers 1 to 4; reads 1 bundle | DATA_MODEL.md:L382 | VERIFIED | `sis/api/app.py:28-47` views over bundle files only; `routes.py:111` contributions read `b.dir/"signals.parquet"` |
| 352 | bundle path `$SIS_DATA/serve/<bundle_version>/` | DATA_MODEL.md:L384 | VERIFIED | `paths.py:59-60`; `bundle.py:66` |
| 353 | evidence.parquet in bundle: as 3.2, active entities only | DATA_MODEL.md:L388 | VERIFIED | `bundle.py:102-106` |
| 354 | events.parquet in bundle: as 4.2, last 2 files only | DATA_MODEL.md:L389 | VERIFIED | `bundle.py:76-80,110-111` newest (from, to) pair; `tests/test_delta.py:534` |
| 355 | signals.parquet in bundle: as 3.1, active entities only | DATA_MODEL.md:L390 | VERIFIED | `bundle.py:107-109` |
| 356 | bundle.json keys bundle_version, built_at, file_ids, scoring_version, n_accounts, n_evidence, pipeline_version | DATA_MODEL.md:L391-392 | VERIFIED | `bundle.py:118-124` |
| 357 | DuckDB in-process inside FastAPI, read-only | DATA_MODEL.md:L395 | VERIFIED | `app.py:35-47` in-memory connection, views over Parquet, no writes |
| 358 | Size on the order of 100s of MB | DATA_MODEL.md:L396-397 | VERIFIED | `docs/DEPLOY.md:31` size_mb 156.6 "Order of 100s of MB" holds; the stricter "a few hundred MB" in DESIGN.md:L74 is a FALSE row. |
| 359 | The bundle is the only artefact deployed | DATA_MODEL.md:L397 | VERIFIED | `Dockerfile:1-17`: code, config and DESIGN.md plus 1 bundle. The bundle is the only data deployed |
| 360 | Queried live: filtering, sorting, paging, lookup over the bundle | DATA_MODEL.md:L400 | VERIFIED | `routes.py:96-97,105-126` |
| 361 | eval path `$SIS_DATA/<file_id>/eval/` | DATA_MODEL.md:L408 | VERIFIED | `paths.py:38-39` |
| 362 | labels.parquet columns entity_id, label_kev, label_verified, label_heartbleed, label_opts_vulns, label_any_tested, label_has_vendor | DATA_MODEL.md:L411-412 | VERIFIED | `sis/evaluate/sql/01_labels.sql:37-43`; `labels.py:85-86` |
| 363 | metrics.json | DATA_MODEL.md:L413 | VERIFIED | `metrics.py:152` |
| 364 | ablations.json: metric per fact removed | DATA_MODEL.md:L414 | VERIFIED | `ablation.py:71-75` no_A..no_D |
| 365 | baselines.json: random, breadth-only, cve-count-only | DATA_MODEL.md:L415 | VERIFIED | `baselines.py:65-72` |
| 366 | CI eval on a fixed sample under tests/fixtures/, fails when p@1000 drops below the committed value | DATA_MODEL.md:L418-420 | VERIFIED | `.github/workflows/ci.yml` job eval `pytest -q -m eval`; `tests/test_eval.py:67-77`; `tests/eval_thresholds.json`; `paths.py:42-44` (scope of metrics: see row 45) |
| 367 | 16 GB Shodan export | README.md:L5 | VERIFIED | 17,619,943,483 bytes = 16.4 GiB (docs/INGEST_REPORT_8e25...:9; PHASE_CONFIG.md:38 "16.4 GB"). |
| 368 | 14.6 million service banners | README.md:L5 | VERIFIED | lines read 14,608,407, rows written 14,608,406 (docs/INGEST_REPORT_8e25...:10-11). |
| 369 | 487,133 named businesses | README.md:L6 | VERIFIED | active total 487,133 (docs/RESOLVE_REPORT_8e25...:16; docs/SCORE_REPORT_8e25...:7; docs/EVAL_REPORT_8e25...:3). |
| 370 | Each with an exposure score and a sales segment | README.md:L6-7 | VERIFIED | segments table sums to 487,133 (docs/SCORE_REPORT_8e25...:11-16); accounts.exposure/segment read in sis/api/routes.py:62. |
| 371 | Built in 5 days | README.md:L7-8 | VERIFIED | Commit dates 2026-10-30 (initial commit only), then 11-01 to 11-04 (`git log --date=short`); DESIGN.md:336 "inside the 5 days". |
| 372 | Linked paths exist: DESIGN.md, DATA_MODEL.md, EXPLORATION.md, findings/REPORT.md, cards/README.md, docs/, docs/DEPLOY.md, sis/config.py, tasks/state.md, tasks/lessons.md | README.md:L10-16, L54, L75, L92-93 | VERIFIED | All exist and are tracked (`git ls-files --error-unmatch`). |
| 373 | Overview shows how many are untouched | README.md:L20-21 | VERIFIED | Untouched tile (sis/api/templates/overview.html:21-28). |
| 374 | Overview shows how many already have a vendor | README.md:L21-22 | VERIFIED | "Has a vendor" tile, segment displace (overview.html:29-36). |
| 375 | Overview shows the exposure distribution | README.md:L22 | VERIFIED | 10-bucket histogram (overview.html:69-99; routes.py:45, 147-152). |
| 376 | Overview shows the most common reasons | README.md:L22 | VERIFIED | "Most common reasons", up to 8 A/B/C signals (overview.html:118-131; routes.py:47, 238-240). |
| 377 | Overview shows 10 accounts to start with | README.md:L22-23 | VERIFIED | START_HERE = 10 untouched by priority (routes.py:48, 241; overview.html:134-156). |
| 378 | Accounts list sorted by priority | README.md:L24 | VERIFIED | default `sort: Sort = "priority"` (routes.py:257); SORT_SQL priority DESC (routes.py:54). Note: a bare /accounts opens filtered to Untouched only (routes.py:264), not the whole book. |
| 379 | Filter by segment; Untouched and "Has a vendor" chips | README.md:L24-25 | VERIFIED | segment checkboxes (sis/api/templates/accounts.html:19-23); chip name "Has a vendor" (sis/api/labels.py:96). |
| 380 | Filter by country | README.md:L26 | VERIFIED | country select (accounts.html:30-31), `country_code = ?` (routes.py:82-85). Dropdown lists the top 20 countries (routes.py:156-158, 285). |
| 381 | Filter by minimum exposure | README.md:L26 | VERIFIED | min_exposure input 0-100 (accounts.html:42-43), `exposure >= ?` (routes.py:86-88). |
| 382 | Search a name | README.md:L26 | VERIFIED | `q` -> `display_name ILIKE` (routes.py:75-78; accounts.html:11-14). |
| 383 | Account header gives the exposure score and rank | README.md:L27 | VERIFIED | Exposure /100 and rank overall, in segment, in country (account.html:59-66). |
| 384 | 4 bars for the 4 facts: visibly old software, neglected certificates, exposed surface, protection present | README.md:L27-30 | VERIFIED | "The 4 facts" panel, fact_a..fact_d bars (account.html:112-126); names in labels.py:84-89 match. |
| 385 | Why panel gives top reasons in plain words | README.md:L30-31 | VERIFIED | "Why it ranks here", top WHY_MAX = 5 by contribution, plain `s.label` (routes.py:46, 291-293; account.html:78-92; labels.signal_sentence). |
| 386 | Raw banner evidence collapsed under each reason | README.md:L31 | VERIFIED | `<details class="disclose"><summary>Show evidence (n)` with ip:port, module, value, snippet (account.html:4-32). |
| 387 | "Mark as prospect" and "Not a fit" buttons record feedback | README.md:L32 | VERIFIED | account.html:48-55; POST /ui/feedback appends to feedback.jsonl (routes.py:169-181, 302-315); verdict prospect/not_fit (sis/api/schemas.py:102-105). |
| 388 | That feedback is the first real label the system collects | README.md:L32-33 | VERIFIED | DESIGN.md:508-512 "the first true labels this system has"; routes.py:170 "the 7th label". |
| 389 | Changes section shows what moved between 2 deliveries | README.md:L34-35 | VERIFIED | events per entity (routes.py:124-127); "Changes" panel (account.html:94-108). |
| 390 | Second delivery is simulated, and the page says so | README.md:L35 | VERIFIED | bundle.json delta.simulated set when the newer file is synthetic (sis/export/bundle.py:114-116); note "Simulated second delivery: these changes were planted..." (account.html:97); overview tile tag "Simulated" (overview.html:41). Also in the live code 390d5f7 (`git show 390d5f7:sis/api/templates/account.html` L97). |
| 391 | Ingest streams the zstd JSONL into Parquet | README.md:L41 | VERIFIED | sis/ingest/reader.py:1 (streams, 64 MiB blocks); zstd Parquet write (sis/ingest/run.py:79). |
| 392 | Ingest idempotent on re-delivery | README.md:L41 | VERIFIED | status "duplicate" (sis/ingest/run.py:41; sis/cli.py:38); tests/test_ingest.py:232 test_duplicate_skipped. |
| 393 | Ingest quarantines malformed files | README.md:L41 | VERIFIED | status "quarantined", quarantine_dir (sis/ingest/run.py:314-319). |
| 394 | Resolve turns banners into businesses by customer domain | README.md:L42 | VERIFIED | key_kind 'domain' primary (sis/entities/sql/06_banner_entity.sql:11); 472,508 of 487,133 are domain (docs/RESOLVE_REPORT_8e25...:13-16). |
| 395 | Resolve drops operators, honeypots and hosting zones | README.md:L42 | VERIFIED | honeypot_or_scanner blocked (sis/entities/sql/07_entities.sql:2,37; config/blocked_tags.yaml:4; 481 blocked, RESOLVE_REPORT:19); hosting zones as operators (sis/entities/sql/03_operators.sql:5; sis/entities/resolve.py:33-40). |
| 396 | 24 deterministic signals | README.md:L43 | VERIFIED | 24 SignalSpec entries in sis/signals/catalogue.py:51-122 (A 6, B 4, C 8, D 5, X 1). |
| 397 | 4 facts | README.md:L43 | VERIFIED | facts A-D (config/scoring.yaml:5; labels.py:84-89; account.html:115). X_small_cloud is outside the 4 facts. |
| 398 | Peer-relative scoring | README.md:L43 | VERIFIED | sis/scoring/peer.py; config/scoring.yaml:56 `peer:`; pct(C_components_vs_peers) at scoring.yaml:26. |
| 399 | 4 sales segments | README.md:L43 | VERIFIED | untouched, partially_covered, displace, low_surface (SCORE_REPORT_8e25...:13-16; labels.py:91-98). |
| 400 | Evidence per signal | README.md:L43 | VERIFIED | sis/signals/evidence.py; evidence keyed by signal_id (routes.py:112-116). |
| 401 | Evaluate: held-out provider labels, precision at k, lift, rank-biserial | README.md:L44 | VERIFIED | sis/evaluate/metrics.py:1-5, 33-90. |
| 402 | Evaluate: baselines, ablations | README.md:L44 | VERIFIED | sis/evaluate/baselines.py, sis/evaluate/ablation.py. |
| 403 | Evaluate: CI threshold | README.md:L44 | VERIFIED | .github/workflows/ci.yml eval job `uv run pytest -q -m eval`; tests/eval_thresholds.json; tests/test_eval.py::test_fixture_threshold. |
| 404 | Delta: diff between deliveries, events per account | README.md:L45 | VERIFIED | sis/delta/diff.py; `sis delta` (cli.py:136-154); events by entity_id (routes.py:124-127). |
| 405 | Serve: FastAPI + DuckDB, server-rendered pages | README.md:L46 | VERIFIED | FastAPI routers + Jinja2Templates (routes.py:12-14, 37-39); DuckDB per DEPLOY.md:16-17 and pyproject.toml:6. (157 MB part: see row 46.) |
| 406 | No LLM runs in the product | README.md:L48 | VERIFIED | `classify`, `reportcard`, `mcp` are stubs (cli.py:157-160, 207-216); no module imports openai (grep); sis/llm holds only tiers_config.py. |
| 407 | 2 LLM features described in DESIGN.md section 7 with their status | README.md:L48-49 | VERIFIED | DESIGN.md:325, 335-343 ("2 uses were designed ... left unbuilt"), 7.2 "(designed, cards/P7.md)". |
| 408 | Requires Python 3.12 | README.md:L53 | VERIFIED | pyproject.toml:4 `requires-python = ">=3.12"`; Dockerfile:4 python:3.12-slim. (Local pycache is cpython-314, so 3.12 is a minimum.) |
| 409 | Requires uv | README.md:L53 | VERIFIED | uv.lock; ci.yml setup-uv. |
| 410 | Data lives outside the repo in $SIS_DATA, see sis/config.py, set in .env | README.md:L54-55 | VERIFIED | sis/config.py:9 env_file=".env", :12 SIS_DATA default C:/Users/NIRANJAN VSKS/sis_data; .env gitignored (.gitignore:153). |
| 411 | `uv run sis ingest <delivery.zst>` | README.md:L59 | VERIFIED | cli.py:17-23, positional path. |
| 412 | Ingest takes about 12 minutes for the 16 GB file on a laptop | README.md:L59 | VERIFIED | wall seconds 712.6 = 11.9 min, 11 workers, 16 logical CPUs (INGEST_REPORT_8e25...:14, 20-21). |
| 413 | `uv run sis resolve <file_id> && uv run sis resolve --merge` | README.md:L60 | VERIFIED | cli.py:42-56, `--merge` option. |
| 414 | `uv run sis score <file_id> && uv run sis score --merge` | README.md:L61 | VERIFIED | cli.py:68-82, `--merge` option. |
| 415 | `uv run sis evaluate <file_id>` | README.md:L62 | VERIFIED | cli.py:94-104. |
| 416 | `uv run sis export` | README.md:L63 | VERIFIED | cli.py:163-179, version optional. |
| 417 | `uv run sis serve` on http://localhost:8000 | README.md:L64 | VERIFIED | cli.py:182-204, host 127.0.0.1, port 8000. |
| 418 | `uv run ruff check .` and `uv run mypy sis` | README.md:L70-71 | VERIFIED | ruff, mypy in dev deps (pyproject.toml:26-33); same commands in ci.yml. |
| 419 | `uv run pytest -q -m eval` checks a ranking-quality threshold on a committed fixture | README.md:L72 | VERIFIED | 4 eval tests incl. test_fixture_threshold; tests/fixtures/eval_bundle/eval_bundle.parquet tracked; tests/eval_thresholds.json. |
| 420 | Cost: 1 Fly.io machine | README.md:L75-76 | VERIFIED | fly.toml [[vm]] shared-cpu-1x 1gb, min_machines_running = 1. |
| 421 | About 7.73 USD a month | README.md:L76 | VERIFIED | docs/DEPLOY.md:9 "7.73 USD a month" (fra). |
| 422 | Built and live: ingest, entity resolution, scoring, evaluation, multi-file delta, hosted app | README.md:L80-81 | VERIFIED | All CLI stages implemented (cli.py); live per DEPLOY.md:3. Note: the live delta is the superseded synthetic pair (84,313 events), not the one in the current DELTA_REPORT (148,368); redeploy pending (tasks/state.md:8). |
| 423 | Designed, not built: LLM industry classification and report-card explanations (P7, P8), MCP server (P9) | README.md:L82-83 | VERIFIED | stubs `_stub("classify")`, `_stub("reportcard")`, `_stub("mcp")` (cli.py:157-216); cards/P7.md, P8.md, P9.md exist. |
| 424 | Known limits, with numbers, in DESIGN.md section 12 | README.md:L84 | VERIFIED | DESIGN.md:529 "## 12. Risks and open items", with numbers (e.g. 95 of top 100, 1,192 kev labels). |
| 425 | Explorer wrote every number to findings/ with the query that produced it | README.md:L89-91 | VERIFIED | findings/queries/*.py (01_flatten.py ... 07_signals.py); DESIGN.md 10. |
| 426 | Builders took 1 card each with acceptance tests and a handoff report; tasks/state.md is the build log; tasks/lessons.md the corrections | README.md:L91-93 | VERIFIED | cards/P0-P9.md; cards/README.md:41; handoff reports in tasks/state.md; tasks/lessons.md exists. |
| 427 | DESIGN.md section 10 has the detail | README.md:L93 | VERIFIED | DESIGN.md:463 "## 10. The dev loop". |

## Notes outside the 3 documents

These are not claims in the 3 documents, so nothing was edited for them.
They are recorded for the next session.

- **Stale section references.**
  - `config/llm_tiers.yaml:1` and `sis/llm/tiers_config.py:1` cite
    "DESIGN.md 7.0". There is no such section; the gateway is 7.1.
  - `cards/P7.md` cites section 7.1 for the classifier, which is now 7.2.
  - `cards/P8.md` cites 7.2 for report cards, which is now 7.3.
- **The live site shows an older simulated delivery.** It serves the
  pre-rework P6 bundle, with 84,313 events (`tasks/state.md`). DESIGN
  sections 8 and 12 and the DELTA_REPORT describe the reworked pair,
  148,368 events in a 162.5 MB bundle. A redeploy of the refreshed bundle
  is still open.
- **Behaviour the documents do not mention:**
  - Per-file `key_inventory.json`, `resolve_meta.json` and `score_meta.json`.
  - `$SIS_DATA/quarantine/<file_id>.txt`.
  - `feedback.jsonl` in the bundle directory.
  - The `delta` block in `bundle.json`.
  - `label_ransomware` in `labels.parquet`.
  - ingest_log `duplicate` rows, which carry null counts.
  - `received_at`, which is the file's modification time, not the time it
    arrived.
  - `unattributed_summary.pct`, which is a 0 to 1 fraction.
- **The P3.1 operator rules are only half documented.** The P3.1 hosting
  rules in `config/resolve.yaml` (template zones and templated hostnames)
  and the hand seed list make some domains under 50 IPs operators. DESIGN
  section 12 describes them. Section 4 and DATA_MODEL 2.1 rule 4 still
  mention only the 50-IP cutoff.
- **The generated eval report repeats a corrected phrase.**
  `sis/evaluate/report.py` prints "number in the low thousands". That is
  code, so it was left alone; the tested labels number 681.
- **Collecting the tests reads `$SIS_DATA`.** `tests/test_scoring.py` globs
  `$SIS_DATA` at import, to find a real scored file. So even
  `pytest --collect-only` lists that directory.
