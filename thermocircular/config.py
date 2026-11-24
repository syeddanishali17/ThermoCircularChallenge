"""Validated UI and JSON inputs for the frozen audited model."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False, strict=True, validate_default=True)

    site: Literal["Vienna", "Linz", "Graz"] = "Vienna"
    it_mw: float = Field(75, gt=0, le=200)
    grid_mw: float = Field(100, gt=0, le=500)
    pv_mwp: float = Field(2, ge=0, le=300)
    pv_fraction: float = Field(1, ge=0, le=3)
    price_multiplier: float = Field(1, ge=0, le=10)
    carbon_g: float = Field(123, ge=0, le=2000)
    heat_scale: float = Field(1, ge=0, le=10)
    cop: float = Field(0, ge=0, le=20)
    heat_tariff: float = Field(85, gt=0, le=1000)
    pipe_km: float = Field(1, ge=0, le=100)
    pipe_cost_per_km_m: float = Field(2, ge=0, le=100)
    nonpipe_stage_one_m: float = Field(10, ge=0, le=1000)
    stage_two_m: float = Field(6, ge=0, le=1000)
    hot_delta_c: float = Field(0, ge=-20, le=30)
    heat_outage_hours: int = Field(0, ge=0, le=2160)
    peak_restriction_mw: float = Field(0, ge=0, le=500)
    expensive_hours: int = Field(0, ge=0, le=2160)
    minimum_increment_gwh: float = Field(5, ge=0, le=500)
    gas_residual_t_mwh: float = Field(0.202 / 0.90, ge=0, le=2)
    hydro_mw: float = Field(20, ge=0, le=500)
    hydro_fraction: float = Field(1, ge=0, le=3)
    wind_mw: float = Field(30, ge=0, le=500)
    wind_fraction: float = Field(1, ge=0, le=3)
    hardware_efficiency_ratio: float = Field(1.7, gt=1, le=20)
    hardware_footprint_kg: float = Field(2274, ge=0, le=100000)
    replacement_horizon_years: float = Field(3, gt=0, le=50)
    module_mw: float = Field(5, gt=0, le=100)

    @model_validator(mode="after")
    def physical_bounds(self):
        if 0 < self.cop <= 1:
            raise ValueError("COP must be zero (automatic) or exceed 1.")
        if self.peak_restriction_mw > self.grid_mw:
            raise ValueError("Winter import reduction cannot exceed the connection capacity.")
        return self


DEFAULT = Settings()
PRESETS = {
    "Base": {},
    "Low renewable year": dict(pv_fraction=.75, hydro_fraction=.65, wind_fraction=.8, carbon_g=180),
    "High winter price": dict(expensive_hours=320),
    "High summer temperature": dict(hot_delta_c=5),
    "Winter import cap 63 MW": dict(peak_restriction_mw=37),
    "Grid delay or 90 MW firm": dict(grid_mw=90),
    "Half heat demand": dict(heat_scale=.5),
    "Heat buyer outage 336 h": dict(heat_outage_hours=336),
    "Electricity +30%": dict(price_multiplier=1.3),
    "Pipe route 3 km": dict(pipe_km=3),
    "Civil cost +30%": dict(nonpipe_stage_one_m=13, pipe_cost_per_km_m=2.6),
    "Low delivered tariff": dict(heat_tariff=65),
    "COP 3": dict(cop=3),
    "High import carbon / low-carbon DH counterfactual": dict(carbon_g=550, gas_residual_t_mwh=.080),
    "Graz solar proxy": dict(site="Graz"),
    "Linz uncalibrated solar proxy": dict(site="Linz"),
    "50 MW IT initial phase": dict(it_mw=50, grid_mw=75),
    "100 MW IT test above facility limit": dict(it_mw=100, grid_mw=100),
    "10 MWp ground PV sensitivity": dict(pv_mwp=10),
    "Efficient heat pump customer": dict(gas_residual_t_mwh=.123 / 3),
    "Stress combination": dict(expensive_hours=320, carbon_g=220, peak_restriction_mw=38),
}
