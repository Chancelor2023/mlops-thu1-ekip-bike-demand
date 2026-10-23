import json
import logging
import math
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

CODE_REVISION = os.getenv("CODE_REVISION", "unknown")

MODEL_DIR = Path(os.getenv("MODEL_DIR", "artifacts"))
MODEL_PATH = MODEL_DIR / "model.joblib"
METADATA_PATH = MODEL_DIR / "model-metadata.json"

logger = logging.getLogger("bike_demand.api")


def write_log(
    *,
    event: str,
    request_id: str | None = None,
    status: int | str | None = None,
    duration_ms: float | None = None,
    model_version: str | None = None,
) -> None:
    """Write one structured JSON log entry without request data or secrets."""
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "request_id": request_id,
        "status": status,
        "duration_ms": duration_ms,
        "model_version": model_version,
        "code_revision": CODE_REVISION,
    }
    print(json.dumps(entry), flush=True)


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
            raise ValueError("Numeric inputs must be finite numbers")
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

        write_log(
            event="startup",
            status="loaded",
            model_version=model_version,
        )

    except (OSError, ValueError, KeyError, TypeError):
        app.state.model = None
        app.state.model_version = None

        write_log(
            event="startup",
            status="unavailable",
        )

    yield

    app.state.model = None
    app.state.model_version = None


app = FastAPI(lifespan=lifespan)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    start_time = time.perf_counter()
    status = 500
    event = "request"

    try:
        response = await call_next(request)
        status = response.status_code

        if status == 503:
            event = "model_unavailable"
        elif status == 422:
            event = "rejected"
        elif request.url.path == "/predict" and status < 400:
            event = "predicted"
        elif request.url.path == "/health":
            event = "health"
        elif status >= 400:
            event = "rejected"

        response.headers["X-Request-ID"] = request_id
        return response

    except Exception:
        # Do not log exception details or request contents.
        event = "request_error"
        status = 500
        raise

    finally:
        duration_ms = round(
            (time.perf_counter() - start_time) * 1000,
            2,
        )

        write_log(
            event=event,
            request_id=request_id,
            status=status,
            duration_ms=duration_ms,
            model_version=getattr(request.app.state, "model_version", None),
        )


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
