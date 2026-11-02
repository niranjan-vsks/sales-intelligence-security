"""Run a .sql file of `;`-separated statements against a DuckDB connection.

`$name` values are bound as parameters (each statement gets only the ones it mentions).
`{name}` fragments are SQL text spliced in before execution, for predicates that come from
config (config/what_we_sell_map.csv) and cannot be bound."""

import re
from pathlib import Path
from typing import Any

import duckdb


def run_sql(con: duckdb.DuckDBPyConnection, path: Path, fragments: dict[str, str] | None = None,
            **params: Any) -> None:
    text = path.read_text(encoding="utf-8")
    code = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("--"))
    for stmt in code.split(";"):  # the file's statements hold no semicolons inside strings
        if not stmt.strip():
            continue
        for key, frag in (fragments or {}).items():
            stmt = stmt.replace("{" + key + "}", frag)
        used = {k: v for k, v in params.items() if re.search(rf"\${k}\b", stmt)}
        con.execute(stmt, used)
