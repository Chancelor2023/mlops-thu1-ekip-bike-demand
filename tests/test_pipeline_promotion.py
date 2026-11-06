"""Connect the real pipeline, gate and preflight using isolated synthetic inputs.

No canonical candidate experiment, remote call or deployment is performed.
Only training, MLflow persistence and latency measurement are stubbed; CSV
validation, chronological splitting, artifact reload, gate and promotion checks run.
"""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
import yaml

from bike_demand import gate, pipeline, promote
from bike_demand.preflight import sha256
from bike_demand.validate import FEATURES


class SyntheticModel:
    def __init__(self, offset=0):
        self.offset = offset

    def predict(self, features):
        return features["hr"].to_numpy(dtype=float) * 10 + self.offset

    def get_params(self):
        return {"offset": self.offset}


class SyntheticTracking:
    def __init__(self, root):
        self.count = 0

    def start_run(self, *args):
        self.count += 1
        return f"synthetic-run-{self.count}"

    def finish(self, *args):
        pass


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def tree_bytes(directory):
    return {
        str(p.relative_to(directory)): p.read_bytes()
        for p in directory.rglob("*")
        if p.is_file()
    }


@pytest.fixture
def connected(tmp_path, monkeypatch):
    root = tmp_path
    rows = []
    dates = [
        "2011-01-01",
        "2011-12-31",
        "2012-01-01",
        "2012-06-30",
        "2012-07-01",
        "2012-12-31",
    ]
    for i, date in enumerate(dates):
        row = {name: 0 for name in FEATURES}
        row.update(season=1, mnth=1, weathersit=1, hr=i)
        count = 10 if i < 2 else (i * 10 if i < 4 else 9999)
        row.update(instant=i + 1, dteday=date, cnt=count, casual=0, registered=count)
        rows.append(row)
    frame = pd.DataFrame(rows)
    data = root / "data/raw/hour.csv"
    data.parent.mkdir(parents=True)
    frame.to_csv(data, index=False)
    write_json(
        root / "data/manifest.json",
        {
            "sha256": sha256(data),
            "bytes": data.stat().st_size,
            "header": list(frame.columns),
            "rows": len(frame),
        },
    )
    config = {
        "data": "data/raw/hour.csv",
        "features": list(FEATURES),
        "model": dict(pipeline.DEFAULT_MODEL),
    }
    config_path = root / "configs/candidate.yaml"
    config_path.parent.mkdir()
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    policy = root / "configs/gate-policy.yaml"
    policy.write_bytes(
        (Path(__file__).resolve().parents[1] / "configs/gate-policy.yaml").read_bytes()
    )
    accepted = root / "artifacts/accepted/accepted-v1"
    accepted.mkdir(parents=True)
    joblib.dump(SyntheticModel(), accepted / "model.joblib")
    write_json(
        accepted / "model-metadata.json",
        {
            "model_version": "accepted-v1",
            "model_sha256": sha256(accepted / "model.joblib"),
            "features": list(FEATURES),
            "data_sha256": sha256(data),
            "config": config,
        },
    )
    # Match the downloaded reference layout; do not add metrics to the frozen bundle.
    write_json(
        accepted / "reference-evidence/validation-reevaluation.json",
        {
            "model_version": "accepted-v1",
            "model_sha256": sha256(accepted / "model.joblib"),
            "validation_mae": {"random_forest": 0},
        },
    )
    current = {
        "state_id": "synthetic-state-1",
        "model_version": "accepted-v1",
        "bundle_path": "artifacts/accepted/accepted-v1",
        "checksums": {name: sha256(accepted / name) for name in promote.BUNDLE_FILES},
    }
    write_json(root / "artifacts/accepted/current.json", current)

    def fake_fit(train, validation, config):
        assert len(train) == 2 and train["dteday"].dt.year.eq(2011).all()
        assert len(validation) == 2 and validation["cnt"].max() == 30
        model = SyntheticModel()
        return model, model.predict(validation[list(FEATURES)]), 0.0

    monkeypatch.setattr(pipeline, "fit_evaluate", fake_fit)
    monkeypatch.setattr(pipeline, "Tracking", SyntheticTracking)
    monkeypatch.setattr(
        gate, "_default_latency_measure", lambda *args, **kwargs: {"p95_ms": 10}
    )
    real_mae = gate.mean_absolute_error

    def validation_only_mae(y, prediction):
        assert len(y) == 2 and np.max(y) <= 30, "Held-test targets were evaluated"
        return real_mae(y, prediction)

    monkeypatch.setattr(gate, "mean_absolute_error", validation_only_mae)
    return root, accepted, config_path, policy


