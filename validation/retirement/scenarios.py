"""Serializable, explicit assumptions for offline retirement experiments."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class AssumptionSource(Record):
    source: str = Field(min_length=1)
    cme_vintage_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class RetirementScenario(Record):
    current_age: int = Field(ge=0, le=120)
    retirement_age: int = Field(ge=0, le=120)
    life_expectancy: int = Field(ge=1, le=150)
    current_savings: float = Field(ge=0)
    annual_savings: float = Field(ge=0)
    desired_annual_income: float = Field(ge=0)
    base_currency: str = Field(default="CNY", pattern=r"^[A-Z]{3}$")
    expected_return: float
    volatility: float = Field(ge=0)
    inflation_rate: float = Field(default=0.025, gt=-1)
    distribution_inflation_rate: float | None = Field(default=None, gt=-1)
    return_multiplier: float = Field(default=0.7, ge=0)
    volatility_multiplier: float = Field(default=0.7, ge=0)
    withdrawal_strategy: Literal["fixed", "guardrails"] = "fixed"
    guardrail_band: float = Field(default=0.2, gt=0, lt=1)
    guardrail_adjust: float = Field(default=0.1, gt=0, lt=1)
    spending_floor_fraction: float = Field(default=0.8, ge=0, le=1)
    n_simulations: int = Field(default=10000, ge=1)
    seed: int = Field(default=42, ge=0)
    model_version: str = Field(default="retirement-annual-v1", min_length=1)
    code_version: str = Field(min_length=1)
    assumption_source: AssumptionSource | None = None

    @model_validator(mode="after")
    def ordered_ages(self):
        if not self.current_age <= self.retirement_age < self.life_expectancy:
            raise ValueError("require current_age <= retirement_age < life_expectancy")
        return self

    @property
    def accumulation_years(self) -> int:
        return self.retirement_age - self.current_age

    @property
    def distribution_years(self) -> int:
        return self.life_expectancy - self.retirement_age

    @property
    def retirement_inflation(self) -> float:
        return (
            self.inflation_rate
            if self.distribution_inflation_rate is None
            else self.distribution_inflation_rate
        )

    def changed(self, **updates) -> "RetirementScenario":
        return type(self).model_validate(self.model_dump() | updates)


class EngineConfig(Record):
    engine: Literal["gbm", "iid_bootstrap", "block_bootstrap"] = "gbm"
    block_length: int = Field(default=6, ge=1)
    bootstrap_mode: Literal["empirical", "matched_gbm_moments"] = "empirical"


class RetirementStress(Record):
    name: str = Field(min_length=1)
    # Annual simple returns replace, rather than add to, the generated returns.
    retirement_returns: tuple[float, ...] = ()
    retirement_inflation: tuple[float, ...] = ()

    @model_validator(mode="after")
    def valid_shocks(self):
        if any(r < -1 for r in self.retirement_returns):
            raise ValueError("stress returns must be >= -1")
        if any(r <= -1 for r in self.retirement_inflation):
            raise ValueError("stress inflation must be > -1")
        return self
