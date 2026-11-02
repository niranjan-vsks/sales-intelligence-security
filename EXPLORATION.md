# EXPLORATION.md

A plan to execute, in order. Every step says what to run and what to record.
Nothing in this document describes what the data contains. Where it has to
assume something, the line is marked ASSUMPTION.

Inputs known at time of writing (all from the brief, not from the file):

- 1 file, 9 to 12 GB compressed. ASSUMPTION: format unknown until step 0.
- It will not fit in memory. Everything below streams or runs columnar.
- The buyer is a "cybersecurity software company" (ASSIGNMENT.md). No
  specific product is named. Section 7.4 therefore maps values to the
  cybersecurity category as a whole, not to 1 product.
- The file is a direct download from Backblaze B2. Its filename and the
  URL's embedded date (d20261026) are the only file-level metadata known so
  far. Record whatever the server sends (Content-Length, Content-Type,
  filename) in `findings/00_format.md` before anything else.
- ASSIGNMENT.md is the authority. Any conflict is resolved in its favour.

Output of Stage 1 is the `findings/` directory described in section 9. Stage 2
is written from that directory and nothing else.

---

## 0a. Addendum after step 0 was run (2026-11-01)

Step 0 is done. Read `findings/00_format.md` first. Summary: zstd JSONL,
16.4 GB compressed, 1 record per service banner from a Shodan scan, ragged
nested schema, about 100 top-level keys of which most are protocol blocks
present in under 1 percent of records.

This addendum replaces section 1. Sections 2 to 9 apply unchanged, with
"column" read as "JSON path".

### 1a. Decompress once to plain JSONL on disk, if there is room

```
zstd -dc --long=31 b2_download_file_by_id > data/raw.jsonl
```

ASSUMPTION: decompressed size is several times 16.4 GB. 302 GB is free on
C:. Watch it with `ls -l` as it grows; abort if it passes 150 GB and work
from the zstd stream instead (`zstd -dc FILE | python flatten.py`).

Line count: `wc -l data/raw.jsonl`. Record it.

### 1b. Flatten to Parquet with a fixed extraction, not schema inference

Schema inference over 100 ragged keys with 2.7 MB records is the step most
likely to fail or eat all memory. Instead write a streaming Python
flattener (`findings/queries/01_flatten.py`) that reads 1 line at a time
and emits 1 row with:

- every always-present scalar as a typed column (port, timestamp, org, isp,
  asn, transport, hash, os, ip_str, ipv6, link, product, version, uptime,
  devicetype, _shodan.module, _shodan.region, _shodan.id, location.*)
- every always-present list as LIST<VARCHAR> (hostnames, domains, tags,
  cpe23, and the keys of vulns)
- the http block's scalars (status, title, server, waf, host, location,
  html_hash, headers_hash, components_hash, dom_hash, securitytxt present
  yes/no, robots present yes/no, redirect count)
- http.components as LIST<VARCHAR> of component names and a 2nd list of
  their categories
- http.headers as a JSON string
- the ssl block's scalars (cipher.version, cipher.name, cert.issued,
  cert.expires, cert.expired, cert.subject.CN, cert.issuer.O,
  cert.pubkey.type, cert.pubkey.bits, cert.sig_alg, jarm, ja3s,
  trust.revoked, trust.browser, chain length, versions list, alpn list)
- the cloud block's scalars (provider, region, service)
- `data` truncated to 2,000 characters, and its full length as an integer
- `http.html` length as an integer, NOT the html body
- `has_<block>` boolean for every top-level protocol block
- `extra_json`: the remaining top-level blocks as 1 JSON string, so nothing
  is lost and section 5 can dig into any block later

Write with pyarrow in batches of 100,000 rows to
`data/banners/module=<module>/part-N.parquet`, partitioned by
`_shodan.module`. `data/banners/**/*.parquet` is then the "full.parquet"
the rest of this document refers to. Build `data/sample.parquet` from the
first 1,000,000 lines first and develop everything against it.

