"""Lab 7 end-to-end integration: pipeline -> gate -> promotion preflight -> API.

Each test drives the real ``run_pipeline`` on the synthetic world built by the
``connected`` fixture (see ``test_pipeline_promotion.py``): CSV validation,
chronological split, artifact reload, gate checks and promotion checks are real;
only training, MLflow and latency measurement are stubbed. Nothing touches the
canonical dataset, the real accepted bundle, GCS or Cloud Run.

Critical cases covered (Lab 7, Romain): real rejection, missing control, file
modified after evaluation, stale accepted reference, interrupted execution, and
proof that no outcome changes the accepted version or the served model identity.
"""

import json

import pytest
from fastapi.testclient import TestClient

# Reuse the synthetic world of test_pipeline_promotion.py (same style as
# test_deploy.py) so both integration suites share one setup.
from test_pipeline_promotion import SyntheticModel, tree_bytes, write_json
from test_pipeline_promotion import connected as connected

from bike_demand import api, gate, pipeline, promote
from bike_demand.preflight import sha256

pytestmark = pytest.mark.lab7

FEATURES_SAMPLE = {
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


def accepted_snapshot(root):
    """Everything that identifies the accepted version: bytes and current state."""
    accepted = root / "artifacts/accepted"
    return {
        "tree": tree_bytes(accepted),
        "current_sha256": sha256(accepted / "current.json"),
    }


def served_identity(bundle, monkeypatch):
    """Start the real API on a bundle and return what /health and /predict expose."""
    monkeypatch.setattr(api, "MODEL_PATH", bundle / "model.joblib")
    monkeypatch.setattr(api, "METADATA_PATH", bundle / "model-metadata.json")
    with TestClient(api.app) as client:
        health = client.get("/health")
        prediction = client.post("/predict", json=FEATURES_SAMPLE)
    assert health.status_code == 200, health.text
    assert prediction.status_code == 200, prediction.text
    body = health.json()
    return {
        "model_version": body["model_version"],
        "model_sha256": body["model_sha256"],
        "prediction": prediction.json()["prediction"],
    }


def only_candidate(root):
    (candidate,) = (root / "artifacts/candidates").iterdir()
    return candidate


def distinct_candidate(offset=0):
    """Same predictions as asked, but bytes that differ from the accepted model.

    Without this, a candidate identical to the accepted model would make an
    overwrite of the accepted bundle invisible to byte comparisons.
    """
    model = SyntheticModel(offset=offset)
    model.origin = "candidate"
    return model


def make_outcome(outcome, monkeypatch):
    """Steer the real gate to one of its three outcomes."""
    offset = 1 if outcome == "rejected" else 0

    def fit(train, validation, settings):
        model = distinct_candidate(offset)
        predictions = model.predict(validation[list(pipeline.FEATURES)])
        return model, predictions, float(offset)

    monkeypatch.setattr(pipeline, "fit_evaluate", fit)
    if outcome == "blocked":

        def broken_measure(*args, **kwargs):
            raise RuntimeError("latency evidence unavailable")

        monkeypatch.setattr(gate, "_default_latency_measure", broken_measure)


EXPECTED_CODES = {"eligible": 0, "rejected": 2, "blocked": 3}


@pytest.mark.parametrize("outcome", ["eligible", "rejected", "blocked"])
def test_no_gate_outcome_changes_accepted_version_or_served_model(
    connected, monkeypatch, outcome
):
    root, accepted, config, _ = connected
    make_outcome(outcome, monkeypatch)
    before = accepted_snapshot(root)
    served_before = served_identity(accepted, monkeypatch)

    code, decision = pipeline.run_pipeline(root, config, accepted)

    assert code == EXPECTED_CODES[outcome], decision
    assert decision["status"] == outcome
    assert accepted_snapshot(root) == before
    assert served_identity(accepted, monkeypatch) == served_before
    assert served_before["model_version"] == "accepted-v1"
    # The attempt is retained in its own directory, never deleted or reused.
    candidate = only_candidate(root)
    assert candidate.name == decision["model_version"] != "accepted-v1"
    # Guard against a vacuous test: the candidate really is a different artifact.
    assert sha256(candidate / "model.joblib") != served_before["model_sha256"]
    stored = json.loads((candidate / "decision.json").read_text(encoding="utf-8"))
    assert stored["status"] == outcome
    # Eligible never promotes: no staging, no lock, no new accepted version.
    assert not (root / "artifacts/.promotion.lock").exists()
    assert sorted(p.name for p in (root / "artifacts/accepted").iterdir()) == [
        "accepted-v1",
        "current.json",
    ]


def test_real_rejection_records_values_thresholds_and_is_refused(
    connected, monkeypatch
):
    root, accepted, config, policy = connected
    make_outcome("rejected", monkeypatch)
    code, decision = pipeline.run_pipeline(root, config, accepted)
    assert code == 2
    quality = decision["checks"]["quality"]
    assert quality["status"] == "fail"
    assert decision["reasons"], "a rejection must explain itself"
    with pytest.raises(ValueError, match="Only an eligible"):
        promote.preflight(root, only_candidate(root), policy)


@pytest.mark.parametrize("check", sorted(promote.REQUIRED_CHECKS))
@pytest.mark.parametrize("problem", ["missing", "not-passed"])
def test_missing_or_unpassed_control_blocks_promotion(
    connected, monkeypatch, check, problem
):
    root, accepted, config, policy = connected
    code, _ = pipeline.run_pipeline(root, config, accepted)
    assert code == 0
    candidate = only_candidate(root)
    path = candidate / "decision.json"
    decision = json.loads(path.read_text(encoding="utf-8"))
    assert decision["checks"][check]["status"] == "pass"
    if problem == "missing":
        del decision["checks"][check]
    else:
        decision["checks"][check]["status"] = "skipped"
    write_json(path, decision)
    before = accepted_snapshot(root)

    with pytest.raises(ValueError, match="Missing mandatory|not passed"):
        promote.preflight(root, candidate, policy)
    assert accepted_snapshot(root) == before


@pytest.mark.parametrize("name", promote.EVALUATED_FILES)
def test_file_modified_after_evaluation_cannot_be_promoted(connected, name):
    root, accepted, config, policy = connected
    code, decision = pipeline.run_pipeline(root, config, accepted)
    assert code == 0
    candidate = only_candidate(root)
    assert promote.preflight(root, candidate, policy)["status"] == "preflight_passed"
    with (candidate / name).open("ab") as stream:
        stream.write(b"\n")
    before = accepted_snapshot(root)

    with pytest.raises(ValueError):
        promote.preflight(root, candidate, policy)
    with pytest.raises(ValueError):
        promote.prepare_promotion(
            root, candidate, policy, decision["accepted_reference"]["state_id"]
        )
    assert accepted_snapshot(root) == before


def test_stale_accepted_reference_requires_reevaluation(connected):
    """Another version became current after evaluation: the decision is stale."""
    root, accepted, config, policy = connected
    code, decision = pipeline.run_pipeline(root, config, accepted)
    assert code == 0
    candidate = only_candidate(root)
    evaluated_state = decision["accepted_reference"]["state_id"]

    current_path = root / "artifacts/accepted/current.json"
    current = json.loads(current_path.read_text(encoding="utf-8"))
    current["state_id"] = "promoted-by-someone-else"
    write_json(current_path, current)
    before = accepted_snapshot(root)

    with pytest.raises(ValueError, match="different accepted state"):
        promote.preflight(root, candidate, policy)
    with pytest.raises(ValueError):
        promote.prepare_promotion(root, candidate, policy, evaluated_state)
    assert accepted_snapshot(root) == before


def test_tampered_accepted_reference_blocks_evaluation(connected, monkeypatch):
    root, accepted, config, _ = connected
    with (accepted / "model.joblib").open("ab") as stream:
        stream.write(b"\0")

    def must_not_train(*args):
        pytest.fail("Training must not start against an unverified reference")

    monkeypatch.setattr(pipeline, "fit_evaluate", must_not_train)
    code, decision = pipeline.run_pipeline(root, config, accepted)
    assert code == 3 and decision["status"] == "blocked"


@pytest.mark.parametrize("stage", ["training", "gate"])
def test_interrupted_execution_is_never_promotable(connected, monkeypatch, stage):
    """Ctrl+C / kill: no decision is written, so preflight refuses the attempt."""
    root, accepted, config, policy = connected

    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt

    target = (
        (pipeline, "fit_evaluate")
        if stage == "training"
        else (
            gate,
            "_default_latency_measure",
        )
    )
    monkeypatch.setattr(*target, interrupt)
    before = accepted_snapshot(root)

    with pytest.raises(KeyboardInterrupt):
        pipeline.run_pipeline(root, config, accepted)

    candidate = only_candidate(root)
    assert not (candidate / "decision.json").exists()
    with pytest.raises((ValueError, OSError)):
        promote.preflight(root, candidate, policy)
    assert accepted_snapshot(root) == before


def test_crash_after_saving_model_is_blocked_and_rerun_is_isolated(
    connected, monkeypatch
):
    root, accepted, config, policy = connected
    real_write = pipeline.write_json
    calls = {"n": 0}

    def crash_on_metrics(path, value):
        calls["n"] += 1
        if path.name == "metrics.json":
            raise OSError("disk full")
        real_write(path, value)

    monkeypatch.setattr(pipeline, "write_json", crash_on_metrics)
    code, decision = pipeline.run_pipeline(root, config, accepted)
    assert code == 3 and decision["status"] == "blocked"
    partial = only_candidate(root)
    assert (partial / "model.joblib").exists()
    assert not (partial / "metrics.json").exists()
    with pytest.raises(ValueError, match="Only an eligible"):
        promote.preflight(root, partial, policy)

    monkeypatch.setattr(pipeline, "write_json", real_write)
    code, decision = pipeline.run_pipeline(root, config, accepted)
    assert code == 0
    attempts = sorted(p.name for p in (root / "artifacts/candidates").iterdir())
    assert len(attempts) == 2 and partial.name in attempts
    assert decision["model_version"] != partial.name
