"""Synthetic-only checks: never score the retained real model or held course data."""

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def final_evaluator(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "final_evaluation_tested", ROOT / "scripts/evaluate_final.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    data = tmp_path / "data/raw/hour.csv"
    data.parent.mkdir(parents=True)
    data.write_bytes((ROOT / "tests/fixtures/missing-hours.csv").read_bytes())
    frame = pd.read_csv(data)

    def sha(content):
        return hashlib.sha256(content).hexdigest()

    def save(path, value):
        path.write_text(json.dumps(value), encoding="utf-8")

    save(
        tmp_path / "data/manifest.json",
        {
            "sha256": sha(data.read_bytes()),
            "bytes": data.stat().st_size,
            "rows": len(frame),
            "header": list(frame.columns),
        },
    )
    bundle = tmp_path / "artifacts/accepted/synthetic"
    bundle.mkdir(parents=True)
    (bundle / "model.joblib").write_bytes(b"synthetic model bytes, never deserialized")
    metadata = {
        "model_version": "synthetic",
        "model_sha256": sha((bundle / "model.joblib").read_bytes()),
        "features": list(module.FEATURES),
        "data_sha256": sha(data.read_bytes()),
        "config": {"model": {"n_estimators": 50}},
    }
    save(bundle / "model-metadata.json", metadata)
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs/baseline.yaml").write_bytes(b"synthetic config")
    (tmp_path / "uv.lock").write_bytes(b"synthetic lock")
    (tmp_path / "reports").mkdir()
    selection = {
        "features": list(module.FEATURES),
        "target": "cnt",
        "metric": "mean_absolute_error",
        "model_version": "synthetic",
        "bundle_path": "artifacts/accepted/synthetic",
        "checksums": {
            name: sha((bundle / name).read_bytes())
            for name in ("model.joblib", "model-metadata.json")
        },
        "data_path": "data/raw/hour.csv",
        "data_sha256": sha(data.read_bytes()),
        "config_path": "configs/baseline.yaml",
        "config_sha256": sha(b"synthetic config"),
        "uv_lock_sha256": sha(b"synthetic lock"),
        "model_parameters": {"n_estimators": 50},
        "selection_basis": {"held_test_used_for_selection": False},
        "test_period": {"start": "2012-07-01", "end": "2012-12-31", "rows": 2},
    }
    save(tmp_path / "reports/final-model-selection.json", selection)
    calls = []

    class Model:
        feature_names_in_ = np.array(module.FEATURES)

        def get_params(self):
            return {"n_estimators": 50}

        def fit(self, *args):
            raise AssertionError("Final evaluation must not fit")

        def predict(self, features):
            assert list(features.columns) == list(module.FEATURES)
            assert len(features) == 2
            calls.append(features.copy())
            return np.full(len(features), 7.0)

    model = Model()
    monkeypatch.setattr(module.joblib, "load", lambda stream: model)
    return module, tmp_path, bundle, calls, model


def test_dry_run_neither_deserializes_nor_scores(final_evaluator, monkeypatch):
    module, root, _, calls, _ = final_evaluator

    def forbidden_load(stream):
        raise AssertionError("Dry run must not load the model")

    monkeypatch.setattr(module.joblib, "load", forbidden_load)
    result = module.evaluate(root)
    assert result["held_test_scored"] is False
    assert "test_mae" not in result
    assert not calls
    assert not (root / "reports/final-evaluation").exists()


def test_one_prediction_pass_and_no_accidental_second_execution(final_evaluator):
    module, root, _, calls, _ = final_evaluator
    result = module.evaluate(root, execute=True, revision="synthetic-revision")
    assert result["test_mae"] == 83.0  # Synthetic labels 80,100; predictions 7,7.
    assert len(calls) == 1
    output = root / "reports/final-evaluation/result.json"
    original = output.read_bytes()
    with pytest.raises(FileExistsError):
        module.evaluate(root, execute=True)
    assert len(calls) == 1
    assert output.read_bytes() == original


@pytest.mark.parametrize("name", ["model.joblib", "model-metadata.json"])
def test_corruption_blocks_before_any_prediction(final_evaluator, name):
    module, root, bundle, calls, _ = final_evaluator
    (bundle / name).write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum mismatch"):
        module.evaluate(root, execute=True)
    assert not calls
    assert not (root / "reports/final-evaluation").exists()


def test_change_during_prediction_retains_failure_without_published_score(
    final_evaluator, monkeypatch
):
    module, root, bundle, _, model = final_evaluator
    predict = model.predict

    def change_model(features):
        (bundle / "model.joblib").write_bytes(b"changed during prediction")
        return predict(features)

    monkeypatch.setattr(model, "predict", change_model)
    with pytest.raises(ValueError, match="changed during evaluation"):
        module.evaluate(root, execute=True)
    output = root / "reports/final-evaluation"
    assert (output / "failure.json").is_file()
    assert not (output / "result.json").exists()