Record: wall time, Parquet size, row count. Verify row count equals the
line count from 1a.

### 1c. The 2nd table: vulns

`vulns` is a map keyed by CVE id with a nested object. Flatten it to its
own table while streaming: 1 row per (banner id, cve id, and every key of
the nested object; inventory those keys from the first 10,000 records that
have vulns and record them). Write to `data/vulns/*.parquet`. Section 6
treats this as a child table joined on `_shodan.id`.

### 1d. Grain and roll-up: do this before section 2

Section 6.1 asks what 1 row is. The answer is known: 1 banner. The open
question is how banners roll up to an organisation, and every later
section depends on it. So run 6.1 immediately after 1b:

- for each candidate key in {ip_str, asn, org, domains (unnested),
  hostnames (unnested), ssl.cert.subject.CN}: distinct count, share of
  banners where it is populated, banners per key value (quantiles)
- the functional dependency checks of 6.2 between these keys only
- 20 example groups by eye for the 2 most promising keys

Record the chosen roll-up key, its coverage, and what is lost (banners
that cannot be attributed) in `findings/06_relationships.md` under a
heading `roll-up`. Do not proceed to section 7 until this is written.
Every section 7 computation runs at both grains: banner and rolled-up
entity.

---

## 0. Setup and format identification

Tooling: DuckDB, driven from Python. Reason: it reads gzip, zstd, CSV, JSON
and Parquet directly, runs out-of-core with a memory cap, and `SUMMARIZE`
answers most of section 2 in 1 statement. Install:

```
pip install duckdb pyarrow
```

Set the laptop up before touching the file:

```
free disk  >= 3x the compressed size (Parquet output + spill)   ASSUMPTION on ratio, verify in 1.3
RAM cap    set DuckDB memory_limit to about half of physical RAM
temp dir   on the fastest disk with the most space
```

Identify the format without decompressing the whole thing:

```
# bash. Replace FILE.
file FILE
xxd -l 16 FILE
# gzip:    1f 8b
# zstd:    28 b5 2f fd
# bzip2:   42 5a 68
# parquet: 50 41 52 31 (PAR1) at start and end
# zip:     50 4b 03 04
# xz:      fd 37 7a 58 5a 00
```

Then look at the first bytes of the decompressed stream:

```
zcat FILE | head -c 4000          # gzip
zstdcat FILE | head -c 4000       # zstd
```

Record in `findings/00_format.md`:

- container (gzip, zstd, zip, none)
- inner format (CSV, TSV, JSONL, JSON array, Parquet, something else)
- delimiter, quoting, header present or not (CSV)
- 1 record per line or not (JSON)
- nesting depth visible in the first records (JSON)
- whether the file is 1 entity type or several (look for a type field or
  for records with different shapes)
- any file-level metadata: delivery date, version, source name, in the
  filename or in a header record. This matters for Stage 2 ingestion design.

Gzip and bzip2 are not splittable. The first full pass over the file will be
single-threaded and is the longest step in this plan. Start it (step 1.3)
and do steps 1.1 and 1.2 on a sample while it runs.

---

## 1. Convert once to Parquet

Every later query runs against Parquet, never against the compressed source.
Querying the source directly re-decompresses 10 GB per query.

### 1.1 Sample first

Build a sample Parquet of the first 1,000,000 records. It exists so that
every query in this plan can be developed in seconds and then run once
against the full file.

```sql
-- duckdb, Python or CLI
SET memory_limit = '8GB';           -- half of RAM, adjust
SET temp_directory = '/path/to/fast/disk/duckdb_tmp';
SET preserve_insertion_order = false;

-- CSV variant. all_varchar avoids type-inference failures mid-file.
COPY (
  SELECT * FROM read_csv('FILE', all_varchar = true, header = true,
                          sample_size = 200000)
  LIMIT 1000000
) TO 'data/sample.parquet' (FORMAT PARQUET, COMPRESSION ZSTD);

-- JSONL variant. Keep nested structure; union_by_name tolerates ragged records.
COPY (
  SELECT * FROM read_json('FILE', format = 'newline_delimited',
                          union_by_name = true, sample_size = 200000,
                          maximum_object_size = 33554432)
  LIMIT 1000000
) TO 'data/sample.parquet' (FORMAT PARQUET, COMPRESSION ZSTD);
```

