# Evaluation

`uv run sis evaluate <file_id>` measures the ranking against labels the scoring never reads
(cards/P4.md, DESIGN.md section 6). It writes `labels.parquet`, `metrics.json`,
`baselines.json` and `ablations.json` to `$SIS_DATA/<file_id>/eval/` and the tables to
`docs/EVAL_REPORT_<file_id>.md`. Constants (k values, seeds, fixture size, threshold factor)
are in `config/eval.yaml`.

## The labels

All at entity grain: an active entity has the label when any banner attributed to it
(primary or fallback, edge banners included) has the property. The scoring never reads them:
`A_inferred_cves` and `A_max_cvss` are recomputed from vulns rows with `kev` and `verified`
false (DATA_MODEL.md 3.1).

| label | true when | what it says | what it cannot say |
|---|---|---|---|
| label_kev | a vulns row with `kev = true` | a version-inferred CVE is on the CISA known-exploited list | whether the host is exploitable. It comes from the same version strings fact A reads, so it is partly circular |
| label_verified | a vulns row with `verified = true` | the provider tested and confirmed a CVE | anything about the 99 percent of hosts nobody tested |
| label_heartbleed | `opts_heartbleed` contains `VULNERABLE` | an active test found Heartbleed | any other CVE; 50 entities on the first file |
| label_opts_vulns | `len(opts_vulns) > 0` | a provider-run vulnerability probe hit | coverage beyond the few CVEs the probes test. On the first file it is almost the same set as label_verified (777 of 791 entities in both) |
| label_any_tested | verified or heartbleed or opts_vulns | the honest exam: labels from a test, not a version string | much, statistically: about 800 entities, so the intervals are wide |
| label_has_vendor | a `D_waf` or `D_security_appliance` signal | already a customer of a security vendor | budget, satisfaction, which product. It is the `displace` rule, so it is a sanity check, never a target |
| label_ransomware | a kev row with `ransomware_campaign = 'Known'` (from `other_keys`) | the KEV catalogue links the CVE to ransomware | exploitation of this host. Informational only |

None of them says anyone bought anything. There is no purchase, contact or churn field in
the data.

## The CI gate

`uv run pytest -m eval` (the `eval` job in `.github/workflows/ci.yml`) recomputes
precision@1000 by `priority` on `tests/fixtures/eval_bundle/eval_bundle.parquet` (50,000
active entities sampled with seed 11 from the first file's scores and labels) and fails when
it falls below `tests/eval_thresholds.json` (the measured value x 0.95), for label_any_tested
and label_kev. The bundle holds scores, not signals: it catches a change to the scores that
is committed with the bundle regenerated, and a change to the metric code.

To move the bar on purpose (a new `scoring_version`): rescore, then run
`uv run sis evaluate <file_id> --fixture`, which rewrites the bundle and the thresholds, and
commit both with the report that explains the change. A plain `sis evaluate` never touches
them.

## Adding the 7th label: sales feedback

The only label that measures what we sell is whether sales got a reply. It is designed, not
populated (no UI exists before P5, and P4 does no human labelling).

1. Store it where the UI writes it: 1 row per (entity_id, outcome, recorded_at, user), with
   outcome in `replied`, `meeting`, `not_interested`, `wrong_contact`. It lives outside the
   per-file tables because it outlives files.
2. Add it to `sis/evaluate/sql/01_labels.sql` as `label_replied` (`replied` or `meeting`),
   left-joined by entity_id, and to `LABELS` in `sis/evaluate/metrics.py`.
3. Evaluate it only over the entities sales actually contacted, not all active entities:
   its base rate is the reply rate of the called list, and the question is whether higher
   `priority` among those called replies more (rank-biserial, precision at the called
   list's own k values). Add a `where` population for it rather than a new metric.
4. Once it has a few hundred outcomes, make it the CI threshold label in
   `config/eval.yaml` in place of label_any_tested.
