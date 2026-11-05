"""Check, stage or install versioned model bytes; never switch serving state."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

EXIT_BLOCKED = 3
BUNDLE_FILES = ("model.joblib", "model-metadata.json")
EVALUATED_FILES = (*BUNDLE_FILES, "metrics.json")
REQUIRED_CHECKS = {"quality", "operation", "integrity"}


def read_object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path.name}")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inside(path: Path, parent: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(parent.resolve()) or resolved == parent.resolve():
        raise ValueError(f"Path must be inside {parent}: {path}")
    return resolved


def verify_files(directory: Path, checksums: dict, names: tuple[str, ...]) -> None:
    if not isinstance(checksums, dict):
        raise ValueError("Missing file checksums")
    for name in names:
        path = directory / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Missing regular bundle file: {name}")
        if sha256(path) != checksums.get(name):
            raise ValueError(f"Checksum mismatch: {name}")


def check_current(root: Path) -> dict:
    current = read_object(root / "artifacts/accepted/current.json")
    for name in ("state_id", "model_version", "bundle_path"):
        if not isinstance(current.get(name), str) or not current[name]:
            raise ValueError(f"Missing accepted state field: {name}")
    directory = inside(root / current["bundle_path"], root / "artifacts/accepted")
    verify_files(directory, current.get("checksums"), BUNDLE_FILES)
    metadata = read_object(directory / "model-metadata.json")
    if metadata.get("model_version") != current["model_version"]:
        raise ValueError("Accepted model version mismatch")
    if metadata.get("model_sha256") != current["checksums"]["model.joblib"]:
        raise ValueError("Accepted metadata model checksum mismatch")
    return current


def preflight(root: Path, candidate: Path, policy: Path) -> dict:
    """Check the proposed gate interface, without loading joblib or writing state."""
    root = root.resolve()
    current_path = root / "artifacts/accepted/current.json"
    state_digest = sha256(current_path)
    current = check_current(root)
    candidate = inside(root / candidate, root / "artifacts/candidates")
    policy = inside(root / policy, root / "configs")
    decision = read_object(candidate / "decision.json")

    if decision.get("status") != "eligible":
        raise ValueError("Only an eligible candidate can pass promotion preflight")
    checks = decision.get("checks")
    if not isinstance(checks, dict) or not REQUIRED_CHECKS.issubset(checks):
        raise ValueError("Missing mandatory gate checks: quality, operation, integrity")
    for name, check in checks.items():
        if not isinstance(check, dict) or check.get("passed") is not True:
            raise ValueError(f"Gate check not passed: {name}")

    reference = decision.get("accepted_reference")
    expected = {key: current[key] for key in ("state_id", "model_version", "checksums")}
    if reference != expected:
        raise ValueError("Gate evaluated a different accepted state; reevaluate")
    if decision.get("policy_sha256") != sha256(policy):
        raise ValueError("Gate policy missing or changed since evaluation")

    evidence = decision.get("evidence_sha256")
    verify_files(candidate, evidence, EVALUATED_FILES)
    metadata = read_object(candidate / "model-metadata.json")
    version = metadata.get("model_version")
    if not isinstance(version, str) or not version or version != candidate.name:
        raise ValueError("Candidate directory and model version must match")
    if decision.get("model_version") != version:
        raise ValueError("Decision and candidate version mismatch")
    if version == current["model_version"]:
        raise ValueError("Candidate must have a new model version")
    if metadata.get("model_sha256") != evidence["model.joblib"]:
        raise ValueError("Candidate metadata model checksum mismatch")
    if decision.get("model_sha256") != evidence["model.joblib"]:
        raise ValueError("Decision model checksum mismatch")
    if not metadata.get("model_run_id") or (
        decision.get("model_run_id") != metadata["model_run_id"]
    ):
        raise ValueError("Decision and candidate MLflow run mismatch")
    if sha256(current_path) != state_digest:
        raise ValueError("Accepted state changed during preflight; retry")
    check_current(root)
    return {
        "status": "preflight_passed",
        "dry_run": True,
        "model_version": version,
        "expected_state_id": current["state_id"],
        "accepted_model_version": current["model_version"],
        "policy_sha256": decision["policy_sha256"],
        "evidence_sha256": evidence,
        "promoted": False,
        "deployed": False,
    }


def write_new_json(path: Path, value: dict) -> None:
    """Create a new record, refusing to overwrite existing evidence."""
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


@contextmanager
def promotion_lock(root: Path):
    """Exclusive lock for cooperating processes sharing this local artifacts dir."""
    path = root / "artifacts/.promotion.lock"
    token = uuid4().hex
    try:
        stream = path.open("x", encoding="utf-8")
    except FileExistsError as error:
        raise ValueError("Promotion lock already exists; operation blocked") from error
    try:
        with stream:
            json.dump({"token": token, "pid": os.getpid()}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        yield
    finally:
        # Never remove another process's replacement lock.
        if read_object(path).get("token") == token:
            path.unlink()


def prepare_promotion(
    root: Path, candidate: Path, policy: Path, expected_state_id: str
) -> dict:
    """Stage verified bytes and a journal, without changing accepted state."""
    root = root.resolve()
    with promotion_lock(root):
        current_path = root / "artifacts/accepted/current.json"
        current_digest = sha256(current_path)
        current = check_current(root)
        if current["state_id"] != expected_state_id:
            raise ValueError("Expected accepted state changed; reevaluate")
        candidate = inside(root / candidate, root / "artifacts/candidates")
        policy = inside(root / policy, root / "configs")
        decision_digest = sha256(candidate / "decision.json")
        checked = preflight(root, candidate, policy)
        if sha256(candidate / "decision.json") != decision_digest:
            raise ValueError("Decision changed during preflight")

        operation_id = f"promotion-{uuid4().hex}"
        stage = root / "artifacts/promotions" / operation_id
        stage.mkdir(parents=True, exist_ok=False)
        started = {
            "operation_id": operation_id,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "status": "started",
            "expected_state_id": expected_state_id,
            "accepted_state_sha256": current_digest,
            "previous_accepted": current,
            "model_version": checked["model_version"],
            "evidence_sha256": checked["evidence_sha256"],
            "policy_sha256": checked["policy_sha256"],
            "decision_sha256": decision_digest,
            "candidate_path": candidate.relative_to(root).as_posix(),
            "policy_path": policy.relative_to(root).as_posix(),
            "promoted": False,
            "deployed": False,
        }
        write_new_json(stage / "00-started.json", started)
        try:
            bundle = stage / "bundle"
            bundle.mkdir()
            for name in (*EVALUATED_FILES, "decision.json"):
                shutil.copyfile(candidate / name, bundle / name)
            shutil.copyfile(policy, stage / "gate-policy.yaml")
            verify_files(bundle, checked["evidence_sha256"], EVALUATED_FILES)
            if sha256(bundle / "decision.json") != decision_digest:
                raise ValueError("Decision changed while staging")
            if sha256(stage / "gate-policy.yaml") != checked["policy_sha256"]:
                raise ValueError("Policy changed while staging")
            # Recheck source evidence and accepted state before publishing readiness.
            final_check = preflight(root, candidate, policy)
            if final_check != checked or sha256(current_path) != current_digest:
                raise ValueError("Inputs changed while staging; operation blocked")
            if sha256(candidate / "decision.json") != decision_digest:
                raise ValueError("Decision changed while staging")
            prepared = {
                **started,
                "status": "prepared",
                "prepared_at": datetime.now(timezone.utc).isoformat(),
                "staging_path": stage.relative_to(root).as_posix(),
            }
            write_new_json(stage / "01-prepared.json", prepared)
            return prepared
        except (Exception, KeyboardInterrupt) as error:
            write_new_json(
                stage / "99-blocked.json",
                {
                    **started,
                    "status": "blocked",
                    "reasons": [f"{type(error).__name__}: {error}"],
                },
            )
            raise


def require_main_checkout(root: Path, expected_revision: str) -> None:
    """Check local main/remote refs; GitHub review and ref freshness are external."""

    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise ValueError("Cannot verify the main checkout")
        return result.stdout.strip()

    if git("branch", "--show-current") != "main":
        raise ValueError("Installation requires the main branch")
    if not expected_revision or git("rev-parse", "HEAD") != expected_revision:
        raise ValueError("Checkout does not match the expected revision")
    if git("rev-parse", "refs/remotes/origin/main") != expected_revision:
        raise ValueError("Checkout does not match origin/main; fetch and review first")
    if git("status", "--porcelain"):
        raise ValueError("Installation requires a clean working tree")


def verify_prepared(root: Path, stage: Path, expected_state_id: str) -> dict:
    """Revalidate journal, source and staged bytes before installation."""
    started = read_object(stage / "00-started.json")
    ready = read_object(stage / "01-prepared.json")
    if ready.get("status") != "prepared" or (stage / "99-blocked.json").exists():
        raise ValueError("Operation was not completely prepared")
    if ready.get("operation_id") != stage.name:
        raise ValueError("Operation identity does not match its directory")
    if any(
        ready.get(key) != value for key, value in started.items() if key != "status"
    ):
        raise ValueError("Prepared journal does not match the started record")
    current = check_current(root)
    if (
        current["state_id"] != expected_state_id
        or ready.get("expected_state_id") != expected_state_id
    ):
        raise ValueError("Expected accepted state changed; reevaluate")
    if ready.get("accepted_state_sha256") != sha256(
        root / "artifacts/accepted/current.json"
    ):
        raise ValueError("Accepted manifest changed since preparation")
    checked = preflight(root, Path(ready["candidate_path"]), Path(ready["policy_path"]))
    for name in ("model_version", "evidence_sha256", "policy_sha256"):
        if ready.get(name) != checked[name]:
            raise ValueError(f"Prepared evidence changed: {name}")
    verify_files(stage / "bundle", ready["evidence_sha256"], EVALUATED_FILES)
    source = root / ready["candidate_path"]
    if (
        sha256(stage / "bundle/decision.json") != ready["decision_sha256"]
        or sha256(source / "decision.json") != ready["decision_sha256"]
    ):
        raise ValueError("Decision changed since preparation")
    if sha256(stage / "gate-policy.yaml") != ready["policy_sha256"]:
        raise ValueError("Staged policy changed since preparation")
    return ready


def verify_installed(directory: Path, ready: dict) -> None:
    verify_files(directory, ready["evidence_sha256"], EVALUATED_FILES)
    if sha256(directory / "decision.json") != ready["decision_sha256"]:
        raise ValueError("Installed decision checksum mismatch")
    origin = read_object(directory / "installation-origin.json")
    if origin != {
        "operation_id": ready["operation_id"],
        "decision_sha256": ready["decision_sha256"],
    }:
        raise ValueError("Existing version belongs to another installation")


def install_local(
    root: Path, operation: Path, expected_state_id: str, expected_revision: str
) -> dict:
    """Install a complete versioned bundle; current.json stays on the served model."""
    root = root.resolve()
    require_main_checkout(root, expected_revision)
    stage = inside(root / operation, root / "artifacts/promotions")
    with promotion_lock(root):
        require_main_checkout(root, expected_revision)
        ready = verify_prepared(root, stage, expected_state_id)
        destination = root / "artifacts/accepted" / ready["model_version"]
        inside(destination, root / "artifacts/accepted")
        receipt_path = stage / "02-installed-local.json"
        try:
            if destination.is_symlink():
                raise ValueError("Installation destination must not be a symlink")
            if not destination.exists():
                # A private sibling keeps incomplete copies outside the final version.
                temporary = destination.parent / f".install-{uuid4().hex}"
                temporary.mkdir(exist_ok=False)
                for name in (*EVALUATED_FILES, "decision.json"):
                    shutil.copyfile(stage / "bundle" / name, temporary / name)
                write_new_json(
                    temporary / "installation-origin.json",
                    {
                        "operation_id": ready["operation_id"],
                        "decision_sha256": ready["decision_sha256"],
                    },
                )
                verify_installed(temporary, ready)
                verify_prepared(root, stage, expected_state_id)
                require_main_checkout(root, expected_revision)
                # All cooperating writers must hold this same local lock.
                temporary.rename(destination)
            verify_installed(destination, ready)
            verify_prepared(root, stage, expected_state_id)
            require_main_checkout(root, expected_revision)
            receipt = {
                "operation_id": ready["operation_id"],
                "status": "installed_local_pending_cloud",
                "installed_bundle_path": destination.relative_to(root).as_posix(),
                "model_version": ready["model_version"],
                "expected_state_id": expected_state_id,
                "installation_code_revision": expected_revision,
                "evidence_sha256": ready["evidence_sha256"],
                "current_manifest_updated": False,
                "promoted": False,
                "deployed": False,
            }
            if receipt_path.exists():
                if read_object(receipt_path) != receipt:
                    raise ValueError("Existing installation receipt differs")
            else:
                write_new_json(receipt_path, receipt)
            return receipt
        except (Exception, KeyboardInterrupt) as error:
            write_new_json(
                stage / f"install-failed-{uuid4().hex}.json",
                {
                    "status": "installation_blocked",
                    "operation_id": ready["operation_id"],
                    "reasons": [f"{type(error).__name__}: {error}"],
                    "current_manifest_updated": False,
                    "deployed": False,
                },
            )
            raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--policy", type=Path, default=Path("configs/gate-policy.yaml"))
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--install-local", action="store_true")
    parser.add_argument("--operation", type=Path, help="Prepared operation directory")
    parser.add_argument(
        "--expected-revision", help="Full main commit SHA for installation"
    )
    parser.add_argument(
        "--expected-state", help="Required with --prepare/--install-local"
    )
    args = parser.parse_args()
    if (args.prepare or args.install_local) and not args.expected_state:
        parser.error("--prepare/--install-local requires --expected-state")
    if args.install_local:
        if not args.operation or not args.expected_revision:
            parser.error("--install-local requires --operation and --expected-revision")
        if args.candidate:
            parser.error("--install-local uses --operation, not --candidate")
    elif not args.candidate:
        parser.error("--dry-run/--prepare requires --candidate")
    try:
        if args.install_local:
            result = install_local(
                Path.cwd(), args.operation, args.expected_state, args.expected_revision
            )
        elif args.prepare:
            result = prepare_promotion(
                Path.cwd(), args.candidate, args.policy, args.expected_state
            )
        else:
            result = preflight(Path.cwd(), args.candidate, args.policy)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(
            json.dumps(
                {"status": "blocked", "dry_run": args.dry_run, "reasons": [str(error)]}
            )
        )
        return EXIT_BLOCKED
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