If JSON inference fails on a field, add `columns = {...}` with that field as
`JSON` type and keep going. Record each such field: it is semi-structured and
section 5 handles it.

### 1.2 Decide the output schema from the sample

```sql
DESCRIBE SELECT * FROM 'data/sample.parquet';
```

Decide, per column, whether to keep it as VARCHAR, cast it, or keep it as
STRUCT/LIST/JSON. Do not cast anything that is not obviously numeric or a
date. A column that is 99 percent integers and 1 percent text is a finding,
not a casting problem. Record the decisions in `findings/01_schema.md`.

### 1.3 Full conversion

Same statement without the LIMIT. Write row-group-sized output so later
scans can skip:

```sql
COPY (SELECT * FROM read_csv('FILE', all_varchar = true, header = true, sample_size = -1))
TO 'data/full.parquet' (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 1000000);
```

If the file has an obvious partition column (visible in the sample: a date,
a region, an entity type), partition on it instead:

```sql
COPY (...) TO 'data/full' (FORMAT PARQUET, PARTITION_BY (col), COMPRESSION ZSTD);
```

Record: wall time, output size, compressed input size, and the ratio. These
3 numbers are the first input to the Stage 2 scaling section.

Sanity check before anything else:

```sql
SELECT count(*) FROM 'data/full.parquet';
```

Compare against a line count of the decompressed stream if the format is
line-based (`zcat FILE | wc -l`). A mismatch means dropped or merged records
and must be resolved before profiling.

---

## 2. Schema, types, row count, population

Run `SUMMARIZE` once against the full Parquet. It returns, per column: type,
min, max, approx unique, avg, std, quartiles, count, null percentage.

```sql
COPY (SUMMARIZE SELECT * FROM 'data/full.parquet')
TO 'findings/02_summarize.csv' (HEADER);
```

`SUMMARIZE` counts SQL NULL only. Placeholders are a separate pass. For every
VARCHAR column:

```sql
SELECT
  col,
  count(*)                                                   AS rows,
  count(col)                                                 AS non_null,
  count(*) FILTER (WHERE trim(col) = '')                     AS empty,
  count(*) FILTER (WHERE lower(trim(col)) IN
     ('null','none','n/a','na','nan','-','--','unknown','0','[]','{}')) AS placeholder,
  count(*) FILTER (WHERE col IS NOT NULL AND trim(col) <> ''
     AND lower(trim(col)) NOT IN
     ('null','none','n/a','na','nan','-','--','unknown','0','[]','{}')) AS populated
FROM 'data/full.parquet';
```

Generate this per column from Python by iterating over `DESCRIBE`. Do not
hand-write it for each column.

Record in `findings/02_columns.csv`, 1 row per column:

```
column, type_in_file, type_decided, rows, populated, populated_pct,
placeholder_pct, approx_unique, min, max, median, notes
```

Then bucket every column by `populated_pct` and write the buckets into
`findings/02_population.md`:

```
>= 90 pct   dense. Usable as a universal feature.
50 to 90    partial. Usable, but absence needs its own meaning.
10 to 50    sparse. Presence is itself information. Ask why these rows.
< 10        rare. Either noise or a very specific signal. Section 7.2 decides.
```

For every column under 50 percent populated, run 1 extra query: what do the
populated rows look like on the 5 densest low-cardinality columns, compared
to the whole file? If the populated slice is skewed, write down how. The
pattern of who has the field filled is often more informative than the
field's value.

---

## 3. Cardinality

From `02_columns.csv`, classify each column:

