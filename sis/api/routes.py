"""JSON endpoints under /api and the HTML pages (cards/P5.md steps 3 to 6, cards/P5_1.md)."""

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, get_args
from urllib.parse import urlencode

import logfire
import markdown
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from sis import paths
from sis.api import labels
from sis.api.app import API_DIR, Bundle, get_bundle
from sis.api.schemas import (
    AccountDetail,
    AccountPage,
    AccountSummary,
    Event,
    EvidenceItem,
    FeedbackIn,
    PageMeta,
    Profile,
    Segment,
    SignalItem,
    Sort,
)
from sis.config import settings
from sis.scoring.explain import contributions
from sis.signals.catalogue import BY_ID

api = APIRouter(prefix="/api")
pages = APIRouter()
templates = Jinja2Templates(directory=API_DIR / "templates")
BundleDep = Annotated[Bundle, Depends(get_bundle)]

PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
ABOUT_DOC = paths.REPO_ROOT / "docs" / "ABOUT.md"  # what the About page renders
HIST_BUCKETS = 10  # exposure histogram: [0, 10), [10, 20), ..., [90, 100]
WHY_MAX = 5  # signals shown in the account page's Why panel
REASONS_MAX = 8  # signals in the overview's "most common reasons"
START_HERE = 10  # untouched accounts on the overview
# a gate with weight 0 never explains a rank; always-present signals (breadth) fire for every
# account with a service, so "accounts showing them" would say nothing
NOT_REASONS = ("C_any_service",)

SORT_SQL = {
    "priority": "priority DESC, rank_overall",
    "exposure": "exposure DESC, rank_overall",
    "n_banners": "n_banners DESC, rank_overall",
    # accounts with a change in the latest delta first, worst change first, then priority
    "recent_change": "max_event_severity DESC NULLS LAST, priority DESC, rank_overall",
}
SORT_LABELS = {"priority": "Priority", "exposure": "Exposure", "n_banners": "Most services",
               "recent_change": "Recent change"}
SUMMARY_COLS = ("entity_id, display_name, key_kind, segment, exposure, priority, rank_overall, "
                "country_code, n_banners, n_ips, org_mode, top_signals, industry, "
                "max_event_severity")


# ---- queries shared by the JSON and HTML routes -----------------------------------------


def _filters(q: str | None, segments: Sequence[str], country: str | None,
             industry: str | None, min_exposure: float | None) -> tuple[str, list[Any]]:
    """WHERE clause and its parameters; filters compose with AND, segments with OR."""
    clauses: list[str] = []
    params: list[Any] = []
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        clauses.append("display_name ILIKE ? ESCAPE '\\'")
        params.append(f"%{escaped}%")
    if segments:
        clauses.append("segment IN (" + ", ".join("?" for _ in segments) + ")")
        params.extend(segments)
    for col, val in (("country_code", country), ("industry", industry)):
        if val:
            clauses.append(f"{col} = ?")
            params.append(val)
    if min_exposure is not None:
        clauses.append("exposure >= ?")
        params.append(min_exposure)
    return ("WHERE " + " AND ".join(clauses)) if clauses else "", params


def list_accounts(b: Bundle, q: str | None, segments: Sequence[str], country: str | None,
                  industry: str | None, min_exposure: float | None, sort: str, page: int,
                  page_size: int) -> AccountPage:
    where, params = _filters(q, segments, country, industry, min_exposure)
    total = b.query(f"SELECT count(*) AS n FROM accounts {where}", params)[0]["n"]
    rows = b.query(f"SELECT {SUMMARY_COLS} FROM accounts {where} ORDER BY {SORT_SQL[sort]} "
                   "LIMIT ? OFFSET ?", [*params, page_size, (page - 1) * page_size])
    return AccountPage(items=[AccountSummary(**r) for r in rows],
                       meta=PageMeta(page=page, page_size=page_size, total=total,
                                     sort=sort))


def account_detail(b: Bundle, entity_id: str) -> AccountDetail:
    rows = b.query("SELECT * FROM accounts WHERE entity_id = ?", [entity_id])
    if not rows:
        raise HTTPException(404, f"no account {entity_id}")
    acc = rows[0]
    with logfire.span("contributions", entity_id=entity_id), b.lock:
        contrib = dict(contributions(entity_id, acc["file_id"],
                                     signals_path=b.dir / "signals.parquet", con=b.con))
    evidence: dict[str, list[EvidenceItem]] = {}
    for e in b.query("SELECT signal_id, banner_id, ip, port, module, field, value, snippet, "
                     "observed_at FROM evidence WHERE entity_id = ? "
                     "ORDER BY signal_id, banner_id", [entity_id]):
        evidence.setdefault(e["signal_id"], []).append(EvidenceItem(**e))
    signals = [SignalItem(**s, contribution=contrib.get(s["signal_id"]),
                          label=labels.signal_sentence(
                              s["signal_id"], s["value"],
                              [e.value or "" for e in evidence.get(s["signal_id"], [])]))
               for s in b.query("SELECT signal_id, fact, value, n_banners, pct_in_peer "
                                "FROM signals WHERE entity_id = ? ORDER BY signal_id",
                                [entity_id])]
    events = [Event(**e) for e in b.query(
        "SELECT event_id, event_type, subject, from_file, to_file, from_value, to_value, "
        "detected_at, severity FROM events WHERE entity_id = ? ORDER BY detected_at, event_id",
        [entity_id])]
    profile = None
    if acc.get("industry") is not None or acc.get("description") is not None:
        profile = Profile(is_business=acc.get("is_business"), industry=acc.get("industry"),
                          description=acc.get("description"),
                          confidence=acc.get("industry_confidence"))
    return AccountDetail(**acc, signals=signals, evidence=evidence, events=events,
                         profile=profile)


