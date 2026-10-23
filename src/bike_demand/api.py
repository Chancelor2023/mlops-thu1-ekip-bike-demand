
import json
import math
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

CODE_REVISION = os.getenv("GIT_SHA", "unknown")

MODEL_DIR = Path(os.getenv("MODEL_DIR", "artifacts"))
MODEL_PATH = MODEL_DIR / "model.joblib"
METADATA_PATH = MODEL_DIR / "model-metadata.json"


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
    temp: float = Field(ge=0, le=1)
    atemp: float = Field(ge=0, le=1)
    hum: float = Field(ge=0, le=1)
    windspeed: float = Field(ge=0, le=1)

    @field_validator("temp", "atemp", "hum", "windspeed")
    @classmethod
    def validate_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("Value must be finite")
        return value


class PredictionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prediction: float = Field(ge=0)
    model_version: str = Field(min_length=1)

    @field_validator("prediction")
    @classmethod
    def validate_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("Prediction must be finite")
        return value


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
        app.state.model = None
        app.state.model_version = None

    yield

    app.state.model = None
    app.state.model_version = None


app = FastAPI(lifespan=lifespan)


@app.middleware("http")
async def log_requests(request, call_next):
    start_time = time.perf_counter()
    status_code = 500

    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    except Exception:
        # Do not log exception details or sensitive request information.
        status_code = 500
        raise
    finally:
        duration_ms = round(
            (time.perf_counter() - start_time) * 1000,
            2,
        )

        log_entry = {
            "event": "http_request",
            "method": request.method,
            "path": request.url.path,
            "status_code": status_code,
            "duration_ms": duration_ms,
        }

        print(json.dumps(log_entry), flush=True)


@app.get("/health")
def health():
    if app.state.model is None:
        raise HTTPException(status_code=503, detail="Model unavailable")

    return {
        "status": "ok",
        "model_version": app.state.model_version,
        "code_revision": CODE_REVISION,
    }


@app.post("/predict", response_model=PredictionResponse)
def predict(features: BikeDemandFeatures):
    model = app.state.model

    if model is None:
        raise HTTPException(status_code=503, detail="Model unavailable")

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