def test_pipeline_gate_preflight_and_prepare_share_real_decision_format(connected):
    root, accepted, config, policy = connected
    before = tree_bytes(root / "artifacts/accepted")
    code, decision = pipeline.run_pipeline(root, config, accepted)
    assert code == 0, decision
    assert decision["checks"]["performance"]["status"] == "pass"
    assert decision["accepted_reference"]["state_id"] == "synthetic-state-1"
    assert decision["policy_sha256"] == sha256(policy)
    candidate = root / "artifacts/candidates" / decision["model_version"]
    assert decision["evidence_sha256"] == {
        name: sha256(candidate / name) for name in promote.EVALUATED_FILES
    }
    assert promote.preflight(root, candidate, policy)["status"] == "preflight_passed"
    prepared = promote.prepare_promotion(root, candidate, policy, "synthetic-state-1")
    assert prepared["status"] == "prepared"
    assert tree_bytes(root / "artifacts/accepted") == before


def test_real_gate_rejection_is_not_promotable(connected, monkeypatch):
    root, accepted, config, policy = connected

    def worse_candidate(train, validation, settings):
        model = SyntheticModel(offset=1)
        return model, model.predict(validation[list(FEATURES)]), 1.0

    monkeypatch.setattr(pipeline, "fit_evaluate", worse_candidate)
    before = tree_bytes(root / "artifacts/accepted")
    code, decision = pipeline.run_pipeline(root, config, accepted)
    assert code == 2, decision
    assert decision["checks"]["quality"]["status"] == "fail"
    candidate = root / "artifacts/candidates" / decision["model_version"]
    with pytest.raises(ValueError, match="Only an eligible"):
        promote.preflight(root, candidate, policy)
    assert tree_bytes(root / "artifacts/accepted") == before


@pytest.mark.parametrize("changed", ["state", "policy", "candidate-metrics"])
def test_changes_during_real_gate_block_pipeline(connected, monkeypatch, changed):
    root, accepted, config, policy = connected

    def changed_during_measurement(*args, **kwargs):
        if changed == "state":
            path = root / "artifacts/accepted/current.json"
            current = promote.read_object(path)
            current["state_id"] = "another-state"
            write_json(path, current)
        elif changed == "policy":
            policy.write_text("changed: true\n", encoding="utf-8")
        else:
            (path,) = (root / "artifacts/candidates").glob("*/metrics.json")
            write_json(path, {"changed": True})
        return {"p95_ms": 10}

    monkeypatch.setattr(gate, "_default_latency_measure", changed_during_measurement)
    code, decision = pipeline.run_pipeline(root, config, accepted)
    assert code == 3, decision
    assert decision["checks"]["evaluation_integrity"]["status"] == "fail"


def test_missing_current_manifest_blocks_before_training(connected, monkeypatch):
    root, accepted, config, _ = connected
    (root / "artifacts/accepted/current.json").unlink()

    def must_not_train(*args):
        pytest.fail("Training must not start without an accepted reference")

    monkeypatch.setattr(pipeline, "fit_evaluate", must_not_train)
    code, decision = pipeline.run_pipeline(root, config, accepted)
    assert code == 3 and decision["status"] == "blocked"
