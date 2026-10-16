import math

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BikeDemandFeatures(BaseModel):
    # Reject unknown fields and leakage targets (cnt, casual, registered)
    model_config = ConfigDict(extra="forbid")

    # Discrete and categorical features
    season: int = Field(ge=1, le=4, description="Season identifier (1 to 4)")
    yr: int = Field(ge=0, le=1, description="Year identifier (0 or 1)")
    mnth: int = Field(ge=1, le=12, description="Month (1 to 12)")
    hr: int = Field(ge=0, le=23, description="Hour of the day (0 to 23)")
    holiday: int = Field(ge=0, le=1, description="Holiday binary flag")
    weekday: int = Field(ge=0, le=6, description="Day of the week (0 to 6)")
    workingday: int = Field(ge=0, le=1, description="Working day flag")
    weathersit: int = Field(ge=1, le=4, description="Weather category (1 to 4)")

    # Normalized continuous variables bounded strictly in [0, 1]
    temp: float = Field(ge=0.0, le=1.0, description="Normalized temperature")
    atemp: float = Field(ge=0.0, le=1.0, description="Normalized feeling temperature")
    hum: float = Field(ge=0.0, le=1.0, description="Normalized relative humidity")
    windspeed: float = Field(ge=0.0, le=1.0, description="Normalized wind speed")

    @field_validator("temp", "atemp", "hum", "windspeed")
    @classmethod
    def check_finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("Numeric inputs must be finite numbers")
        return v


class PredictionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prediction: float = Field(ge=0.0, description="Finite non-negative prediction")
    model_version: str = Field(
        min_length=1, description="Metadata model version string"
    )

    @field_validator("prediction")
    @classmethod
    def check_finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("Prediction result must be finite")
        return v
