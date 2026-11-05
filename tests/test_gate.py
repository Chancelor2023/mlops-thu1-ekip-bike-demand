"""Contract and defect-regression tests for the isolated gate implementation."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import RandomForestRegressor
import statistics

REPO = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(REPO / "src"))

from bike_demand import gate  # noqa: E402

FEATURES = gate.FEATURES


class FixedModel:
    """Return a fixed prediction for each row; suitable for adversarial tests."""

    def __init__(self, value):
        self.value = value

    def predict(self, features):
        return np.full(len(features), self.value, dtype=float)


class PatternModel:
    """Picklable: predicts the validation target pattern 100 + (i % 20) * 2."""

    def predict(self, features):
        return 100.0 + (np.arange(len(features)) % 20) * 2.0


class AdditiveModel:
    """Apply a fixed output perturbation to a fitted estimator."""

    def __init__(self, base, offset):
        self.base = base
        self.offset = offset

    def predict(self, features):
        return self.base.predict(features) + self.offset


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Build deterministic train/validation/test data and the absent repo split API."""
    root = tmp_path
    data_dir = root / "data/raw"
    data_dir.mkdir(parents=True)
    dataset_path = data_dir / "hour.csv"
    n = 120
    frame = pd.DataFrame({name: np.arange(n, dtype=float) for name in FEATURES})
    frame["cnt"] = 100.0 + (np.arange(n) % 20) * 2.0
    frame["instant"] = np.arange(n)
    frame.to_csv(dataset_path, index=False)
    digest = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
    (data_dir / "hour.csv.sha256").write_text(f"{digest}  hour.csv\n")

    # Explicit, deterministic test stub; test rows (80:120) are never passed to gate.
    def load_data(path):
        return pd.read_csv(path)

    def split_data(data):
        return {
            "train": data.iloc[:60].copy(),
            "validation": data.iloc[60:80].copy(),
            "test": data.iloc[80:].copy(),
        }

    validate_module = type(sys)("bike_demand.validate")
    validate_module.load_data = load_data
    validate_module.FEATURES = FEATURES
    split_module = type(sys)("bike_demand.split")
    split_module.split_data = split_data
    monkeypatch.setitem(sys.modules, "bike_demand.validate", validate_module)
    monkeypatch.setitem(sys.modules, "bike_demand.split", split_module)

    cand = root / "artifacts/candidates/c1"
    accepted = root / "artifacts/accepted/a1"
    cand.mkdir(parents=True)
    accepted.mkdir(parents=True)
    policy = root / "configs/gate-policy.yaml"
    policy.parent.mkdir()
    policy.write_text((REPO / "configs/gate-policy.yaml").read_text())

    data = load_data(dataset_path)
    partitions = split_data(data)
    x_train = partitions["train"].loc[:, FEATURES]
    y_train = partitions["train"]["cnt"]
    # Compact RandomForest fixture trained only on the synthetic training partition.
    rf = RandomForestRegressor(n_estimators=8, max_depth=5, random_state=7, n_jobs=1)
    rf.fit(x_train, y_train)
    return {
        "root": root,
        "candidate": cand,
        "accepted": accepted,
        "policy": policy,
        "frame": data,
        "partitions": partitions,
        "rf": rf,
        "manifest": data_dir / "hour.csv.sha256",
    }


def write_bundle(sandbox, directory, model, *, features=None, missing_metrics=False):
    model_path = directory / "model.joblib"
    joblib.dump(model, model_path)
    meta = {
        "data_sha256": hashlib.sha256(
            (sandbox["root"] / "data/raw/hour.csv").read_bytes()
        ).hexdigest(),
        "config": {"data": "data/raw/hour.csv"},
        "features": list(FEATURES if features is None else features),
        "model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
        "validation_mae": {"random_forest": 0.0},
    }
    val = sandbox["partitions"]["validation"]
    pred = np.asarray(model.predict(val.loc[:, FEATURES]), dtype=float)
    mae = (
        float(np.mean(np.abs(val["cnt"].to_numpy(dtype=float) - pred)))
        if np.isfinite(pred).all()
        else 0.0
    )
    meta["validation_mae"]["random_forest"] = mae
    (directory / "model-metadata.json").write_text(json.dumps(meta))
    if not missing_metrics:
        (directory / "metrics.json").write_text(
            json.dumps({"candidate_validation_mae": mae})
        )
    return meta


def latency(candidate_ms=10.0, accepted_ms=10.0):
    values = iter([candidate_ms, accepted_ms])
    return lambda model, features, **kwargs: next(values)


def evaluate(sandbox, *, measure=None):
    return gate.evaluate_candidate(
        sandbox["root"],
        sandbox["candidate"],
        sandbox["accepted"],
        sandbox["policy"],
        latency_measure=measure or latency(),
    )


def setup_pair(sandbox, candidate_model=None, accepted_model=None, **kwargs):
    candidate_model = candidate_model or sandbox["rf"]
    accepted_model = accepted_model or sandbox["rf"]
    write_bundle(sandbox, sandbox["candidate"], candidate_model, **kwargs)
    write_bundle(sandbox, sandbox["accepted"], accepted_model)


def test_eligible_random_forest_on_same_validation_and_no_promotion(sandbox):
    setup_pair(sandbox, PatternModel(), PatternModel())
    result = evaluate(sandbox)

    details = result["checks"]["quality"]["details"]
    assert result["status"] == "eligible"
    assert details["candidate_beats_train_mean"] is True
    assert details["candidate_validation_mae"] < details["train_mean_validation_mae"]
    assert not (sandbox["accepted"] / "decision.json").exists()
    assert not list(sandbox["root"].glob("artifacts/accepted/**/promoted*"))


