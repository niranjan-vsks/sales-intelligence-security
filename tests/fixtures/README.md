# Fixtures

`tiny_banners.jsonl`: the first 200 lines of the raw delivery, unmodified (1,133,252 bytes, under
the 2 MB limit, so no line was dropped). Produced by streaming the zstd file in-process:

```
zstd -dc --long=31 <raw file> | head -n 200 > tests/fixtures/tiny_banners.jsonl
```

All 200 lines parse as JSON. `conftest.py::tiny_banners` flattens them into Parquet under `tmp_path`.