def _cached(b: Bundle, key: str, sql: str) -> list[dict[str, Any]]:
    """A bundle-wide aggregate, computed on first use and kept for the process lifetime (the
    bundle is read-only)."""
    if key not in b.cache:
        b.cache[key] = b.query(sql)
    rows: list[dict[str, Any]] = b.cache[key]
    return rows


def stats(b: Bundle) -> dict[str, Any]:
    hist = [0] * HIST_BUCKETS
    for r in _cached(b, "exposure_hist",
                     f"SELECT least(floor(exposure / {100 // HIST_BUCKETS}), "
                     f"{HIST_BUCKETS - 1})::INTEGER AS b, count(*) AS n "
                     "FROM accounts GROUP BY 1"):
        hist[r["b"]] = r["n"]
    return {
        "segments": {r["segment"]: r["n"] for r in b.query(
            "SELECT segment, count(*) AS n FROM accounts GROUP BY 1 ORDER BY 2 DESC")},
        "countries_top20": {r["country_code"]: r["n"] for r in b.query(
            "SELECT country_code, count(*) AS n FROM accounts GROUP BY 1 "
            "ORDER BY 2 DESC, 1 LIMIT 20")},
        "exposure_hist": hist,
        # accounts with the signal present (value > 0), most common first
        "signal_fire_counts": {r["signal_id"]: r["n"] for r in _cached(
            b, "signal_fire_counts",
            "SELECT signal_id, count(DISTINCT entity_id) AS n FROM signals WHERE value > 0 "
            "GROUP BY 1 ORDER BY 2 DESC, 1")},
        "bundle": b.meta,
    }


def append_feedback(b: Bundle, fb: FeedbackIn) -> int:
    """Append 1 line to <bundle>/feedback.jsonl (the 7th label, DESIGN.md 10). Returns the
    file's line count after the write."""
    if not b.query("SELECT 1 AS x FROM accounts WHERE entity_id = ?", [fb.entity_id]):
        raise HTTPException(404, f"no account {fb.entity_id}")
    path = b.dir / "feedback.jsonl"
    line = json.dumps({**fb.model_dump(), "at": datetime.now(UTC).isoformat(),
                       "bundle_version": b.meta["bundle_version"]})
    with b.feedback_lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        with open(path, encoding="utf-8") as f:
            return sum(1 for _ in f)


# ---- JSON API ---------------------------------------------------------------------------


@api.get("/accounts", response_model=AccountPage)
def get_accounts(
    b: BundleDep,
    q: str | None = None,
    segment: Segment | None = None,
    country: str | None = None,
    industry: str | None = None,
    min_exposure: Annotated[float | None, Query(ge=0, le=100)] = None,
    sort: Sort = "priority",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = PAGE_SIZE,
) -> AccountPage:
    return list_accounts(b, q, [segment] if segment else [], country, industry, min_exposure,
                         sort, page, page_size)


@api.get("/accounts/{entity_id}", response_model=AccountDetail)
def get_account(entity_id: str, b: BundleDep) -> AccountDetail:
    return account_detail(b, entity_id)


@api.get("/stats")
def get_stats(b: BundleDep) -> dict[str, Any]:
    return stats(b)


@api.get("/health")
def health(b: BundleDep) -> dict[str, Any]:
    n = b.query("SELECT count(*) AS n FROM accounts")[0]["n"]
    return {"status": "ok", "bundle_version": b.meta["bundle_version"], "n_accounts": n}


@api.post("/feedback")
def post_feedback(fb: FeedbackIn, b: BundleDep) -> dict[str, Any]:
    n = append_feedback(b, fb)
    return {"status": "ok", "n_feedback": n}


# ---- HTML pages -------------------------------------------------------------------------


def _ctx(request: Request, b: Bundle, **kw: Any) -> dict[str, Any]:
    return {"request": request, "meta": b.meta, "rollup_max_ips": settings.ROLLUP_MAX_IPS,
            "L": labels, **kw}


