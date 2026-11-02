"""Typed loader for config/eval.yaml (cards/P4.md)."""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from sis import paths


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Fixture(_Strict):
    seed: int
    n_entities: int = Field(gt=0)
    k: int = Field(gt=0)
    labels: list[str]
    threshold_factor: float = Field(gt=0.0, le=1.0)


class EvalConfig(_Strict):
    ks: list[int]
    z: float = Field(gt=0.0)
    random_seeds: list[int]
    fixture: Fixture


def load(path: Path | None = None) -> EvalConfig:
    path = path or paths.config_dir() / "eval.yaml"
    with open(path, encoding="utf-8") as f:
        return EvalConfig.model_validate(yaml.safe_load(f))
