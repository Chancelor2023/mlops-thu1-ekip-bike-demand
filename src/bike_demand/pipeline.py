"""Train, reload and evaluate an isolated model candidate."""

import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4

import joblib
import numpy as np
import yaml
from sklearn.metrics import mean_absolute_error

from bike_demand.preflight import check_snapshot, sha256
from bike_demand.split import partition_summary, split_data
from bike_demand.tracking import (
    Tracking,
    timestamp,
    training_commit,
    working_tree_dirty,
    write_json,
)
from bike_demand.train import DEFAULT_MODEL, compare_mean, fit_evaluate
from bike_demand.validate import FEATURES, load_data

EXIT_ELIGIBLE = 0
EXIT_REJECTED = 2
EXIT_BLOCKED = 3

FROZEN_DATA = "data/raw/hour.csv"
CANDIDATE_ROOT = Path("artifacts/candidates")


def load_candidate_config(path: Path) -> dict:
    """Load a candidate config while protecting the frozen data contract."""
    if not path.is_file():
        raise ValueError(f"config: file not found: {path}")

    config = yaml.safe_load(path.read_text(encoding="utf-8"))

    if not isinstance(config, dict) or set(config) != {"data", "features", "model"}:
        raise ValueError("config: require exactly data, features and model")

    if config["data"] != FROZEN_DATA:
        raise ValueError(f"config: data must remain {FROZEN_DATA}")

    if config["features"] != list(FEATURES):
        raise ValueError("config: the 12 contract features and their order are frozen")

    model = config["model"]
    if not isinstance(model, dict) or set(model) != set(DEFAULT_MODEL):
        raise ValueError(f"config: model must contain exactly {sorted(DEFAULT_MODEL)}")

    # Only n_estimators and max_depth may vary between candidates.
    if not isinstance(model["n_estimators"], int) or model["n_estimators"] < 1:
        raise ValueError("config: n_estimators must be a positive integer")

    if model["max_depth"] is not None and (
        not isinstance(model["max_depth"], int) or model["max_depth"] < 1
    ):
        raise ValueError("config: max_depth must be a positive integer or null")

    if model["random_state"] != DEFAULT_MODEL["random_state"]:
        raise ValueError("config: random_state is frozen")

    if model["n_jobs"] != DEFAULT_MODEL["n_jobs"]:
        raise ValueError("config: n_jobs is frozen")

    return config


def validate_predictions(predictions: np.ndarray) -> None:
    """Reject invalid model outputs."""
    if not np.isfinite(predictions).all():
        raise ValueError("predictions: all values must be finite")

    if (predictions < 0).any():
        raise ValueError("predictions: all values must be nonnegative")