@pages.get("/", response_class=HTMLResponse)
def overview_page(request: Request, b: BundleDep) -> HTMLResponse:
    """The shape of the book: tiles, segment split, exposure histogram, countries, reasons,
    and the top untouched accounts. Every number is from /api/stats or the accounts list."""
    s = stats(b)
    reasons = [(sid, n) for sid, n in s["signal_fire_counts"].items()
               if sid[0] in "ABC" and sid not in NOT_REASONS and not BY_ID[sid].always
               ][:REASONS_MAX]
    start = list_accounts(b, None, ["untouched"], None, None, None, "priority", 1, START_HERE)
    countries = list(s["countries_top20"].items())[:10]
    return templates.TemplateResponse(request, "overview.html", _ctx(
        request, b, s=s, total=sum(s["segments"].values()), reasons=reasons,
        start=start.items, countries=countries, nav="overview"))


@pages.get("/accounts", response_class=HTMLResponse)
def accounts_page(
    request: Request,
    b: BundleDep,
    q: str = "",
    segment: Annotated[list[str] | None, Query()] = None,
    country: str = "",
    industry: str = "",
    min_exposure: str = "",
    sort: Sort = "priority",
    page: Annotated[int, Query(ge=1)] = 1,
) -> HTMLResponse:
    """The accounts table. An htmx request (filters, paging) gets the rows partial only. Form
    fields arrive as text and an empty field means no filter. `segment` repeats (chips); the
    form always sends 1 empty `segment`, so no chip ticked means any segment, while a bare
    /accounts opens on untouched."""
    segs = ["untouched"] if segment is None else [s for s in segment if s]
    for seg in segs:
        if seg not in get_args(Segment):
            raise HTTPException(422, f"unknown segment {seg!r}")
    try:
        min_exp = float(min_exposure) if min_exposure.strip() else None
    except ValueError as e:
        raise HTTPException(422, f"min_exposure must be a number, got {min_exposure!r}") from e
    if min_exp is not None and not 0 <= min_exp <= 100:
        raise HTTPException(422, "min_exposure must be between 0 and 100")
    res = list_accounts(b, q or None, segs, country.upper() or None, industry or None, min_exp,
                        sort, page, PAGE_SIZE)
    form = {"q": q, "segments": segs, "country": country.upper(), "industry": industry,
            "min_exposure": min_exposure, "sort": sort}
    qs = urlencode([("q", q), ("segment", ""), *(("segment", s) for s in segs),
                    ("country", country.upper()), ("industry", industry),
                    ("min_exposure", min_exposure), ("sort", sort)])
    s = stats(b)
    name = "_rows.html" if request.headers.get("HX-Request") else "accounts.html"
    return templates.TemplateResponse(request, name, _ctx(
        request, b, res=res, form=form, qs=qs, seg_counts=s["segments"],
        countries=list(s["countries_top20"]), sorts=SORT_LABELS, nav="accounts"))


@pages.get("/accounts/{entity_id}", response_class=HTMLResponse)
def account_page(request: Request, entity_id: str, b: BundleDep) -> HTMLResponse:
    acc = account_detail(b, entity_id)
    adds = sorted((s for s in acc.signals if (s.contribution or 0) > 0),
                  key=lambda s: (-(s.contribution or 0), s.signal_id))
    why, rest = adds[:WHY_MAX], [s for s in acc.signals
                                  if s not in adds[:WHY_MAX] and s.fact != "D" and s.value > 0]
    protection = [s for s in acc.signals if s.fact == "D" and s.value > 0]
    events = sorted(acc.events, key=lambda e: (-(e.severity or 0), e.event_type, e.event_id))
    return templates.TemplateResponse(request, "account.html", _ctx(
        request, b, acc=acc, why=why, rest=rest, protection=protection, events=events,
        nav="accounts"))


@pages.post("/ui/feedback", response_class=HTMLResponse)
def feedback_form(
    request: Request,
    b: BundleDep,
    entity_id: Annotated[str, Form()],
    verdict: Annotated[str, Form()],
) -> HTMLResponse:
    try:
        fb = FeedbackIn(entity_id=entity_id, verdict=verdict)
    except ValidationError as e:
        raise HTTPException(422, str(e)) from e
    append_feedback(b, fb)
    text = "Marked as prospect." if fb.verdict == "prospect" else "Marked as not a fit."
    return HTMLResponse(f'<p class="done" role="status">{text} Thank you.</p>')


def render_markdown(path: Path) -> str:
    """A markdown file as HTML."""
    return markdown.markdown(path.read_text(encoding="utf-8"), extensions=["tables", "fenced_code"])


@pages.get("/about", response_class=HTMLResponse)
def about_page(request: Request, b: BundleDep) -> HTMLResponse:
    body = render_markdown(ABOUT_DOC)
    return templates.TemplateResponse(request, "about.html", _ctx(
        request, b, body=body, nav="about"))
