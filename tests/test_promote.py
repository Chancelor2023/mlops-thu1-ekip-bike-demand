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


def test_prepare_stages_exact_bytes_and_preserves_accepted_state(scenario):
    root, candidate, policy, _ = scenario
    before = snapshot(root / "artifacts/accepted")
    result = promote.prepare_promotion(root, candidate, policy, "state-1")
    stage = root / result["staging_path"]
    assert result["status"] == "prepared"
    assert result["promoted"] is False and result["deployed"] is False
    for name in (*promote.EVALUATED_FILES, "decision.json"):
        assert (stage / "bundle" / name).read_bytes() == (candidate / name).read_bytes()
    assert (stage / "gate-policy.yaml").read_bytes() == policy.read_bytes()
    assert (stage / "01-prepared.json").is_file()
    assert snapshot(root / "artifacts/accepted") == before
    assert not (root / "artifacts/.promotion.lock").exists()


def test_concurrent_prepare_is_blocked(scenario):
    root, candidate, policy, _ = scenario
    with promote.promotion_lock(root):
        with pytest.raises(ValueError, match="lock already exists"):
            promote.prepare_promotion(root, candidate, policy, "state-1")
        assert (root / "artifacts/.promotion.lock").is_file()
    assert not (root / "artifacts/promotions").exists()


def test_expected_state_is_checked_under_lock(scenario):
    root, candidate, policy, _ = scenario
    before = snapshot(root)
    with pytest.raises(ValueError, match="Expected accepted state changed"):
        promote.prepare_promotion(root, candidate, policy, "outdated-state")
    assert snapshot(root) == before


def test_interrupted_copy_keeps_journal_and_preserves_accepted(scenario, monkeypatch):
    root, candidate, policy, _ = scenario
    before = snapshot(root / "artifacts/accepted")

    def interrupted(*args):
        raise OSError("simulated interrupted copy")

    monkeypatch.setattr(promote.shutil, "copyfile", interrupted)
    with pytest.raises(OSError, match="simulated interrupted copy"):
        promote.prepare_promotion(root, candidate, policy, "state-1")
    (stage,) = (root / "artifacts/promotions").iterdir()
    assert promote.read_object(stage / "99-blocked.json")["status"] == "blocked"
    assert not (stage / "01-prepared.json").exists()
    assert snapshot(root / "artifacts/accepted") == before
    assert not (root / "artifacts/.promotion.lock").exists()


def test_copy_corruption_is_detected(scenario, monkeypatch):
    root, candidate, policy, _ = scenario
    original = promote.shutil.copyfile

    def corrupt(source, destination):
        original(source, destination)
        if destination.name == "model.joblib":
            destination.write_bytes(b"corruption during copy")

    monkeypatch.setattr(promote.shutil, "copyfile", corrupt)
    with pytest.raises(ValueError, match="Checksum mismatch"):
        promote.prepare_promotion(root, candidate, policy, "state-1")
    (stage,) = (root / "artifacts/promotions").iterdir()
    assert not (stage / "01-prepared.json").exists()


def test_repeated_preparation_retains_previous_attempt(scenario):
    root, candidate, policy, _ = scenario
    first = promote.prepare_promotion(root, candidate, policy, "state-1")
    before = snapshot(root / first["staging_path"])
    second = promote.prepare_promotion(root, candidate, policy, "state-1")
    assert first["operation_id"] != second["operation_id"]
    assert snapshot(root / first["staging_path"]) == before


@pytest.mark.parametrize("changed", ["candidate", "policy", "accepted-state"])
def test_inputs_changed_during_preparation_cannot_be_prepared(
    scenario, monkeypatch, changed
):
    root, candidate, policy, _ = scenario
    original = promote.shutil.copyfile

    def change_input(source, destination):
        original(source, destination)
        if destination.name == "gate-policy.yaml":
            if changed == "candidate":
                (candidate / "metrics.json").write_bytes(b"changed after copy")
            elif changed == "policy":
                policy.write_text("changed: true\n", encoding="utf-8")
            else:
                path = root / "artifacts/accepted/current.json"
                current = promote.read_object(path)
                current["state_id"] = "concurrent-state"
                write_json(path, current)

    monkeypatch.setattr(promote.shutil, "copyfile", change_input)
    with pytest.raises(ValueError):
        promote.prepare_promotion(root, candidate, policy, "state-1")
    (stage,) = (root / "artifacts/promotions").iterdir()
    assert not (stage / "01-prepared.json").exists()
    assert (stage / "99-blocked.json").is_file()
