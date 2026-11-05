"""Read-only promotion preflight. No local promotion or deployment is implemented yet."""

import argparse
import hashlib
import json
from pathlib import Path

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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--policy", type=Path, default=Path("configs/gate-policy.yaml"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.dry_run:
        parser.error("Only --dry-run is implemented; no promotion is performed")
    try:
        result = preflight(Path.cwd(), args.candidate, args.policy)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(
            json.dumps({"status": "blocked", "dry_run": True, "reasons": [str(error)]})
        )
        return EXIT_BLOCKED
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
