"""Typed loader for config/scoring.yaml (DESIGN.md sections 5.2 and 5.3)."""

import math
from pathlib import Path
from typing import Annotated, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from sis import paths

Weight = Annotated[float, Field(ge=0.0, le=2.0)]
SEGMENTS = ("untouched", "partially_covered", "displace", "low_surface")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _require_keys(d: dict[str, float], expected: set[str]) -> dict[str, float]:
    if set(d) != expected:
        raise ValueError(f"expected keys {sorted(expected)}, got {sorted(d)}")
    return d


class FactA(_Strict):
    weights: dict[str, Weight]

    @field_validator("weights")
    @classmethod
    def _keys(cls, w: dict[str, float]) -> dict[str, float]:
        return _require_keys(
            w, {"eol", "cves_base", "cves_cvss", "fingerprinted", "os_leak", "cpe_per_header"}
        )


class FactB(_Strict):
    weights: dict[str, Weight]

    @field_validator("weights")
    @classmethod
    def _keys(cls, w: dict[str, float]) -> dict[str, float]:
        return _require_keys(w, {"self_signed", "expired", "legacy_tls", "cert_age"})


class FactCCaps(_Strict):
    admin_services: int = Field(gt=0)
    asset_tags: int = Field(gt=0)


class FactC(_Strict):
    weights: dict[str, Weight]
    caps: FactCCaps

    @field_validator("weights")
    @classmethod
    def _keys(cls, w: dict[str, float]) -> dict[str, float]:
        return _require_keys(
            w,
            {"admin_services", "windows_internals", "asset_tags", "breadth_modules",
             "components_vs_peers"},
        )


class FactD(_Strict):
    weights: dict[str, Weight]

    @field_validator("weights")
    @classmethod
    def _keys(cls, w: dict[str, float]) -> dict[str, float]:
        return _require_keys(
            w, {"waf", "security_appliance", "edge_substitute", "vpn", "hardening_headers"}
        )


class Facts(_Strict):
    a: FactA
    b: FactB
    c: FactC
    d: FactD


class Exposure(_Strict):
    weights: dict[str, Weight]

    @field_validator("weights")
    @classmethod
    def _sum_to_one(cls, w: dict[str, float]) -> dict[str, float]:
        _require_keys(w, {"a", "b", "c"})
        if not math.isclose(sum(w.values()), 1.0, abs_tol=1e-9):
            raise ValueError(f"exposure weights must sum to 1.0, got {sum(w.values())}")
        return w


class Segments(_Strict):
    multipliers: dict[str, float]

    @field_validator("multipliers")
    @classmethod
    def _keys(cls, m: dict[str, float]) -> dict[str, float]:
        _require_keys(m, set(SEGMENTS))
        if any(not 0.0 <= v <= 1.0 for v in m.values()):
            raise ValueError("segment multipliers must be in [0, 1]")
        return m


class Peer(_Strict):
    breadth_buckets: list[tuple[int, int | None]]

    @model_validator(mode="after")
    def _contiguous(self) -> Self:
        prev_hi: int | None = 0
        for lo, hi in self.breadth_buckets:
            if prev_hi is None or lo != prev_hi + 1:
                raise ValueError("breadth buckets must be contiguous from 1, only the last open")
            if hi is not None and hi < lo:
                raise ValueError(f"bucket [{lo}, {hi}] is empty")
            prev_hi = hi
        if prev_hi is not None:
            raise ValueError("the last breadth bucket must be open-ended (null upper bound)")
        return self


class ScoringConfig(_Strict):
    scoring_version: str
    facts: Facts
    exposure: Exposure
    segments: Segments
    peer: Peer


def load(path: Path | None = None) -> ScoringConfig:
    path = path or paths.config_dir() / "scoring.yaml"
    with open(path, encoding="utf-8") as f:
        return ScoringConfig.model_validate(yaml.safe_load(f))
