"""JSON endpoints under /api and the 3 HTML pages (cards/P5.md steps 3 to 6)."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, get_args

import logfire
import markdown
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from sis import paths
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

api = APIRouter(prefix="/api")
pages = APIRouter()
templates = Jinja2Templates(directory=API_DIR / "templates")
BundleDep = Annotated[Bundle, Depends(get_bundle)]

PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
ABOUT_SECTIONS = ("1", "5", "6", "7")  # DESIGN.md sections the About page renders

SIGNAL_LABELS: dict[str, str] = {
    "A_fingerprinted": "Software and version visible to anyone",
    "A_inferred_cves": "Known CVEs for the versions seen",
    "A_max_cvss": "Worst CVSS score among those CVEs",
    "A_eol": "End-of-life product or operating system",
    "A_os_leak": "Operating system disclosed",
    "A_cpe_per_header": "Many components named per HTTP response",
    "B_self_signed": "Self-signed certificate",
    "B_expired": "Expired certificate",
    "B_legacy_tls": "Legacy TLS or SSLv3 offered",
    "B_cert_age_days": "Old certificate",
    "C_admin_services": "Remote admin or database service open to the internet",
    "C_windows_internals": "Windows internals exposed (NTLM or Windows OS)",
    "C_asset_tags": "Exposed asset class (database, IoT, ICS, medical, devops, open dir)",
    "C_breadth_modules": "Number of distinct services",
    "C_breadth_ports": "Number of distinct ports",
    "C_components_vs_peers": "Web components compared with peers",
    "C_live_web": "Live web service",
    "C_any_service": "A service of theirs answered",
    "D_waf": "Web application firewall in front",
    "D_edge_substitute": "CDN edge in front (partial cover)",
    "D_security_appliance": "Security appliance seen",
    "D_vpn": "VPN gateway seen",
    "D_hardening_headers": "Hardening headers set (HSTS or CSP)",
    "X_small_cloud": "Hosted on a small cloud provider",
}

SORT_SQL = {
    "priority": "priority DESC, rank_overall",
    "exposure": "exposure DESC, rank_overall",
    "n_banners": "n_banners DESC, rank_overall",
    # accounts with a change in the latest delta first, worst change first, then priority
    "recent_change": "max_event_severity DESC NULLS LAST, priority DESC, rank_overall",
}
SUMMARY_COLS = ("entity_id, display_name, key_kind, segment, exposure, priority, rank_overall, "
                "country_code, n_banners, n_ips, org_mode, top_signals, industry, "
                "max_event_severity")


# ---- queries shared by the JSON and HTML routes -----------------------------------------


def _filters(q: str | None, segment: str | None, country: str | None, industry: str | None,
             min_exposure: float | None) -> tuple[str, list[Any]]:
    """WHERE clause and its parameters; filters compose with AND."""
    clauses: list[str] = []
    params: list[Any] = []
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        clauses.append("display_name ILIKE ? ESCAPE '\\'")
        params.append(f"%{escaped}%")
    for col, val in (("segment", segment), ("country_code", country), ("industry", industry)):
        if val:
            clauses.append(f"{col} = ?")
            params.append(val)
    if min_exposure is not None:
        clauses.append("exposure >= ?")
        params.append(min_exposure)
    return ("WHERE " + " AND ".join(clauses)) if clauses else "", params


def list_accounts(b: Bundle, q: str | None, segment: str | None, country: str | None,
                  industry: str | None, min_exposure: float | None, sort: str, page: int,
                  page_size: int) -> AccountPage:
    where, params = _filters(q, segment, country, industry, min_exposure)
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
    signals = [SignalItem(**s, label=SIGNAL_LABELS.get(s["signal_id"], s["signal_id"]),
                          contribution=contrib.get(s["signal_id"]))
               for s in b.query("SELECT signal_id, fact, value, n_banners, pct_in_peer "
                                "FROM signals WHERE entity_id = ? ORDER BY signal_id",
                                [entity_id])]
    evidence: dict[str, list[EvidenceItem]] = {}
    for e in b.query("SELECT signal_id, banner_id, ip, port, module, field, value, snippet, "
                     "observed_at FROM evidence WHERE entity_id = ? "
                     "ORDER BY signal_id, banner_id", [entity_id]):
        evidence.setdefault(e["signal_id"], []).append(EvidenceItem(**e))
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


def stats(b: Bundle) -> dict[str, Any]:
    return {
        "segments": {r["segment"]: r["n"] for r in b.query(
            "SELECT segment, count(*) AS n FROM accounts GROUP BY 1 ORDER BY 2 DESC")},
        "countries_top20": {r["country_code"]: r["n"] for r in b.query(
            "SELECT country_code, count(*) AS n FROM accounts GROUP BY 1 "
            "ORDER BY 2 DESC, 1 LIMIT 20")},
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
    return list_accounts(b, q, segment, country, industry, min_exposure, sort, page, page_size)


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
            "labels": SIGNAL_LABELS, **kw}


@pages.get("/", response_class=HTMLResponse)
def accounts_page(
    request: Request,
    b: BundleDep,
    q: str = "",
    segment: str = "untouched",
    country: str = "",
    industry: str = "",
    min_exposure: str = "",
    sort: Sort = "priority",
    page: Annotated[int, Query(ge=1)] = 1,
) -> HTMLResponse:
    """The accounts table. An htmx request (paging) gets the rows partial only. Form fields
    arrive as text, and an empty field means no filter (segment "" = any segment)."""
    if segment and segment not in get_args(Segment):
        raise HTTPException(422, f"unknown segment {segment!r}")
    try:
        min_exp = float(min_exposure) if min_exposure.strip() else None
    except ValueError as e:
        raise HTTPException(422, f"min_exposure must be a number, got {min_exposure!r}") from e
    res = list_accounts(b, q or None, segment or None, country.upper() or None,
                        industry or None, min_exp, sort, page, PAGE_SIZE)
    form = {"q": q, "segment": segment, "country": country, "industry": industry,
            "min_exposure": min_exposure, "sort": sort}
    name = "_rows.html" if request.headers.get("HX-Request") else "accounts.html"
    return templates.TemplateResponse(request, name, _ctx(request, b, res=res, form=form))


@pages.get("/accounts/{entity_id}", response_class=HTMLResponse)
def account_page(request: Request, entity_id: str, b: BundleDep) -> HTMLResponse:
    acc = account_detail(b, entity_id)
    why = [s for s in sorted(acc.signals, key=lambda s: -(s.contribution or 0))
           if s.signal_id in acc.top_signals]
    protection = [(s, acc.evidence.get(s.signal_id, [])) for s in acc.signals
                  if s.fact == "D"]
    return templates.TemplateResponse(request, "account.html", _ctx(
        request, b, acc=acc, why=why, protection=protection))


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
    return HTMLResponse(f'<p class="done">{text} Thank you.</p>')


def design_sections(path: Path, numbers: tuple[str, ...]) -> str:
    """The `## N.` sections of DESIGN.md with the given numbers, as HTML."""
    text = path.read_text(encoding="utf-8")
    keep: list[str] = []
    on = False
    for line in text.splitlines():
        if line.startswith("## "):
            on = line[3:].split(".", 1)[0].strip() in numbers
        if on:
            keep.append(line)
    return markdown.markdown("\n".join(keep), extensions=["tables", "fenced_code"])


@pages.get("/about", response_class=HTMLResponse)
def about_page(request: Request, b: BundleDep) -> HTMLResponse:
    body = design_sections(paths.REPO_ROOT / "DESIGN.md", ABOUT_SECTIONS)
    return templates.TemplateResponse(request, "about.html", _ctx(request, b, body=body))
