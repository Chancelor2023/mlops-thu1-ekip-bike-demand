"""Synthetic bytes only: these tests never train, unpickle, promote or deploy."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from bike_demand import promote

pytestmark = pytest.mark.lab7


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
        "checks": {name: {"status": "pass"} for name in promote.REQUIRED_CHECKS},
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
        del decision["checks"]["model_sha256"]
    else:
        decision["checks"]["model_sha256"]["status"] = (
            "fail" if problem == "false" else True
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


@pytest.fixture
def installation(scenario, monkeypatch):
    root, candidate, policy, _ = scenario
    prepared = promote.prepare_promotion(root, candidate, policy, "state-1")
    # Git branch/revision guards are covered separately below. These tests only
    # exercise installation of synthetic bytes into a temporary filesystem.
    monkeypatch.setattr(promote, "require_main_checkout", lambda *args: None)
    return root, candidate, policy, root / prepared["staging_path"]


def test_install_keeps_current_and_previous_bundle_unchanged(installation):
    root, _, _, stage = installation
    current = (root / "artifacts/accepted/current.json").read_bytes()
    previous = snapshot(root / "artifacts/accepted/accepted-v1")
    result = promote.install_local(root, stage, "state-1", "main-commit")
    target = root / result["installed_bundle_path"]
    for name in (*promote.EVALUATED_FILES, "decision.json"):
        assert (target / name).read_bytes() == (stage / "bundle" / name).read_bytes()
    assert result["status"] == "installed_local_pending_cloud"
    assert result["current_manifest_updated"] is False
    assert result["promoted"] is False and result["deployed"] is False
    assert (root / "artifacts/accepted/current.json").read_bytes() == current
    assert snapshot(root / "artifacts/accepted/accepted-v1") == previous


def test_install_retry_is_idempotent(installation):
    root, _, _, stage = installation
    first = promote.install_local(root, stage, "state-1", "main-commit")
    before = snapshot(root)
    second = promote.install_local(root, stage, "state-1", "main-commit")
    assert first == second
    assert snapshot(root) == before


def test_install_refuses_existing_version_from_another_operation(installation):
    root, _, _, stage = installation
    destination = root / "artifacts/accepted/candidate-v2"
    destination.mkdir()
    marker = destination / "preserve.txt"
    marker.write_text("existing version", encoding="utf-8")
    before = snapshot(destination)
    with pytest.raises(ValueError, match="Missing regular bundle file"):
        promote.install_local(root, stage, "state-1", "main-commit")
    assert snapshot(destination) == before
    assert not (stage / "02-installed-local.json").exists()


@pytest.mark.parametrize("changed", ["state", "policy", "staged-model", "journal"])
def test_install_revalidates_prepared_evidence(installation, changed):
    root, _, policy, stage = installation
    if changed == "state":
        path = root / "artifacts/accepted/current.json"
        current = promote.read_object(path)
        current["state_id"] = "new-state"
        write_json(path, current)
    elif changed == "policy":
        policy.write_text("changed: true\n", encoding="utf-8")
    elif changed == "staged-model":
        (stage / "bundle/model.joblib").write_bytes(b"modified staged model")
    else:
        path = stage / "01-prepared.json"
        value = promote.read_object(path)
        value["evidence_sha256"]["model.joblib"] = "changed"
        write_json(path, value)
    with pytest.raises(ValueError):
        promote.install_local(root, stage, "state-1", "main-commit")
    assert not (root / "artifacts/accepted/candidate-v2").exists()
    assert not (stage / "02-installed-local.json").exists()


def test_install_copy_failure_never_exposes_partial_final_bundle(
    installation, monkeypatch
):
    root, _, _, stage = installation
    current = (root / "artifacts/accepted/current.json").read_bytes()

    def interrupted(*args):
        raise OSError("simulated installation copy failure")

    monkeypatch.setattr(promote.shutil, "copyfile", interrupted)
    with pytest.raises(OSError, match="installation copy failure"):
        promote.install_local(root, stage, "state-1", "main-commit")
    assert not (root / "artifacts/accepted/candidate-v2").exists()
    assert not (stage / "02-installed-local.json").exists()
    assert list(stage.glob("install-failed-*.json"))
    assert (root / "artifacts/accepted/current.json").read_bytes() == current
    assert not (root / "artifacts/.promotion.lock").exists()


def test_install_can_resume_after_rename_before_receipt(installation, monkeypatch):
    root, _, _, stage = installation
    original = Path.rename

    def interrupted_after_rename(source, target):
        original(source, target)
        raise OSError("simulated interruption after directory rename")

    with monkeypatch.context() as patch:
        patch.setattr(Path, "rename", interrupted_after_rename)
        with pytest.raises(OSError, match="after directory rename"):
            promote.install_local(root, stage, "state-1", "main-commit")
    assert (root / "artifacts/accepted/candidate-v2/model.joblib").is_file()
    assert not (stage / "02-installed-local.json").exists()
    result = promote.install_local(root, stage, "state-1", "main-commit")
    assert result["status"] == "installed_local_pending_cloud"
    assert promote.check_current(root)["model_version"] == "accepted-v1"


@pytest.mark.parametrize("problem", ["branch", "head", "remote", "dirty", "git-error"])
def test_main_guard_refuses_unverified_checkout(tmp_path, monkeypatch, problem):
    outputs = {
        ("branch", "--show-current"): "main",
        ("rev-parse", "HEAD"): "expected-commit",
        ("rev-parse", "refs/remotes/origin/main"): "expected-commit",
        ("status", "--porcelain"): "",
    }
    key = {
        "branch": ("branch", "--show-current"),
        "head": ("rev-parse", "HEAD"),
        "remote": ("rev-parse", "refs/remotes/origin/main"),
        "dirty": ("status", "--porcelain"),
        "git-error": ("branch", "--show-current"),
    }[problem]
    outputs[key] = "unexpected"

    def git(command, **kwargs):
        return SimpleNamespace(
            returncode=1 if problem == "git-error" else 0,
            stdout=outputs[tuple(command[3:])],
        )

    monkeypatch.setattr(promote.subprocess, "run", git)
    with pytest.raises(ValueError):
        promote.require_main_checkout(tmp_path, "expected-commit")


def test_main_guard_accepts_matching_clean_checkout(tmp_path, monkeypatch):
    outputs = {
        ("branch", "--show-current"): "main",
        ("rev-parse", "HEAD"): "expected-commit",
        ("rev-parse", "refs/remotes/origin/main"): "expected-commit",
        ("status", "--porcelain"): "",
    }
    monkeypatch.setattr(
        promote.subprocess,
        "run",
        lambda command, **kwargs: SimpleNamespace(
            returncode=0, stdout=outputs[tuple(command[3:])]
        ),
    )
    promote.require_main_checkout(tmp_path, "expected-commit")


def test_install_enforces_main_guard_before_any_writes(installation, monkeypatch):
    root, _, _, stage = installation

    def refuse(*args):
        raise ValueError("Installation requires the main branch")

    monkeypatch.setattr(promote, "require_main_checkout", refuse)
    before = snapshot(root)
    with pytest.raises(ValueError, match="main branch"):
        promote.install_local(root, stage, "state-1", "main-commit")
    assert snapshot(root) == before