```
approx_unique ~= rows            identifier. Candidate key. Section 6.
approx_unique <= 50               low-cardinality categorical. Full value list.
50 < approx_unique <= 5000        mid-cardinality categorical. Top 100 + tail.
approx_unique > 5000, VARCHAR     high-cardinality. Free text, name, or URL. Section 5.
numeric                           distribution. Section 4.
```

The thresholds are starting points. Adjust after seeing the file and record
what you used.

For low and mid cardinality columns, dump the value table:

```sql
COPY (
  SELECT col, count(*) AS n, round(100.0 * count(*) / sum(count(*)) OVER (), 3) AS pct
  FROM 'data/full.parquet'
  GROUP BY col ORDER BY n DESC
) TO 'findings/values/col.csv' (HEADER);
```

1 file per column. Low cardinality: all values. Mid: all values too, the
file is small. Look at every value list by eye. Record in
`findings/03_cardinality.md`:

- columns that are the same fact under 2 spellings (case, whitespace,
  abbreviation). These get normalised in Stage 2 ingestion.
- enumerations that look controlled (a fixed vocabulary) versus free entry.
- values that are clearly codes (look up what they mean before going on).

---

## 4. Distributions and long tails

Numeric columns, after casting:

```sql
SELECT
  quantile_cont(col, [0.01,0.05,0.1,0.25,0.5,0.75,0.9,0.95,0.99,0.999]) AS q,
  min(col), max(col), avg(col), stddev(col),
  count(*) FILTER (WHERE col = 0) AS zeros,
  count(*) FILTER (WHERE col < 0) AS negatives
FROM 'data/full.parquet';
```

Plus a log-scale histogram, because most count-like business fields are
heavy-tailed:

```sql
SELECT floor(log10(col + 1)) AS bucket, count(*)
FROM 'data/full.parquet' WHERE col IS NOT NULL
GROUP BY 1 ORDER BY 1;
```

Categorical columns, the tail shape:

```sql
-- how many distinct values cover 50, 80, 95 percent of rows
WITH v AS (
  SELECT col, count(*) AS n FROM 'data/full.parquet' GROUP BY col
), c AS (
  SELECT col, n, sum(n) OVER (ORDER BY n DESC) / sum(n) OVER () AS cum
  FROM v
)
SELECT
  count(*) FILTER (WHERE cum <= 0.5) AS values_for_50pct,
  count(*) FILTER (WHERE cum <= 0.8) AS values_for_80pct,
  count(*) FILTER (WHERE cum <= 0.95) AS values_for_95pct,
  count(*) FILTER (WHERE n = 1) AS singletons,
  count(*) AS distinct_values
FROM c;
```

Record in `findings/04_distributions.md`, per column:

- the quantiles, and whether the field is heavy-tailed
- obvious sentinel values (a spike at 0, at 1, at a round number, at a max)
- for categoricals: head size, tail size, singleton count
- anything that looks like a unit mismatch (2 populations in 1 column)

---

## 5. Free text and semi-structured fields

Detection. For every high-cardinality VARCHAR column:

```sql
SELECT
  avg(length(col)) AS avg_len,
  quantile_cont(length(col), 0.95) AS p95_len,
  avg(CASE WHEN col LIKE '[%' OR col LIKE '{%' THEN 1 ELSE 0 END) AS json_like,
  avg(CASE WHEN col LIKE '%,%' THEN 1 ELSE 0 END)  AS has_comma,
  avg(CASE WHEN col LIKE '%|%' THEN 1 ELSE 0 END)  AS has_pipe,
  avg(CASE WHEN col LIKE '%;%' THEN 1 ELSE 0 END)  AS has_semicolon,
  avg(CASE WHEN col LIKE 'http%' THEN 1 ELSE 0 END) AS url_like,
  avg(length(col) - length(replace(col, ' ', ''))) AS avg_spaces
FROM 'data/full.parquet' WHERE col IS NOT NULL;
```

Classify each as: URL, identifier, delimited list, JSON, prose. Then:

**Delimited list columns.** Explode and treat the elements as a categorical:

