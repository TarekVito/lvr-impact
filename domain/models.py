from datetime import date
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class SimulationParams(BaseModel):
    capital: float = Field(gt=0)
    max_drop_percent: float = Field(ge=10, le=70)
    rebalance_frequency: str = Field(pattern="^(Never|Daily|Monthly|Quarterly)$")
    start_date: date
    end_date: date
    
    @field_validator("end_date")
    @classmethod
    def end_after_start(cls, v: date, info) -> date:
        if "start_date" in info.data and v <= info.data["start_date"]:
            raise ValueError("end_date must be after start_date")
        return v


class SimulationResult(BaseModel):
    liquidated: bool
    liquidation_date: Optional[date]
    final_equity: float
    total_return_pct: float
    total_costs_paid: float
    initial_units: float


class BenchmarkResult(BaseModel):
    final_equity: float
    total_return_pct: float
    units_held: float
