# Fixtures

`tiny_banners.jsonl`: the first 200 lines of the raw delivery, unmodified (1,133,252 bytes, under
the 2 MB limit, so no line was dropped). Produced by streaming the zstd file in-process:

```
zstd -dc --long=31 <raw file> | head -n 200 > tests/fixtures/tiny_banners.jsonl
```

All 200 lines parse as JSON. `conftest.py::tiny_banners` flattens them into Parquet under `tmp_path`.

`eval_bundle/eval_bundle.parquet`: 50,000 active entities sampled with seed 11 (Python
`random.Random(11).sample` over the sorted entity ids) from the first file's scores and P4
labels: entity_id, priority, exposure, segment, fact_a..fact_d and the 7 labels (1.85 MB).
Written with `tests/eval_thresholds.json` by `uv run sis evaluate <file_id> --fixture`;
`tests/test_eval.py::test_fixture_threshold` reads both. See evals/README.md.