```sql
COPY (
  SELECT trim(e) AS element, count(*) AS n,
         count(DISTINCT row_id) AS rows_containing
  FROM (SELECT row_id, unnest(string_split(col, ',')) AS e FROM 'data/full.parquet')
  GROUP BY 1 ORDER BY n DESC
) TO 'findings/values/col_elements.csv' (HEADER);
```

Also record list length per row (quantiles). List length is itself a
derived numeric and goes to section 7.3.

**JSON columns.** Key inventory first, values second:

```sql
SELECT k, count(*) AS n
FROM (SELECT unnest(json_keys(col)) AS k FROM 'data/full.parquet' WHERE json_valid(col))
GROUP BY k ORDER BY n DESC;
```

Every key that appears in more than 1 percent of rows becomes a virtual
column and gets the section 2 to 4 treatment. Nested keys: repeat 1 level
down. Record the key tree in `findings/05_semistructured.md`.

**Prose columns.** Do not read them row by row. Profile them:

```sql
-- token frequency, lowercase, minus a stopword list
SELECT tok, count(*) FROM (
  SELECT unnest(string_split(regexp_replace(lower(col), '[^a-z0-9 ]', ' ', 'g'), ' ')) AS tok
  FROM (SELECT col FROM 'data/full.parquet' USING SAMPLE 200000)
) WHERE length(tok) > 2 GROUP BY tok ORDER BY 2 DESC LIMIT 500;
```

Then bigrams the same way. Then read 50 random rows by hand and write down
what kind of text it is (description, notes, scraped page text, template
output) and whether rows look templated (many near-duplicates). Templated
text is a sign of a generated field and is cheap to parse with a regex.
Non-templated prose is the only place in this plan where an LLM might earn
its cost, and that decision is Stage 2's.

Record for each prose column: what it is, length distribution, top 50
tokens, top 50 bigrams, duplicate rate (`count(DISTINCT col) / count(col)`),
and 5 verbatim examples.

---

## 6. Joins and relationships inside the file

### 6.1 Grain and keys

First question: what is 1 row?

```sql
-- candidate keys: uniqueness ratio per identifier-like column
SELECT count(*) AS rows, count(DISTINCT col) AS distinct_col FROM 'data/full.parquet';
```

If no single column is unique, try pairs of the identifier-like columns. If
nothing is unique, the file has duplicates or is at a finer grain than you
think (1 row per company-per-something). Record the grain in words, and the
duplicate rate:

```sql
SELECT count(*) - count(DISTINCT (col_a, col_b)) AS dup_rows FROM 'data/full.parquet';
```

Look at 20 duplicate groups by hand. Exact duplicates, or same key with
different values? The second case means the file contains history or
conflicting sources, and that changes Stage 2 ingestion entirely.

### 6.2 Functional dependencies

For every pair of categorical columns (A, B) with cardinality under 5,000:

```sql
SELECT count(DISTINCT a) AS da, count(DISTINCT b) AS db,
       count(DISTINCT (a, b)) AS dab
FROM 'data/full.parquet';
-- dab = da      means A determines B (B is a rollup of A)
-- dab = db      means B determines A
-- dab ~= da*db  means independent
```

Generate the pairs from Python. Record every near-dependency (dab within 5
percent of da or db) in `findings/06_relationships.md`. These are
hierarchies (a code and its label, a city and its region, a subcategory
and its category). A hierarchy means 1 fact, not 2 features.

### 6.3 References between columns

Does any column's value set overlap with another column's value set?

```sql
SELECT count(*) FROM (SELECT DISTINCT col_x FROM 'data/full.parquet') x
JOIN (SELECT DISTINCT col_y FROM 'data/full.parquet') y ON x.col_x = y.col_y;
```

Run across every pair of identifier-like columns. A large overlap means a
self-reference (parent, owner, related entity) and the file contains a graph.
Record edge count, in-degree and out-degree distributions, and whether the
graph has cycles (it should not, if it is a hierarchy).

