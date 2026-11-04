# Write-up: sales intelligence from a Shodan export

Live app: https://sis-niranjan.fly.dev/
Repository: https://github.com/niranjan-vsks/sales-intelligence-security
Full design: DESIGN.md. Demo guide: docs/DEMO_GUIDE.md.

## What the file was

14,608,406 service banners from 1 Shodan scan, 17.6 GB compressed, 123 GB
uncompressed, collected in 1 day. Not a company table. 62 percent of the
rows belong to 5 network operators; Incapsula alone is 32 percent. Only
7 percent of rows resolve to a business's own domain. I profiled the
whole file before writing any application code (findings/REPORT.md), and that profile set the design.

## What I built

1. **Ingest.** Streams the compressed file into Parquet in 12 minutes on
   a laptop, idempotent on re-delivery by file hash, quarantines
   malformed files, reconciles row counts before publishing output.
2. **Entity resolution.** Banners roll up to a business by the registered
   domain of their reverse DNS, with certificate names and Host headers
   as fallbacks. Domains covering more than 50 addresses, cloud and CDN
   zones, hosting providers' numbered server zones, honeypots and
   scanners are set aside. 487,133 businesses remain.
3. **Signals and score.** 24 deterministic signals measured on the file,
   collapsed into 4 facts because the correlation analysis showed they
   encode 4 things: visibly old software, neglected certificates, exposed
   surface, protection present. Each business is scored against peers in
   the same country with a similar number of services. 4 sales segments
   follow from the protection fact: untouched (300,849), partially
   covered (103,141), has a vendor (77,530), low visible surface (5,613).
4. **Evidence.** Every signal stores the banners that fired it. The
   account page shows them verbatim.
5. **Evaluation.** No buying outcome exists in the file. I hold out the
   provider's tested vulnerability labels and measure precision at k,
   lift and rank-biserial against random, a breadth-only ranking and a
   CVE-count ranking, with ablations per fact. At the top 1,000 the
   ranking is 28 times richer in tested vulnerabilities than chance. It
   does not clearly beat the breadth baseline on precision at 1,000; it
   does on rank-biserial (0.60 against 0.12). The evaluation found 3
   defects in the first version, hosting zones at the top, a too-narrow
   surface definition, and labels counting CDN banners, and all 3 were
   fixed in the open. 57 of the top 100 are still hosting providers; the
   rule that would finish the job is listed as not built.
6. **Monthly deliveries.** Each file is processed in isolation; a diff
   between consecutive files produces events per business (new service,
   certificate expired, protection removed). Proven on a second file
   manufactured from the first with planted changes; recall per change
   type is reported and 2 of 5 types fall short of their bar.
7. **Hosted app.** FastAPI and DuckDB over a 160 MB bundle on 1 Fly.io
   machine at 7.73 USD a month. Overview, filtered list, account page with
   plain-language reasons and evidence, feedback buttons that collect the
   first real labels.

## What I chose not to build, and why

- No LLM in the product. Every signal is a rule on structured fields,
  which is reproducible, explainable and free. 2 LLM features were
  designed with validation protocols and cost accounting, a business
  classifier and report-card explanations, and are left unbuilt; the
  cards and gateway configuration are in the repo.
- No outreach emails and no UI beyond what finding and reading an
  account needs. The assignment said those are not the interesting part.
- No scanning of prospects and no web research. Legal exposure and
  hallucination risk.

## How I built it

3 kinds of AI session with a human running the gates between them. An
architect session wrote the exploration plan before seeing the data and
the design after reading only the findings. An explorer session profiled
the full file and wrote every number with the query that produced it.
Builder sessions each took 1 spec card with acceptance tests and returned
a fixed-format handoff. A non-author session reviewed entity resolution
before scoring was built. A spec-to-code audit at the end checked 427
claims in the documents against the code and corrected 65. The build log
was kept per phase.

## Limits, stated

The tested labels number 681 businesses, so intervals are wide. The
known-exploited label is downstream of the same version strings the
model reads. The scan is 1 day, so change over time is simulated. The
CI quality gate re-sorts stored scores rather than re-scoring, so it
would not catch a weight change; that is recorded as an open item.
