"""The web app over 1 serve bundle (cards/P5.md, DATA_MODEL.md 6).

1 in-memory DuckDB connection with a view per bundle file, opened in the lifespan and kept on
app.state; requests are serialised through a lock, since concurrency is not a goal at this size.
"""

import json
import os
import threading
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import duckdb
import logfire
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from sis.config import settings

API_DIR = Path(__file__).resolve().parent
DEFAULT_BUNDLE_DIR = "/app/bundle"
TABLES = ("accounts", "evidence", "events", "signals")
MEMORY_LIMIT = "512MB"


class Bundle:
    """The read-only connection over a bundle directory, and bundle.json."""

    def __init__(self, bundle_dir: Path) -> None:
        self.dir = bundle_dir
        self.meta: dict[str, Any] = json.loads(
            (bundle_dir / "bundle.json").read_text(encoding="utf-8"))
        self.con = duckdb.connect()
        self.con.execute(f"SET memory_limit = '{MEMORY_LIMIT}'")
        self.con.execute("SET threads = 2")
        for t in TABLES:
            path = (bundle_dir / f"{t}.parquet").as_posix().replace("'", "''")
            extra = ""
            if t == "accounts":  # a bundle built before the delta existed lacks this column
                cols = {r[0] for r in self.con.execute(
                    f"DESCRIBE SELECT * FROM read_parquet('{path}')").fetchall()}
                if "max_event_severity" not in cols:
                    extra = ", NULL::INTEGER AS max_event_severity"
            self.con.execute(
                f"CREATE VIEW {t} AS SELECT *{extra} FROM read_parquet('{path}')")
        self.lock = threading.RLock()  # reentrant: a caller may hold it across queries
        self.feedback_lock = threading.Lock()

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        """Rows as dicts. `params` are bound, never formatted into `sql`."""
        with logfire.span("query", sql=sql), self.lock:
            cur = self.con.execute(sql, list(params))
            cols = [d[0] for d in cur.description or []]
            return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]

    def close(self) -> None:
        self.con.close()


def bundle_dir_from_env() -> Path:
    return Path(os.environ.get("SIS_BUNDLE_DIR", DEFAULT_BUNDLE_DIR))


def create_app(bundle_dir: Path | None = None) -> FastAPI:
    from sis.api import routes  # import here: routes imports this module

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.bundle = Bundle(bundle_dir or bundle_dir_from_env())
        yield
        app.state.bundle.close()

    logfire.configure(token=settings.LOGFIRE_TOKEN, send_to_logfire="if-token-present",
                      service_name="sis")
    app = FastAPI(title="Sales intelligence", lifespan=lifespan)
    logfire.instrument_fastapi(app)
    app.mount("/static", StaticFiles(directory=API_DIR / "static"), name="static")
    app.include_router(routes.api)
    app.include_router(routes.pages)
    return app


def get_bundle(request: Request) -> Bundle:
    bundle: Bundle = request.app.state.bundle
    return bundle