### 6.4 Multiple entity types

If step 0 found a type field, or records of visibly different shape: split
the file by type, rerun sections 2 to 4 per type, and record how the types
link. Multi-entity files are where the richest derived signals live, because
you can count children per parent.

### 6.5 Temporal fields

List every column that parses as a date or timestamp:

```sql
SELECT count(*) FILTER (WHERE try_cast(col AS TIMESTAMP) IS NOT NULL) AS parses,
       min(try_cast(col AS TIMESTAMP)), max(try_cast(col AS TIMESTAMP))
FROM 'data/full.parquet';
```

Also check integer columns that might be epoch seconds or years. For each
temporal column record: range, mode (a spike at 1 date means a batch
import, not an event), and what the date means (created, updated, observed,
founded, an event). Whether the file has 1 timestamp per row or several
determines whether change-over-time is computable at all. Record the
answer explicitly in `findings/06_relationships.md` under a heading
`temporal`, even if the answer is "none".

---

## 7. The signal hunt

This is a procedure. It produces candidates. It does not produce a ranking;
that is Stage 2.

### 7.1 Correlated column clusters

Goal: find groups of columns that encode 1 underlying fact, so Stage 2 does
not count the same fact 3 times.

Numeric columns, pairwise, on a sample:

```sql
SELECT corr(a, b) FROM (SELECT a, b FROM 'data/full.parquet' USING SAMPLE 2000000);
```

Generate all pairs from Python, write the matrix to
`findings/07_corr_numeric.csv`. Use Spearman if the fields are heavy-tailed
(rank them first with `rank()` in a CTE, then `corr`).

Categorical columns, pairwise: use the functional dependency table from
6.2, plus Cramér's V for pairs that are not dependencies:

```sql
-- chi-square inputs: contingency table
SELECT a, b, count(*) AS n FROM 'data/full.parquet' GROUP BY a, b;
```

Compute V in Python from the contingency table. Write to
`findings/07_corr_categorical.csv`.

Numeric against categorical: for each categorical value, the median of each
numeric. If the medians differ by more than the interquartile range of the
numeric overall, record the pair.

Then cluster: group columns where |corr| > 0.7, or V > 0.5, or a dependency
exists. Give each cluster a 1-line name for the fact it encodes, and pick 1
representative column. Record in `findings/07_clusters.md`:

```
cluster_id, columns, representative, fact_it_encodes, strength, notes
```

### 7.2 Rare but meaningful values

Common values describe the population. Rare values describe a subgroup.
The procedure finds rare values whose rows differ from the population.

For every categorical column (including exploded list elements and JSON
keys from section 5), take values with frequency between a floor and a
ceiling:

```
floor:    50 rows      (below this, nothing can be measured)   ADJUST after seeing row count
ceiling:  2 percent    (above this, it is a common value)
```

For each such value, compare the slice to the population on the
representative columns from 7.1:

```sql
WITH slice AS (SELECT * FROM 'data/full.parquet' WHERE col = 'VALUE'),
     pop   AS (SELECT * FROM 'data/full.parquet')
SELECT
  (SELECT median(num) FROM slice) / nullif((SELECT median(num) FROM pop), 0) AS lift_num,
  (SELECT avg(cat = 'X') FROM slice) / nullif((SELECT avg(cat = 'X') FROM pop), 0) AS lift_cat
;
```

In practice: compute the population profile once (1 row), compute every
slice profile in 1 grouped query, and divide in Python. Write
`findings/07_rare_values.csv`:

```
column, value, rows, pct, lift_on_rep1, lift_on_rep2, ..., max_abs_lift, notes
```

Sort by `max_abs_lift`. Read the top 100 by eye. A rare value with lift far
from 1 on several unrelated clusters is a candidate signal. A rare value
with lift near 1 everywhere is just rare.

Do the same for sparse columns (section 2): treat "populated" as the value
and compute the lift of the populated slice.

### 7.3 Derived signals

