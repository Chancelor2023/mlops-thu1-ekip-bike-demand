import json
import math
import os
from contextlib import asynccontextmanager
from pathlib import Path

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator


class BikeDemandFeatures(BaseModel):
    model_config = ConfigDict(extra="forbid")

    season: int = Field(ge=1, le=4)
    yr: int = Field(ge=0, le=1)
    mnth: int = Field(ge=1, le=12)
    hr: int = Field(ge=0, le=23)
    holiday: int = Field(ge=0, le=1)
    weekday: int = Field(ge=0, le=6)
    workingday: int = Field(ge=0, le=1)
    weathersit: int = Field(ge=1, le=4)

    temp: float = Field(ge=0.0, le=1.0)
    atemp: float = Field(ge=0.0, le=1.0)
    hum: float = Field(ge=0.0, le=1.0)
    windspeed: float = Field(ge=0.0, le=1.0)

    @field_validator("temp", "atemp", "hum", "windspeed")
    @classmethod
    def check_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("Numeric inputs must be finite numbers")
        return value


class PredictionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prediction: float = Field(ge=0.0)
    model_version: str = Field(min_length=1)

    @field_validator("prediction")
    @classmethod
    def check_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("Prediction must be finite")
        return value


MODEL_DIR = Path(os.getenv("MODEL_DIR", "artifacts"))
MODEL_PATH = MODEL_DIR / "model.joblib"
METADATA_PATH = MODEL_DIR / "model-metadata.json"


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.model = None
    app.state.model_version = None

    try:
        model = joblib.load(MODEL_PATH)
        metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
        model_version = metadata["model_version"]

        if not isinstance(model_version, str) or not model_version:
            raise ValueError("Invalid model_version in metadata")

        app.state.model = model
        app.state.model_version = model_version
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        # The API starts, but reports that it cannot serve without a usable model.
        app.state.model = None
        app.state.model_version = None

    yield

    app.state.model = None
    app.state.model_version = None


app = FastAPI(lifespan=lifespan)


@app.get("/health")
def health():
    if app.state.model is None:
        raise HTTPException(status_code=503, detail="Model unavailable")
    return {"status": "ok"}


@app.post("/predict", response_model=PredictionResponse)
def predict(features: BikeDemandFeatures):
    model = app.state.model
    if model is None:
        raise HTTPException(status_code=503, detail="Model unavailable")

    # A DataFrame preserves the named input features used by many sklearn models.
    input_data = pd.DataFrame([features.model_dump()])
    prediction_values = model.predict(input_data)

    prediction = float(prediction_values[0])
    if not math.isfinite(prediction) or prediction < 0:
        raise HTTPException(
            status_code=500,
            detail="Model returned an invalid prediction",
        )

    return PredictionResponse(
        prediction=prediction,
        model_version=app.state.model_version,
    )
