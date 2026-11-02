# Prompt for the exploration agent

Paste everything below this line into a fresh Claude Code session (Opus or
Sonnet) opened in this repo, after the dataset is downloaded. Replace
DATASET_PATH.

---

You are the DATA EXPLORER for a 5-day take-home. Your only job is to execute
EXPLORATION.md in this repo, in order, against the file at DATASET_PATH, and
to fill the `findings/` directory exactly as section 9 of that document
specifies. The dataset is at C:\Users\NIRANJAN VSKS\Downloads\b2_download_file_by_id (no
extension). Read ASSIGNMENT.md once for context. Read EXPLORATION.md fully
before running anything, section 0a first: step 0 is already done,
`findings/00_format.md` says what the file is, and section 0a replaces
section 1.

Rules:

1. Do not load the file into memory. Follow section 1: convert once to
   Parquet with DuckDB, then query the Parquet. Set memory_limit and
   temp_directory first. Start the full conversion (step 1.3) in the
   background and develop every query against the 1,000,000-row sample
   while it runs.
2. Save every SQL and Python file you run under `findings/queries/`. Every
   number in findings/ must be reproducible from those files.
3. Never print more than 50 rows of any result to the conversation. Write
   results to files and summarise.
4. Do not skip a section. If a section does not apply (for example, no
   temporal columns, no JSON columns), write the file anyway with 1 line
   saying so and why.
5. Do not invent, round, or estimate a number. Every number comes from a
   query. If a query is too slow on the full file, run it on the sample and
   mark the result SAMPLE in the file.
6. Do not name signals from your own knowledge of cybersecurity buyers.
   Every candidate in 08_candidates.md must come out of the section 7
   procedures with lift evidence attached. If you find yourself writing a
   candidate with no query behind it, delete it.
7. Do not write any application code, scoring, or ranking. No LLM calls.
8. Fill the 08_candidates.md template completely for every candidate. A
   block with an empty field is worse than no block.
9. When section 7.4 asks for what-we-sell, build it from values actually
   present in the file and say which column each value came from.
10. Commit findings/ when done. Do not commit the dataset or the Parquet.
    Add `data/` to .gitignore if it is not there.

Deliver, in this order of priority, so partial work is still useful:

- findings/00_format.md, 01_schema.md, 02_columns.csv, 02_population.md
- findings/06_relationships.md including the temporal section
- findings/03_cardinality.md, 04_distributions.md, 05_semistructured.md
  and the values/ directory
- findings/07_* files
- findings/08_candidates.md with the 6 facts at the top

When finished, write findings/REPORT.md: at most 150 lines, no tables wider
than 6 columns, containing the 6 facts, the list of candidates by id with
1 line each, the 10 most surprising things you saw, and every place where
you deviated from EXPLORATION.md and why. That file is what the architect
reads first.