3 families. For each family, generate candidates mechanically, then
test each candidate with the same lift procedure as 7.2 (bucket the derived
value into deciles, compare top decile to bottom decile).

**Ratios.** For every pair of count-like numeric columns (a, b) that are
not in the same 7.1 cluster, compute `a / nullif(b, 0)`. Keep a ratio if its
distribution is not a function of either input alone (Spearman of the ratio
against a and against b both under 0.9). Record the survivors.

**Peer gaps.** Define a peer group as the combination of the 2 or 3 lowest
cardinality representative columns that most strongly split the numeric
distributions (use the numeric-vs-categorical result from 7.1). Then, per
row, per numeric or list-length feature:

```sql
SELECT *,
  num - median(num) OVER (PARTITION BY peer_col1, peer_col2)            AS gap_abs,
  percent_rank() OVER (PARTITION BY peer_col1, peer_col2 ORDER BY num)  AS pct_in_peer
FROM 'data/full.parquet';
```

A row at the 5th percentile of its peers on something peers usually have is
a gap. A row at the 95th percentile is an outlier. Record which features
produce wide peer spreads (where the gap is informative) and which are flat
within peers (where it is not). Peer groups smaller than 30 rows are not
peers; record the share of rows that fall into undersized groups.

**Change over time.** Only if 6.5 found more than 1 temporal column, or
multiple rows per entity with different timestamps. Compute, per entity:
age (now minus earliest date), recency (now minus latest date), and deltas
between date pairs. If there are multiple rows per entity over time, compute
the change in each numeric between the earliest and latest row. If 6.5 found
nothing, write "no temporal signal available in this file" and move on.
Do not manufacture a temporal signal.

Record every derived candidate in `findings/07_derived.csv`:

```
candidate_id, family, formula, inputs, coverage_pct, top_vs_bottom_decile_lift, notes
```

### 7.4 Negative signals

A negative signal is evidence a prospect does not need what we sell, or
cannot buy it. It needs 2 things: a definition of what we sell and a way to
see what each company already has. The assignment names only the category,
"cybersecurity software", so write `findings/07_what_we_sell.md` yourself
from the value lists: every value in the file that names a cybersecurity
product, vendor, control, certification or role, grouped by what it is.
Build that list from the data, not from memory. Mark it as the working
definition, since the assignment leaves the product open.

Procedure:

1. From sections 3 and 5, list every column or list element whose values
   describe something a company possesses, uses, has done, or is subject
   to. Do this from the actual value lists, not from the column names.
2. For each such column, build a 2-way mapping by hand from value to 1 of:
   `is_what_we_sell`, `is_a_substitute`, `is_a_prerequisite`,
   `is_a_blocker`, `unrelated`. Record the mapping as a CSV; it is Stage 2
   configuration. Expect most values to be `unrelated`.
3. Count: how many rows already have `is_what_we_sell`, how many have a
   `substitute`, how many have the `prerequisite` without the thing itself.
   That last group is who the whole platform is for. Record all 3
   counts and their overlap.
4. Check whether absence is informative. If the column is sparse (section
   2), absence may mean unobserved rather than not present. Record the
   populated percentage next to every negative signal; Stage 2 will treat
   absence in a 90 percent column differently from absence in a 10 percent
   column.
5. Look for disqualifiers that are not about product: values indicating the
   row is not a buyable entity at all (defunct, duplicate, a subsidiary of
   something already in the file, out of territory, wrong kind of
   organisation). These come from the value lists and the 6.3 graph.
   Record them with coverage.

Write `findings/07_negative.md` with 1 block per negative signal:

```
signal, source_column, values_that_trigger, rows_triggered, populated_pct_of_source,
absence_is_informative (yes/no/unknown), notes
```

### 7.5 Ground truth hunt

Stage 2 must say how it knows the ranking works. Before leaving the data,
look for anything in the file that could serve as an outcome:

- any column whose values indicate an existing relationship with a vendor
  in our category (from the 7.4 mapping, `is_what_we_sell` and `substitute`)
