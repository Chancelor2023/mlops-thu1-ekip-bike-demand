"""Fail-closed quality gate for isolated bike-demand model candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import yaml
from sklearn.metrics import mean_absolute_error

FEATURES = [
    "season",
    "yr",
    "mnth",
    "hr",
    "holiday",
    "weekday",
    "workingday",
    "weathersit",
    "temp",
    "atemp",
    "hum",
    "windspeed",
]
EXIT_CODES = {"eligible": 0, "rejected": 2, "blocked": 3}


def sha256(path: Path) -> str:
    """Return a file's SHA-256 digest."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _result(status: str, details: Any = None) -> dict:
    return {"status": status, "details": details}


def _run(checks: dict, name: str, operation: Callable[[], tuple[str, Any]]) -> Any:
    """Run one check, converting all exceptions into not_evaluated."""
    try:
        status, details = operation()
        if status not in {"pass", "fail", "not_evaluated"}:
            raise ValueError(f"invalid check status: {status}")
        checks[name] = _result(status, details)
        return details if status == "pass" else None
    except Exception as exc:  # noqa: BLE001  # Fail closed on every control exception.
        checks[name] = _result("not_evaluated", f"{type(exc).__name__}: {exc}")
        return None


def _read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def _dataset_manifest(root: Path, data_path: Path, policy: dict) -> tuple[str, str]:
    configured = policy.get("manifest_path")
    candidates = (
        [root / configured]
        if configured
        else [
            data_path.with_suffix(data_path.suffix + ".sha256"),
            data_path.parent / "manifest.json",
            root / "data" / "manifest.json",
        ]
    )
    for path in candidates:
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8").strip()
        if path.suffix.lower() == ".json":
            obj = json.loads(content)
            expected = obj.get("sha256") or obj.get("data_sha256")
            if isinstance(obj.get(data_path.name), dict):
                expected = obj[data_path.name].get("sha256", expected)
            elif isinstance(obj.get(data_path.name), str):
                expected = obj[data_path.name]
        else:
            expected = content.split()[0] if content else None
        if expected:
            return str(expected), str(path)
    raise FileNotFoundError("dataset checksum manifest not found or has no sha256")


def _default_latency_measure(
    model: Any, features: Any, *, warmup: int, requests: int, repeats: int
) -> dict:
    """Measure sequential model.predict latency locally (no remote service)."""
    if len(features) == 0:
        raise ValueError("cannot measure latency on empty validation data")
    sample = features.iloc[[0]] if hasattr(features, "iloc") else features[:1]
    for _ in range(warmup):
        model.predict(sample)
    p95s = []
    for _ in range(repeats):
        durations = []
        for _ in range(requests):
            started = time.perf_counter()
            model.predict(sample)
            durations.append((time.perf_counter() - started) * 1000)
        p95s.append(float(np.percentile(durations, 95)))
    return {"p95_ms": float(statistics.median(p95s)), "repeat_p95_ms": p95s}


