import pytest
from pydantic import ValidationError
from bike_demand.api import BikeDemandFeatures, PredictionResponse

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

def test_valid_input_passes():
    obj = BikeDemandFeatures(**VALID_SAMPLE)
    assert obj.season == 1
    assert obj.hr == 10

@pytest.mark.parametrize("target", ["cnt", "casual", "registered"])
def test_leakage_fields_raise_error(target):
    payload = {**VALID_SAMPLE, target: 42}
    with pytest.raises(ValidationError):
        BikeDemandFeatures(**payload)

@pytest.mark.parametrize("field,value", [
    ("season", 0),
    ("season", 5),
    ("yr", 2),
    ("mnth", 13),
    ("hr", 24),
    ("temp", 1.5),
    ("hum", -0.05),
    ("windspeed", float("nan")),
    ("windspeed", float("inf")),
])
def test_out_of_bounds_and_non_finite_rejected(field, value):
    payload = {**VALID_SAMPLE, field: value}
    with pytest.raises(ValidationError):
        BikeDemandFeatures(**payload)

def test_prediction_response_schema():
    res = PredictionResponse(prediction=12.5, model_version="baseline_v1")
    assert res.prediction == 12.5
    assert res.model_version == "baseline_v1"

def test_negative_prediction_rejected():
    with pytest.raises(ValidationError):
        PredictionResponse(prediction=-1.0, model_version="baseline_v1")