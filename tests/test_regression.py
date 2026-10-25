# Regression: recompute the validation MAEs recorded in Labs 2 and 4.

from pathlib import Path

import pytest

from bike_demand.split import split_data
from bike_demand.train import compare_mean, fit_evaluate, load_config
from bike_demand.validate import load_data

pytestmark = pytest.mark.regression

ROOT = Path(__file__).resolve().parents[1]

# Recorded by the Lab 4 container run (reports/logs/lab-04/03-train-into-volume.log),
# identical to the Lab 2 laptop run.
RECORDED_MAE = {
    "naive_train_mean": 154.23179306864967,
    "random_forest": 86.84685685591091,
}
# Same value to the last digit on every machine measured so far (see README "CI");
# 1e-6 only absorbs floating-point noise, far below any real model change.
TOLERANCE = 1e-6


@pytest.fixture(scope="module")
def recomputed_mae():
    config = load_config(ROOT / "configs/baseline.yaml")
    partitions = split_data(load_data(ROOT / config["data"]))
    train, validation = partitions["train"], partitions["validation"]
    _, naive_mae = compare_mean(train["cnt"], validation["cnt"])
    _, _, rf_mae = fit_evaluate(train, validation, config)
    # Printed so a CI log (pytest -s) records the value measured on that machine
    print(f"\nrecomputed validation MAE: naive={naive_mae!r} random_forest={rf_mae!r}")
    return {"naive_train_mean": naive_mae, "random_forest": rf_mae}


@pytest.mark.parametrize("name", sorted(RECORDED_MAE))
def test_validation_mae_matches_record(recomputed_mae, name):
    assert recomputed_mae[name] == pytest.approx(RECORDED_MAE[name], abs=TOLERANCE)
