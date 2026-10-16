import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

import joblib
import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from bike_demand.schemas import PredictionRequest


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
        version = metadata["model_version"]
        app.state.model = model
        app.state.model_version = str(version)
    except (OSError, ValueError, KeyError, TypeError):
        pass

    yield

    app.state.model = None
    app.state.model_version = None


app = FastAPI(lifespan=lifespan)


class PredictionResponse(BaseModel):
    prediction: float
    model_version: str


@app.get("/health")
def health():
    if app.state.model is None:
        raise HTTPException(status_code=503, detail="Model unavailable")
    return {"status": "ok"}


@app.post("/predict", response_model=PredictionResponse)
def predict(request: PredictionRequest):
    model = app.state.model
    if model is None:
        raise HTTPException(status_code=503, detail="Model unavailable")

    features = request.model_dump()
    values = np.asarray(model.predict([features]), dtype=float).reshape(-1)

    if values.size != 1 or not np.isfinite(values[0]) or values[0] < 0:
        raise HTTPException(status_code=500, detail="Model returned an invalid prediction")

    return PredictionResponse(
        prediction=float(values[0]),
        model_version=app.state.model_version,
    )