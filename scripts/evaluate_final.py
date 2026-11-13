"""Inspect the frozen final selection; score held test only with explicit opt-in."""

import argparse
import hashlib
import io
import json
import platform
import subprocess
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.exceptions import InconsistentVersionWarning
from sklearn.metrics import mean_absolute_error

from bike_demand.preflight import check_snapshot
from bike_demand.split import split_data
from bike_demand.validate import FEATURES, load_data


def digest(content):
    return hashlib.sha256(content).hexdigest()


def save(path, value):
    path.write_bytes((json.dumps(value, indent=2, allow_nan=False) + "\n").encode())


def prepare(root):
    root = root.resolve()
    selection_path = root / "reports/final-model-selection.json"
    selection_bytes = selection_path.read_bytes()
    selection = json.loads(selection_bytes)
    if (
        selection["features"] != list(FEATURES)
        or selection["target"] != "cnt"
        or selection["metric"] != "mean_absolute_error"
        or selection["test_period"]["start"] != "2012-07-01"
        or selection["test_period"]["end"] != "2012-12-31"
        or selection["data_path"] != "data/raw/hour.csv"
        or selection["selection_basis"]["held_test_used_for_selection"] is not False
    ):
        raise ValueError("Selection violates the frozen evaluation contract")
    bundle = (root / selection["bundle_path"]).resolve()
    if not bundle.is_relative_to(root / "artifacts/accepted"):
        raise ValueError("Bundle must be inside artifacts/accepted")
    contents = {}
    paths = {}
    for name in ("model.joblib", "model-metadata.json"):
        path = bundle / name
        contents[name] = path.read_bytes()
        if digest(contents[name]) != selection["checksums"][name]:
            raise ValueError(f"Frozen checksum mismatch: {name}")
        paths[path] = selection["checksums"][name]
    metadata = json.loads(contents["model-metadata.json"])
    if (
        metadata["model_version"] != selection["model_version"]
        or metadata["model_sha256"] != selection["checksums"]["model.joblib"]
        or metadata["data_sha256"] != selection["data_sha256"]
        or metadata["features"] != selection["features"]
        or metadata["config"]["model"] != selection["model_parameters"]
    ):
        raise ValueError("Model metadata differs from the final selection")
    manifest = check_snapshot(root)
    if manifest["sha256"] != selection["data_sha256"]:
        raise ValueError("Dataset differs from the final selection")
    for name, expected in (
        (selection["config_path"], selection["config_sha256"]),
        ("uv.lock", selection["uv_lock_sha256"]),
        (selection["data_path"], selection["data_sha256"]),
    ):
        path = root / name
        if digest(path.read_bytes()) != expected:
            raise ValueError(f"Frozen checksum mismatch: {name}")
        paths[path] = expected
    paths[selection_path] = digest(selection_bytes)
    partitions = split_data(load_data(root / selection["data_path"]))
    test = partitions["test"]
    if len(test) != selection["test_period"]["rows"]:
        raise ValueError("Unexpected held-test population")
    return selection, contents, test, paths


def evaluate(root, *, execute=False, revision="not_recorded"):
    root = root.resolve()
    selection, contents, test, paths = prepare(root)
    plan = {
        "status": "ready_not_evaluated",
        "model_version": selection["model_version"],
        "model_sha256": selection["checksums"]["model.joblib"],
        "test_period": selection["test_period"],
        "metric": selection["metric"],
        "retraining_performed": False,
        "held_test_scored": False,
    }
    if not execute:
        return plan
    output = root / "reports/final-evaluation"
    # Exclusive directory also retains incomplete attempts. Never delete to rerun.
    output.mkdir()
    save(
        output / "started.json",
        {**plan, "started_at": datetime.now(timezone.utc).isoformat()},
    )
    try:
        # Only deserialize the exact trusted accepted bytes whose hash was checked.
        with warnings.catch_warnings():
            warnings.simplefilter("error", InconsistentVersionWarning)
            model = joblib.load(io.BytesIO(contents["model.joblib"]))
        if list(model.feature_names_in_) != selection["features"]:
            raise ValueError("Serialized model feature order differs")
        if any(
            model.get_params()[key] != value
            for key, value in selection["model_parameters"].items()
        ):
            raise ValueError("Serialized model parameters differ")
        predictions = np.asarray(model.predict(test.loc[:, list(FEATURES)]))
        if (
            predictions.shape != (len(test),)
            or not np.isfinite(predictions).all()
            or (predictions < 0).any()
        ):
            raise ValueError("Predictions must be finite nonnegative scalar values")
        if any(
            digest(path.read_bytes()) != expected for path, expected in paths.items()
        ):
            raise ValueError("Frozen input changed during evaluation")
        score = float(mean_absolute_error(test["cnt"], predictions))
        rows = test.loc[:, ["instant", "dteday", "hr", "cnt"]].copy()
        rows["prediction"] = predictions
        csv_bytes = rows.to_csv(index=False, lineterminator="\n").encode()
        (output / "predictions.csv").write_bytes(csv_bytes)
        result = {
            **plan,
            "status": "completed",
            "held_test_scored": True,
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "evaluation_code_revision": revision,
            "evaluation_script_sha256": digest(Path(__file__).read_bytes()),
            "selection_sha256": paths[root / "reports/final-model-selection.json"],
            "metadata_sha256": selection["checksums"]["model-metadata.json"],
            "data_sha256": selection["data_sha256"],
            "uv_lock_sha256": selection["uv_lock_sha256"],
            "test_rows": len(test),
            "test_date_min": str(test["dteday"].min().date()),
            "test_date_max": str(test["dteday"].max().date()),
            "test_mae": score,
            "predictions_sha256": digest(csv_bytes),
            "environment": {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "scikit_learn": sklearn.__version__,
                "numpy": np.__version__,
                "pandas": pd.__version__,
                "joblib": joblib.__version__,
            },
            "scope": "Held-test prediction quality of the preselected saved model; not HTTP latency or a promotion decision",
        }
        save(output / "result.json", result)
        return result
    except BaseException as error:
        save(
            output / "failure.json",
            {
                "status": "incomplete",
                "error_type": type(error).__name__,
                "message": str(error),
            },
        )
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute-held-test", action="store_true")
    args = parser.parse_args()
    root = Path.cwd()
    try:
        revision = "not_recorded"
        if args.execute_held_test:
            dirty = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            if dirty.strip():
                raise ValueError(
                    "Commit the frozen selection and evaluator before scoring"
                )
            revision = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        result = evaluate(root, execute=args.execute_held_test, revision=revision)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print(f"Final evaluation stopped: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