- any column that records an event with a date (from 6.5)
- any column that looks like a label, flag, tier, status, or score assigned
  by the data provider

Record each in `findings/07_ground_truth.md` with coverage and a 1-line
statement of what it does and does not measure. If nothing qualifies, write
that in 1 line. Stage 2 will spec a proxy either way, and needs to know
which case it is in.

---

## 8. Time budget

ASSUMPTION: the conversion in 1.3 is the long pole. Everything else runs
on Parquet in seconds to minutes.

```
Day 1 morning     steps 0, 1.1, 1.2; start 1.3 in the background
Day 1 afternoon   sections 2 to 4 on the sample, then rerun on full when 1.3 finishes
Day 2 morning     sections 5 and 6
Day 2 afternoon   section 7
Day 2 end         findings/ complete, report back
```

If 1.3 is still running at end of day 1, sections 2 to 7 run on the sample
and `findings/` says so on every file. Stage 2 can be written from a sample
profile if the full profile confirms it later; it cannot be written from
nothing.

---

## 9. What to record: the findings/ directory

This is the contract between Stage 1 and Stage 2. Stage 2 reads only this.

```
findings/
  00_format.md            container, inner format, file-level metadata, entity types
  01_schema.md            column list with type in file and type decided
  02_summarize.csv        raw SUMMARIZE output
  02_columns.csv          1 row per column: population, cardinality, range
  02_population.md        columns bucketed by fill rate, skew of sparse columns
  03_cardinality.md       classification, spelling variants, controlled vocabularies
  04_distributions.md     quantiles, tails, sentinels, per column
  05_semistructured.md    list columns, JSON key trees, prose profiles
  06_relationships.md     grain, keys, duplicates, dependencies, graph, temporal
  07_clusters.md          correlated column groups with representative + fact
  07_corr_numeric.csv
  07_corr_categorical.csv
  07_rare_values.csv
  07_derived.csv
  07_negative.md
  07_what_we_sell.md      cybersecurity-related values found in the file, grouped
  07_ground_truth.md
  08_candidates.md        THE SUMMARY. See template below.
  values/                 1 CSV per categorical column, 1 per exploded list column
  queries/                every SQL and Python file you ran, so the profile is reproducible
```

### 08_candidates.md template

1 block per candidate signal, positive or negative, raw or derived. Stage 2
turns these blocks into the scoring model, so every field matters.

```
### C-NN  short name

type            raw | derived | negative | disqualifier
columns         the columns it reads
computation     1 line, or a reference to a query in queries/
coverage        rows where it can be computed, as a percent
direction       what a high or present value is hypothesised to mean for a buyer
evidence        the lift numbers from section 7 that made you keep it
cluster         which 7.1 cluster it belongs to, so Stage 2 does not double count
absence_meaning informative | unobserved | unknown
cost            cheap (1 column) | medium (join or window) | expensive (text parse)
ground_truth    any column from 7.5 it could be validated against, or none
confidence      high | medium | low, with 1 line on why
```

Also record, at the top of `08_candidates.md`, the 6 facts Stage 2 cannot
proceed without:

```
1. grain: what 1 row is, and the key
2. row count, and distinct entity count if different
3. whether the file is a full snapshot, a delta, or history (from 6.1 and 6.5)
4. the list of representative columns from 7.1
5. which candidates have coverage above 50 percent (these carry the model)
6. whether any ground truth exists (7.5), and if so its coverage
```

---

## 10. What this plan deliberately does not do

- It does not read the file into pandas. Nothing here loads more than a
  sample into memory.
- It does not name any signal. Every candidate comes out of sections 7.1 to
  7.5 or it does not exist.
- It does not call an LLM. If section 5 finds non-templated prose, the
  decision about whether an LLM is worth its cost belongs to Stage 2, made
  with the duplicate rate and length distribution in hand.
- It does not rank anything. Lift is evidence that a candidate carries
  information, not a weight.