def test_modified_dataset_checksum_blocks(sandbox):
    setup_pair(sandbox)
    with (sandbox["root"] / "data/raw/hour.csv").open("a") as stream:
        stream.write("\n")
    result = evaluate(sandbox)
    assert result["status"] == "blocked"
    assert result["checks"]["dataset_checksum_and_split"]["status"] == "fail"


def test_reordered_features_block(sandbox):
    setup_pair(sandbox, features=list(reversed(FEATURES)))
    result = evaluate(sandbox)
    assert result["status"] == "blocked"
    assert result["checks"]["feature_contract"]["status"] == "fail"


def test_missing_accepted_proof_blocks(sandbox):
    setup_pair(sandbox)
    (sandbox["accepted"] / "metrics.json").unlink()
    result = evaluate(sandbox)
    assert result["status"] == "blocked"
    assert result["checks"]["accepted_evidence"]["status"] == "fail"


@pytest.mark.parametrize("value", [-2.0, float("nan")])
def test_negative_or_nonfinite_predictions_block(sandbox, value):
    setup_pair(sandbox, FixedModel(value), FixedModel(119.0))
    result = evaluate(sandbox)
    assert result["status"] == "blocked"
    assert result["checks"]["predictions"]["status"] == "fail"


def test_candidate_worse_than_train_mean_is_rejected(sandbox):
    setup_pair(sandbox, FixedModel(200.0), FixedModel(119.0))
    result = evaluate(sandbox)
    assert result["status"] == "rejected"
    assert result["checks"]["quality"]["status"] == "fail"


def test_candidate_worse_than_accepted_by_more_than_epsilon_is_rejected(sandbox):
    # The offset pattern has MAE 1: worse than the accepted pattern (MAE 0),
    # but better than the train-mean baseline (MAE 10).
    setup_pair(sandbox, AdditiveModel(PatternModel(), 1.0), PatternModel())
    result = evaluate(sandbox)
    assert result["status"] == "rejected"
    details = result["checks"]["quality"]["details"]
    assert details["candidate_validation_mae"] < details["train_mean_validation_mae"]
    assert (
        details["candidate_validation_mae"] > details["accepted_validation_mae"] + 1e-6
    )


def test_candidate_at_accepted_plus_epsilon_is_eligible(sandbox):
    # Make validation targets constant so two constant predictors differ in MAE
    # by exactly epsilon while both substantially beat the train-mean baseline.
    data_path = sandbox["root"] / "data/raw/hour.csv"
    changed = sandbox["frame"].copy()
    changed.loc[60:79, "cnt"] = 120.1
    changed.to_csv(data_path, index=False)
    digest = hashlib.sha256(data_path.read_bytes()).hexdigest()
    sandbox["manifest"].write_text(f"{digest}  hour.csv\n")
    setup_pair(sandbox, FixedModel(120.1 + 1e-6), FixedModel(120.1))
    result = evaluate(sandbox)
    assert result["status"] == "eligible"
    details = result["checks"]["quality"]["details"]
    assert details["candidate_validation_mae"] == pytest.approx(
        details["accepted_validation_mae"] + 1e-6, abs=1e-12
    )
    assert "equivalent" in details["accepted_comparison"]


def test_latency_over_25_percent_is_rejected(sandbox):
    setup_pair(sandbox)
    result = evaluate(sandbox, measure=latency(12.51, 10.0))
    assert result["status"] == "rejected"
    assert result["checks"]["performance"]["status"] == "fail"


def test_tampered_model_checksum_blocks(sandbox):
    setup_pair(sandbox)
    with (sandbox["candidate"] / "model.joblib").open("ab") as stream:
        stream.write(b"tamper")
    result = evaluate(sandbox)
    assert result["status"] == "blocked"
    assert result["checks"]["model_sha256"]["status"] == "fail"


def test_missing_candidate_metrics_blocks(sandbox):
    setup_pair(sandbox, missing_metrics=True)
    result = evaluate(sandbox)
    assert result["status"] == "blocked"
    assert result["checks"]["candidate_artifacts"]["status"] == "fail"


def test_accepted_tree_hash_unchanged_after_rejected_or_blocked(sandbox):
    setup_pair(sandbox, FixedModel(200.0), FixedModel(119.0))
    before = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sandbox["accepted"].iterdir()
    }
    assert evaluate(sandbox)["status"] == "rejected"
    after = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sandbox["accepted"].iterdir()
    }
    assert before == after
    (sandbox["accepted"] / "metrics.json").unlink()
    before_blocked = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sandbox["accepted"].iterdir()
    }
    assert evaluate(sandbox)["status"] == "blocked"
    after_blocked = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sandbox["accepted"].iterdir()
    }
    assert before_blocked == after_blocked


def test_missing_manifest_blocks_and_every_check_has_state(sandbox):
    setup_pair(sandbox)
    sandbox["manifest"].unlink()
    result = evaluate(sandbox)
    assert result["status"] == "blocked"
    assert all(
        c["status"] in {"pass", "fail", "not_evaluated"}
        for c in result["checks"].values()
    )


def test_policy_hash_recorded_and_decision_written_only_for_candidate(sandbox):
    setup_pair(sandbox)
    result = evaluate(sandbox)
    decision_path = sandbox["candidate"] / "decision.json"
    assert (
        result["policy_sha256"]
        == hashlib.sha256(sandbox["policy"].read_bytes()).hexdigest()
    )
    assert json.loads(decision_path.read_text())["status"] == result["status"]
    assert not (sandbox["accepted"] / "decision.json").exists()
