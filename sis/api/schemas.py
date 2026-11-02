"""Response and request models of the JSON API (cards/P5.md)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Segment = Literal["untouched", "partially_covered", "displace", "low_surface"]
Sort = Literal["priority", "exposure", "n_banners"]


class AccountSummary(BaseModel):
    entity_id: str
    display_name: str
    key_kind: str
    segment: str
    exposure: float
    priority: float
    rank_overall: int
    country_code: str | None
    n_banners: int
    n_ips: int
    org_mode: str | None
    top_signals: list[str]
    industry: str | None = None


class PageMeta(BaseModel):
    page: int
    page_size: int
    total: int
    sort: Sort


class AccountPage(BaseModel):
    items: list[AccountSummary]
    meta: PageMeta


class SignalItem(BaseModel):
    signal_id: str
    fact: str
    value: float
    n_banners: int
    pct_in_peer: float | None
    label: str
    contribution: float | None = None


class EvidenceItem(BaseModel):
    signal_id: str
    banner_id: str
    ip: str | None
    port: int | None
    module: str | None
    field: str | None
    value: str | None
    snippet: str | None
    observed_at: datetime | None


class Event(BaseModel):
    event_id: str
    event_type: str
    subject: str | None
    from_file: str | None
    to_file: str | None
    from_value: str | None
    to_value: str | None
    detected_at: datetime | None
    severity: int | None


class Profile(BaseModel):
    is_business: bool | None
    industry: str | None
    description: str | None
    confidence: float | None


class AccountDetail(AccountSummary):
    fact_a: float
    fact_b: float
    fact_c: float
    fact_d: float
    rank_in_segment: int
    rank_in_country: int
    peer_group: str | None
    country_codes: list[str]
    cloud_providers: list[str]
    n_ports: int
    n_modules: int
    scoring_version: str
    file_id: str
    signals: list[SignalItem]
    evidence: dict[str, list[EvidenceItem]]
    events: list[Event]
    profile: Profile | None


class FeedbackIn(BaseModel):
    entity_id: str = Field(min_length=1, max_length=64)
    verdict: Literal["prospect", "not_fit"]
    note: str | None = Field(default=None, max_length=1000)
