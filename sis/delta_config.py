"""Typed loader for config/delta.yaml (phase P6)."""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from sis import paths


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Cve(_Strict):
    id: str
    cvss: float


class Percent(_Strict):
    drop_banner: float = Field(ge=0.0, le=100.0)
    new_banner: float = Field(ge=0.0, le=100.0)
    expire_cert: float = Field(ge=0.0, le=100.0)
    remove_waf: float = Field(ge=0.0, le=100.0)
    add_waf: float = Field(ge=0.0, le=100.0)
    add_vuln: float = Field(ge=0.0, le=100.0)


class Synth(_Strict):
    seed_default: int
    shift_days: int = Field(gt=0)
    expire_days_before: int = Field(gt=0)
    new_ports: list[int] = Field(min_length=2)
    waf_name: str
    cve: Cve
    percent: Percent


class Severity(_Strict):
    default: int = Field(ge=1, le=3)
    by_type: dict[str, int]
    admin_service_new: int = Field(ge=1, le=3)
    high_signals: list[str]
    high_signal_severity: int = Field(ge=1, le=3)


class Diff(_Strict):
    exposure_threshold: float = Field(gt=0.0)
    severity: Severity


class Verify(_Strict):
    recall_min: dict[str, float]


class DeltaConfig(_Strict):
    synth: Synth
    diff: Diff
    verify: Verify


def load(path: Path | None = None) -> DeltaConfig:
    path = path or paths.config_dir() / "delta.yaml"
    with open(path, encoding="utf-8") as f:
        return DeltaConfig.model_validate(yaml.safe_load(f))
