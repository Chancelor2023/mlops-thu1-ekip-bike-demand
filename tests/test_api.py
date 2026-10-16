
import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from bike_demand import api

VALID_SAMPLE = {
    "season": 1,
    "yr": 0,
    "mnth": 1,
    "hr": 10,
    "holiday": 0,
    "weekday": 2,
    "workingday": 1,
    "weathersit": 1,
    "temp": 0.24,
    "atemp": 0.28,
    "hum": 0.80,
    "windspeed": 0.15,
}


class FakeModel:
    """Small deterministic model used only by the API tests."""

    def predict(self, data):
        return [12.5]


@pytest.fixture
def client_with_model(monkeypatch, tmp_path):
    """Start the API with a predictable fake model and metadata."""
    model_path = tmp_path / "model.joblib"
    metadata_path = tmp_path / "model-metadata.json"

    model_path.touch()
    metadata_path.write_text(
        json.dumps({"model_version": "test_v1"}),
        encoding="utf-8",
    )

    monkeypatch.setattr(api, "MODEL_PATH", model_path)
    monkeypatch.setattr(api, "METADATA_PATH", metadata_path)
    monkeypatch.setattr(api.joblib, "load", lambda path: FakeModel())

    with TestClient(api.app) as client:
        yield client


@pytest.fixture
def client_without_model(monkeypatch, tmp_path):
    """Start the API without an available model."""
    monkeypatch.setattr(
        api,
        "MODEL_PATH",
        tmp_path / "missing-model.joblib",
    )
    monkeypatch.setattr(
        api,
        "METADATA_PATH",
        tmp_path / "missing-model-metadata.json",
    )

    with TestClient(api.app) as client:
        yield client


def test_health_returns_200_when_model_is_loaded(client_with_model):
    response = client_with_model.get("/health")

    assert response.status_code == 200


def test_valid_prediction_returns_prediction_and_version(client_with_model):
    response = client_with_model.post("/predict", json=VALID_SAMPLE)

    assert response.status_code == 200

    body = response.json()
    assert body["prediction"] == 12.5
    assert body["model_version"] == "test_v1"


def test_missing_field_returns_422(client_with_model):
    payload = VALID_SAMPLE.copy()
    del payload["season"]

    response = client_with_model.post("/predict", json=payload)

    assert response.status_code == 422


def test_wrong_type_returns_422(client_with_model):
    payload = {**VALID_SAMPLE, "season": "summer"}

    response = client_with_model.post("/predict", json=payload)

    assert response.status_code == 422


@pytest.mark.parametrize(
    "field,value",
    [
        ("season", 0),
        ("season", 5),
        ("yr", 2),
        ("mnth", 13),
        ("hr", 24),
        ("weekday", 7),
        ("weathersit", 5),
        ("temp", 1.5),
        ("atemp", -0.1),
    ],
)
def test_out_of_range_value_returns_422(
    client_with_model,
    field,
    value,
):
    payload = {**VALID_SAMPLE, field: value}

    response = client_with_model.post("/predict", json=payload)

    assert response.status_code == 422


@pytest.mark.parametrize(
    "value",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
    ],
)
def test_non_finite_values_are_rejected(value):
    payload = {**VALID_SAMPLE, "hum": value}

    with pytest.raises(ValidationError):
        api.BikeDemandFeatures(**payload)


@pytest.mark.parametrize("field", ["cnt", "casual", "registered"])
def test_target_leakage_fields_return_422(client_with_model, field):
    payload = {**VALID_SAMPLE, field: 42}

    response = client_with_model.post("/predict", json=payload)

    assert response.status_code == 422


def test_health_returns_503_when_model_is_missing(client_without_model):
    response = client_without_model.get("/health")

    assert response.status_code == 503


def test_prediction_returns_503_when_model_is_missing(client_without_model):
    response = client_without_model.post("/predict", json=VALID_SAMPLE)

    assert response.status_code == 503