def evaluate_candidate(
    root: Path,
    candidate_dir: Path,
    accepted_dir: Path,
    policy_path: Path,
    latency_measure: Callable[..., Any] | None = None,
    accepted_state: dict | None = None,
) -> dict:
    """Evaluate a candidate without mutating accepted artifacts.

    The optional callable accepts ``(model, validation_features, warmup=...,
    requests=..., repeats=...)`` and returns a number (p95 milliseconds) or a
    mapping containing ``p95_ms``. Passing ``None`` uses an in-process local
    measurement; no Cloud Run or external service is contacted. Pipeline callers
    supply accepted_state captured before training to bind promotion evidence.
    Without it, a standalone evaluation cannot authorize promotion.
    """
    root, candidate_dir, accepted_dir, policy_path = map(
        Path, (root, candidate_dir, accepted_dir, policy_path)
    )
    checks: dict[str, dict] = {}
    reasons: list[str] = []
    policy_hash: str | None = None
    policy: dict = {}
    try:
        if not policy_path.is_file():
            raise FileNotFoundError(f"policy not found: {policy_path}")
        policy_hash = sha256(policy_path)
        policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
        if not isinstance(policy, dict):
            raise TypeError("policy must be a YAML mapping")
        thresholds = policy.get("quality", {})
        epsilon = float(thresholds.get("epsilon", 1e-6))
        if epsilon != 1e-6:
            raise ValueError("policy epsilon is frozen at 1e-6")
    except Exception as exc:  # noqa: BLE001  # Invalid policy must block.
        checks["policy"] = _result("not_evaluated", f"{type(exc).__name__}: {exc}")
        decision = {
            "status": "blocked",
            "reasons": ["policy unavailable or invalid"],
            "checks": checks,
            "policy_sha256": policy_hash,
        }
        _write_decision(candidate_dir, decision)
        return decision
    checks["policy"] = _result("pass", {"sha256": policy_hash})

    candidate_model_path = candidate_dir / "model.joblib"
    candidate_metadata_path = candidate_dir / "model-metadata.json"
    candidate_metrics_path = candidate_dir / "metrics.json"
    accepted_model_path = accepted_dir / "model.joblib"
    accepted_metadata_path = accepted_dir / "model-metadata.json"
    accepted_metrics_path = accepted_dir / "metrics.json"
    if not accepted_metrics_path.is_file():
        accepted_metrics_path = (
            accepted_dir / "reference-evidence/validation-reevaluation.json"
        )
    evidence_paths = {
        "model.joblib": candidate_model_path,
        "model-metadata.json": candidate_metadata_path,
        "metrics.json": candidate_metrics_path,
    }
    evidence_before = {
        name: sha256(path) for name, path in evidence_paths.items() if path.is_file()
    }
    accepted_reference = None

    def reference_check() -> tuple[str, Any]:
        nonlocal accepted_reference
        current = _read_json(root / "artifacts/accepted/current.json")
        if current != accepted_state:
            return "fail", "accepted state changed since pipeline start"
        if not current.get("state_id") or not current.get("model_version"):
            return "fail", "accepted state identity missing"
        if (root / current["bundle_path"]).resolve() != accepted_dir.resolve():
            return "fail", "accepted directory is not the current reference"
        checksums = current.get("checksums", {})
        for name in ("model.joblib", "model-metadata.json"):
            if sha256(accepted_dir / name) != checksums.get(name):
                return "fail", f"accepted reference checksum mismatch: {name}"
        meta = _read_json(accepted_metadata_path)
        if meta.get("model_version") != current["model_version"]:
            return "fail", "accepted reference model version mismatch"
        accepted_reference = {
            key: current[key] for key in ("state_id", "model_version", "checksums")
        }
        return "pass", accepted_reference

    if accepted_state is not None:
        _run(checks, "accepted_reference", reference_check)
    candidate_meta: dict | None = None
    accepted_meta: dict | None = None
    candidate_metrics: dict | None = None
    accepted_metrics: dict | None = None
    candidate_model = accepted_model = None
    frame = partitions = train = validation = None

    def artifact_check() -> tuple[str, Any]:
        absent = [
            str(path)
            for path in (
                candidate_model_path,
                candidate_metadata_path,
                candidate_metrics_path,
            )
            if not path.is_file()
        ]
        if absent:
            return "fail", {"missing": absent}
        return "pass", "candidate model, metadata and metrics exist"

    _run(checks, "candidate_artifacts", artifact_check)

    def accepted_evidence_check() -> tuple[str, Any]:
        absent = [
            str(path)
            for path in (
                accepted_model_path,
                accepted_metadata_path,
                accepted_metrics_path,
            )
            if not path.is_file()
        ]
        if absent:
            return "fail", {"missing": absent}
        return "pass", "accepted model, metadata and metrics exist"

    _run(checks, "accepted_evidence", accepted_evidence_check)

    def load_data_split() -> tuple[str, Any]:
        nonlocal frame, partitions, train, validation
        meta = _read_json(candidate_metadata_path)
        data_rel = meta.get("config", {}).get("data", "data/raw/hour.csv")
        data_path = root / data_rel
        if not data_path.is_file():
            raise FileNotFoundError(f"dataset not found: {data_path}")
        manifest_hash, manifest_path = _dataset_manifest(root, data_path, policy)
        actual_hash = sha256(data_path)
        if actual_hash != manifest_hash or meta.get("data_sha256") != actual_hash:
            return "fail", {
                "dataset_sha256": actual_hash,
                "manifest_sha256": manifest_hash,
                "metadata_sha256": meta.get("data_sha256"),
                "manifest": manifest_path,
            }
        from bike_demand.split import split_data
        from bike_demand.validate import load_data

        frame = load_data(data_path)
        partitions = split_data(frame)
        train, validation = partitions["train"], partitions["validation"]
        if validation.empty or train.empty:
            raise ValueError("train/validation split must be non-empty")
        return "pass", {
            "sha256": actual_hash,
            "manifest": manifest_path,
            "validation_rows": len(validation),
        }

    _run(checks, "dataset_checksum_and_split", load_data_split)

    def metadata_check() -> tuple[str, Any]:
        nonlocal candidate_meta, accepted_meta, candidate_metrics, accepted_metrics
        candidate_meta = _read_json(candidate_metadata_path)
        accepted_meta = _read_json(accepted_metadata_path)
        candidate_metrics = _read_json(candidate_metrics_path)
        accepted_metrics = _read_json(accepted_metrics_path)
        for label, meta, metrics in (
            ("candidate", candidate_meta, candidate_metrics),
            ("accepted", accepted_meta, accepted_metrics),
        ):
            if meta.get("features") != FEATURES:
                return (
                    "fail",
                    f"{label} metadata features differ from the ordered contract",
                )
            if (
                not isinstance(meta.get("model_sha256"), str)
                or not meta["model_sha256"]
            ):
                return "fail", f"{label} metadata lacks model_sha256"
            if not isinstance(metrics, dict):
                return "fail", f"{label} metrics must be an object"
        candidate_mae = candidate_metrics.get("candidate_validation_mae")
        metadata_mae = candidate_meta.get("validation_mae", {}).get("random_forest")
        if (
            not _finite_number(candidate_mae)
            or not _finite_number(metadata_mae)
            or not math.isclose(
                float(candidate_mae), float(metadata_mae), rel_tol=0.0, abs_tol=1e-12
            )
        ):
            return "fail", "candidate metrics and metadata validation MAE disagree"
        if accepted_meta.get("data_sha256") != candidate_meta.get("data_sha256"):
            return "fail", "candidate and accepted refer to different dataset snapshots"
        return "pass", "metadata/metrics schema and candidate MAE agree"

    _run(checks, "metadata_consistency", metadata_check)

    def features_check() -> tuple[str, Any]:
        if candidate_meta is None or accepted_meta is None:
            raise ValueError("metadata unavailable")
        for label, meta in (("candidate", candidate_meta), ("accepted", accepted_meta)):
            if meta.get("features") != FEATURES:
                return "fail", f"{label} features missing, renamed, or reordered"
        if validation is not None and not all(
            feature in validation.columns for feature in FEATURES
        ):
            return "fail", "validation frame lacks contract features"
        return "pass", FEATURES

    _run(checks, "feature_contract", features_check)

    def model_load() -> tuple[str, Any]:
        nonlocal candidate_model, accepted_model
        candidate_model = joblib.load(candidate_model_path)
        accepted_model = joblib.load(accepted_model_path)
        return "pass", "candidate and accepted joblib artifacts reloaded"

    _run(checks, "model_reload", model_load)

    def model_hashes() -> tuple[str, Any]:
        if candidate_meta is None or accepted_meta is None:
            raise ValueError("model metadata unavailable")
        actual_candidate, actual_accepted = (
            sha256(candidate_model_path),
            sha256(accepted_model_path),
        )
        if actual_candidate != candidate_meta.get("model_sha256"):
            return "fail", {
                "candidate_expected": candidate_meta.get("model_sha256"),
                "candidate_actual": actual_candidate,
            }
        if actual_accepted != accepted_meta.get("model_sha256"):
            return "fail", {
                "accepted_expected": accepted_meta.get("model_sha256"),
                "accepted_actual": actual_accepted,
            }
        return "pass", {"candidate": actual_candidate, "accepted": actual_accepted}

    _run(checks, "model_sha256", model_hashes)

    def prediction_check() -> tuple[str, Any]:
        if candidate_model is None or accepted_model is None or validation is None:
            raise ValueError("reloaded models or validation data unavailable")
        features = validation.loc[:, FEATURES]
        candidate_predictions = np.asarray(
            candidate_model.predict(features), dtype=float
        )
        accepted_predictions = np.asarray(accepted_model.predict(features), dtype=float)
        for label, values in (
            ("candidate", candidate_predictions),
            ("accepted", accepted_predictions),
        ):
            if values.shape != (len(validation),):
                return "fail", f"{label} prediction shape invalid: {values.shape}"
            if not np.isfinite(values).all() or (values < 0).any():
                return "fail", f"{label} predictions must be finite and nonnegative"
        return "pass", {
            "candidate_predictions": candidate_predictions.tolist(),
            "accepted_predictions": accepted_predictions.tolist(),
        }

    predictions = _run(checks, "predictions", prediction_check)

    def quality_check() -> tuple[str, Any]:
        if predictions is None or train is None or validation is None:
            raise ValueError("predictions/split unavailable")
        y = np.asarray(validation["cnt"], dtype=float)
        candidate_mae = float(
            mean_absolute_error(y, predictions["candidate_predictions"])
        )
        accepted_mae = float(
            mean_absolute_error(y, predictions["accepted_predictions"])
        )
        train_mean = float(train["cnt"].mean())
        baseline_mae = float(mean_absolute_error(y, np.full(len(y), train_mean)))
        epsilon_value = float(policy["quality"]["epsilon"])
        baseline_ok = candidate_mae < baseline_mae
        accepted_ok = candidate_mae <= accepted_mae + epsilon_value
        details = {
            "candidate_validation_mae": candidate_mae,
            "accepted_validation_mae": accepted_mae,
            "train_mean_validation_mae": baseline_mae,
            "candidate_beats_train_mean": baseline_ok,
            "candidate_within_accepted_epsilon": accepted_ok,
            "epsilon": epsilon_value,
        }
        if not baseline_ok or not accepted_ok:
            return "fail", details
        if abs(candidate_mae - accepted_mae) <= epsilon_value:
            details["accepted_comparison"] = (
                "equivalent within epsilon; not claimed as an improvement"
            )
        else:
            details["accepted_comparison"] = "candidate is better than accepted"
        return "pass", details

    _run(checks, "quality", quality_check)

    def performance_check() -> tuple[str, Any]:
        if candidate_model is None or accepted_model is None or validation is None:
            raise ValueError("models or validation data unavailable")
        perf_cfg = policy.get("performance", {})
        warmup, requests, repeats = (
            int(perf_cfg.get(key, default))
            for key, default in (("warmup", 20), ("requests", 100), ("repeats", 3))
        )
        if (warmup, requests, repeats) != (20, 100, 3):
            raise ValueError("performance protocol is frozen at 20/100/3")
        measure = latency_measure or _default_latency_measure
        features = validation.loc[:, FEATURES]

        def run(model: Any) -> float:
            value = measure(
                model, features, warmup=warmup, requests=requests, repeats=repeats
            )
            if isinstance(value, dict):
                value = value.get("p95_ms")
            value = float(value)
            if not math.isfinite(value) or value < 0:
                raise ValueError("latency must be finite and nonnegative")
            return value

        candidate_latency, accepted_latency = run(candidate_model), run(accepted_model)
        ratio = float(perf_cfg.get("max_ratio", 1.25))
        passed = candidate_latency <= ratio * accepted_latency
        details = {
            "candidate_p95_ms": candidate_latency,
            "accepted_p95_ms": accepted_latency,
            "max_ratio": ratio,
            "candidate_to_accepted_ratio": candidate_latency / accepted_latency
            if accepted_latency
            else None,
            "protocol": {"warmup": warmup, "requests": requests, "repeats": repeats},
        }
        if not passed:
            return "fail", details
        return "pass", details

    _run(checks, "performance", performance_check)

    def evaluation_integrity() -> tuple[str, Any]:
        if set(evidence_before) != set(evidence_paths):
            return "fail", "candidate evidence was incomplete at evaluation start"
        if any(
            sha256(path) != evidence_before[name]
            for name, path in evidence_paths.items()
        ):
            return "fail", "candidate files changed during evaluation"
        if sha256(policy_path) != policy_hash:
            return "fail", "policy changed during evaluation"
        if accepted_state is not None:
            status, details = reference_check()
            if status != "pass":
                return status, details
        return "pass", "evaluated bytes, policy and reference unchanged"

    _run(checks, "evaluation_integrity", evaluation_integrity)

    failed = [name for name, check in checks.items() if check["status"] == "fail"]
    unevaluated = [
        name for name, check in checks.items() if check["status"] == "not_evaluated"
    ]
    integrity_checks = {
        "candidate_artifacts",
        "accepted_evidence",
        "dataset_checksum_and_split",
        "metadata_consistency",
        "feature_contract",
        "model_reload",
        "model_sha256",
        "predictions",
        "accepted_reference",
        "evaluation_integrity",
    }
    blocking_failures = [name for name in failed if name in integrity_checks]
    rejected_checks = [name for name in failed if name not in integrity_checks]
    if unevaluated or blocking_failures:
        status = "blocked"
        reasons.extend(f"{name}: not_evaluated" for name in unevaluated)
        reasons.extend(
            f"{name}: integrity/evidence failure" for name in blocking_failures
        )
    elif rejected_checks:
        status = "rejected"
        reasons.extend(f"{name}: failed" for name in rejected_checks)
    else:
        status = "eligible"
        reasons.append("all quality-gate checks passed; no promotion performed")
    decision = {
        "status": status,
        "reasons": reasons,
        "checks": checks,
        "policy_sha256": policy_hash,
        "evidence_sha256": evidence_before,
        "promotion_evidence_complete": accepted_reference is not None,
    }
    if accepted_reference is not None:
        decision["accepted_reference"] = accepted_reference
    _write_decision(candidate_dir, decision)
    return decision


def _finite_number(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _write_decision(candidate_dir: Path, decision: dict) -> None:
    try:
        candidate_dir.mkdir(parents=True, exist_ok=True)
        (candidate_dir / "decision.json").write_text(
            json.dumps(decision, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
    except Exception as exc:  # noqa: BLE001  # Report failure to persist.
        # A failed decision write is reflected in the returned result as blocked.
        decision["status"] = "blocked"
        decision.setdefault("reasons", []).append(
            f"decision.json write failed: {type(exc).__name__}: {exc}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--accepted", type=Path, required=True)
    parser.add_argument("--policy", type=Path, default=Path("configs/gate-policy.yaml"))
    args = parser.parse_args()
    root = args.root.resolve()
    candidate = (
        args.candidate if args.candidate.is_absolute() else root / args.candidate
    )
    accepted = args.accepted if args.accepted.is_absolute() else root / args.accepted
    policy = args.policy if args.policy.is_absolute() else root / args.policy
    result = evaluate_candidate(root, candidate, accepted, policy)
    print(json.dumps(result, indent=2))
    return EXIT_CODES[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
