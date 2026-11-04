"""Typed loader for config/llm_tiers.yaml (DESIGN.md section 7.1)."""

import math
from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from sis import paths
from sis.config import settings

TierName = Literal["reasoning", "mid", "errand"]
REQUIRED_TASKS = ("classify", "reportcard", "judge", "mcp_agent")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TierSpec(_Strict):
    models: list[str] = Field(min_length=2, max_length=3)
    rpm: int = Field(gt=0)
    concurrency: int = Field(gt=0)
    budget_usd: float = Field(ge=0)

    @model_validator(mode="after")
    def _distinct(self) -> Self:
        if len(set(self.models)) != len(self.models):
            raise ValueError(f"duplicate model in tier: {self.models}")
        return self


class Escalation(_Strict):
    max_steps: int = Field(ge=0)


class TiersConfig(_Strict):
    models_verified_on: str
    router: Literal["openrouter"]
    tiers: dict[TierName, TierSpec]
    tasks: dict[str, TierName]
    escalation: Escalation
    reserve_usd: float = Field(ge=0)

    @model_validator(mode="after")
    def _complete(self) -> Self:
        missing_tiers = {"reasoning", "mid", "errand"} - set(self.tiers)
        if missing_tiers:
            raise ValueError(f"tiers missing: {sorted(missing_tiers)}")
        missing_tasks = set(REQUIRED_TASKS) - set(self.tasks)
        if missing_tasks:
            raise ValueError(f"tasks without a tier: {sorted(missing_tasks)}")
        return self

    def check_budget(self, total_usd: float) -> None:
        spend = sum(t.budget_usd for t in self.tiers.values()) + self.reserve_usd
        if spend > total_usd and not math.isclose(spend, total_usd, abs_tol=1e-9):
            raise ValueError(f"tier budgets + reserve = {spend} exceed total {total_usd}")


def load(path: Path | None = None, total_usd: float | None = None) -> TiersConfig:
    path = path or paths.config_dir() / "llm_tiers.yaml"
    with open(path, encoding="utf-8") as f:
        cfg = TiersConfig.model_validate(yaml.safe_load(f))
    cfg.check_budget(settings.LLM_BUDGET_USD_TOTAL if total_usd is None else total_usd)
    return cfg