def run_pipeline(
    root: Path,
    config_path: Path,
    accepted_dir: Path,
) -> tuple[int, dict]:
    """Execute one isolated candidate evaluation."""
    candidate_version = f"candidate-{uuid4().hex[:12]}"
    candidate_dir = root / CANDIDATE_ROOT / candidate_version
    candidate_dir.mkdir(parents=True, exist_ok=False)

    decision_path = candidate_dir / "decision.json"

    try:
        # Resolve paths relative to the repository root.
        config_path = config_path if config_path.is_absolute() else root / config_path
        accepted_dir = (
            accepted_dir if accepted_dir.is_absolute() else root / accepted_dir
        )

        if not accepted_dir.is_dir():
            raise ValueError(f"accepted model directory does not exist: {accepted_dir}")

        # 1. Validate configuration and frozen dataset.
        config = load_candidate_config(config_path)
        snapshot = check_snapshot(root)

        # 2. Load and split the data.
        frame = load_data(root / config["data"])
        partitions = split_data(frame)

        train = partitions["train"]
        validation = partitions["validation"]

        # The test partition is retained in partition metadata only.
        # It is never used for fitting, evaluation or quality decisions.

        # 3. Calculate the train-mean reference and train the candidate.
        train_mean, naive_mae = compare_mean(
            train["cnt"],
            validation["cnt"],
        )

        model, predictions, candidate_mae = fit_evaluate(
            train,
            validation,
            config,
        )
        validate_predictions(predictions)

        # 4. Save the candidate in its isolated directory.
        model_path = candidate_dir / "model.joblib"
        metadata_path = candidate_dir / "model-metadata.json"
        metrics_path = candidate_dir / "metrics.json"

        joblib.dump(model, model_path)

        # 5. Reload the exact saved artifact and compare predictions.
        reloaded_model = joblib.load(model_path)
        reloaded_predictions = reloaded_model.predict(
            validation.loc[:, config["features"]]
        )
        validate_predictions(reloaded_predictions)

        if not np.array_equal(predictions, reloaded_predictions):
            raise ValueError("reload: saved model predictions differ from fitted model")

        reload_mae = float(mean_absolute_error(validation["cnt"], reloaded_predictions))
        if reload_mae != candidate_mae:
            raise ValueError("reload: validation MAE differs after model reload")

        # 6. Record the complete execution context.
        context = {
            "timestamp": timestamp(),
            "model_version": candidate_version,
            "training_commit": training_commit(root),
            "working_tree_dirty": working_tree_dirty(root),
            "data_sha256": snapshot["sha256"],
            "config_sha256": sha256(config_path),
            "features": config["features"],
            "partitions": partition_summary(partitions),
            "config": config,
            "effective_model_settings": model.get_params(),
        }

        # 7. Log the train-mean reference and candidate in MLflow.
        tracking = Tracking(root)

        naive_run_id = tracking.start_run(
            "candidate_naive_train_mean",
            context,
            {"train_mean": train_mean},
        )
        tracking.finish(naive_run_id, naive_mae, [])

        candidate_run_id = tracking.start_run(
            candidate_version,
            context,
            model.get_params(),
        )

        metadata = {
            **context,
            "model_run_id": candidate_run_id,
            "naive_run_id": naive_run_id,
            "model_sha256": sha256(model_path),
            "validation_mae": {
                "naive_train_mean": naive_mae,
                "random_forest": candidate_mae,
            },
        }

        metrics = {
            "naive_train_mean_validation_mae": naive_mae,
            "candidate_validation_mae": candidate_mae,
            "reload_validation_mae": reload_mae,
            "prediction_max_abs_delta": float(
                np.max(np.abs(predictions - reloaded_predictions))
            ),
        }

        write_json(metadata_path, metadata)
        write_json(metrics_path, metrics)

        tracking.finish(
            candidate_run_id,
            candidate_mae,
            [model_path, metadata_path, metrics_path],
        )

        # 8. Verify that the model artifact did not change after saving.
        if sha256(model_path) != metadata["model_sha256"]:
            raise ValueError("integrity: candidate model checksum changed")

        # 9. Apply Brett's quality gate.
        # The gate implementation and policy are supplied by Brett.
        from bike_demand.gate import evaluate_candidate

        gate_result = evaluate_candidate(
            root=root,
            candidate_dir=candidate_dir,
            accepted_dir=accepted_dir,
            policy_path=root / "configs/gate-policy.yaml",
        )

        if not isinstance(gate_result, dict):
            raise ValueError("gate: expected a dictionary result")

        status = gate_result.get("status")
        if status not in {"eligible", "rejected", "blocked"}:
            raise ValueError(f"gate: invalid status: {status}")

        decision = {
            "model_version": candidate_version,
            "status": status,
            "reasons": gate_result.get("reasons", []),
            "checks": gate_result.get("checks", {}),
            "model_sha256": metadata["model_sha256"],
            "model_run_id": candidate_run_id,
        }
        write_json(decision_path, decision)

        exit_codes = {
            "eligible": EXIT_ELIGIBLE,
            "rejected": EXIT_REJECTED,
            "blocked": EXIT_BLOCKED,
        }
        return exit_codes[status], decision

    except Exception as error:
        # Any incomplete execution is blocked, never eligible.
        decision = {
            "model_version": candidate_version,
            "status": "blocked",
            "reasons": [f"{type(error).__name__}: {error}"],
        }
        write_json(decision_path, decision)
        return EXIT_BLOCKED, decision


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--accepted", type=Path, required=True)
    args = parser.parse_args()

    exit_code, decision = run_pipeline(
        root=Path.cwd(),
        config_path=args.config,
        accepted_dir=args.accepted,
    )

    print(json.dumps(decision, indent=2))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
