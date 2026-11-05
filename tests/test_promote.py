"""Synthetic bytes only: these tests never train, unpickle, promote or deploy."""

import json

import pytest

from bike_demand import promote


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def scenario(tmp_path):
    accepted = tmp_path / "artifacts/accepted/accepted-v1"
    accepted.mkdir(parents=True)
    (accepted / "model.joblib").write_bytes(b"synthetic accepted model")
    write_json(
        accepted / "model-metadata.json",
        {
            "model_version": "accepted-v1",
            "model_sha256": promote.sha256(accepted / "model.joblib"),
        },
    )
    current = {
        "state_id": "state-1",
        "model_version": "accepted-v1",
        "bundle_path": "artifacts/accepted/accepted-v1",
        "checksums": {
            name: promote.sha256(accepted / name) for name in promote.BUNDLE_FILES
        },
    }
    write_json(tmp_path / "artifacts/accepted/current.json", current)
    policy = tmp_path / "configs/gate-policy.yaml"
    policy.parent.mkdir()
    policy.write_text("synthetic_policy: true\n", encoding="utf-8")
    candidate = tmp_path / "artifacts/candidates/candidate-v2"
    candidate.mkdir(parents=True)
    (candidate / "model.joblib").write_bytes(b"synthetic candidate model")
    write_json(
        candidate / "model-metadata.json",
        {
            "model_version": "candidate-v2",
            "model_run_id": "synthetic-run",
            "model_sha256": promote.sha256(candidate / "model.joblib"),
        },
    )
    write_json(candidate / "metrics.json", {"synthetic": True})
    decision = {
        "status": "eligible",
        "model_version": "candidate-v2",
        "model_run_id": "synthetic-run",
        "model_sha256": promote.sha256(candidate / "model.joblib"),
        "checks": {name: {"passed": True} for name in promote.REQUIRED_CHECKS},
        "accepted_reference": {
            key: current[key] for key in ("state_id", "model_version", "checksums")
        },
        "policy_sha256": promote.sha256(policy),
        "evidence_sha256": {
            name: promote.sha256(candidate / name) for name in promote.EVALUATED_FILES
        },
    }
    write_json(candidate / "decision.json", decision)
    return tmp_path, candidate, policy, decision


def snapshot(root):
    return {
        str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()
    }


def test_valid_preflight_writes_nothing(scenario):
    root, candidate, policy, _ = scenario
    before = snapshot(root)
    result = promote.preflight(root, candidate, policy)
    assert result["status"] == "preflight_passed"
    assert result["promoted"] is False
    assert result["deployed"] is False
    assert snapshot(root) == before


@pytest.mark.parametrize("status", ["rejected", "blocked", None])
def test_noneligible_candidate_is_refused_without_writes(scenario, status):
    root, candidate, policy, decision = scenario
    decision["status"] = status
    write_json(candidate / "decision.json", decision)
    before = snapshot(root)
    with pytest.raises(ValueError, match="Only an eligible"):
        promote.preflight(root, candidate, policy)
    assert snapshot(root) == before


@pytest.mark.parametrize("file", promote.EVALUATED_FILES)
def test_tampered_candidate_evidence_is_refused(scenario, file):
    root, candidate, policy, _ = scenario
    (candidate / file).write_bytes(b"changed after evaluation")
    with pytest.raises(ValueError, match="Checksum mismatch"):
        promote.preflight(root, candidate, policy)


def test_changed_policy_is_refused(scenario):
    root, candidate, policy, _ = scenario
    policy.write_text("changed: true\n", encoding="utf-8")
    with pytest.raises(ValueError, match="policy missing or changed"):
        promote.preflight(root, candidate, policy)


def test_changed_incumbent_is_refused(scenario):
    root, candidate, policy, _ = scenario
    path = root / "artifacts/accepted/current.json"
    current = promote.read_object(path)
    current["state_id"] = "state-2"
    write_json(path, current)
    with pytest.raises(ValueError, match="different accepted state"):
        promote.preflight(root, candidate, policy)


def test_tampered_accepted_model_is_refused(scenario):
    root, candidate, policy, _ = scenario
    (root / "artifacts/accepted/accepted-v1/model.joblib").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="Checksum mismatch"):
        promote.preflight(root, candidate, policy)


@pytest.mark.parametrize("problem", ["missing", "false", "string"])
def test_incomplete_checks_are_refused(scenario, problem):
    root, candidate, policy, decision = scenario
    if problem == "missing":
        del decision["checks"]["integrity"]
    else:
        decision["checks"]["integrity"]["passed"] = (
            False if problem == "false" else "true"
        )
    write_json(candidate / "decision.json", decision)
    with pytest.raises(ValueError, match="gate checks|Gate check"):
        promote.preflight(root, candidate, policy)


def test_candidate_outside_candidate_directory_is_refused(scenario):
    root, _, policy, _ = scenario
    with pytest.raises(ValueError, match="Path must be inside"):
        promote.preflight(root, root / "artifacts/accepted/accepted-v1", policy)
