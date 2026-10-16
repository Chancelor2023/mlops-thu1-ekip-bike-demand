# Week 1, Labs 1–2: team evidence

## Team and roles
* **Repository:** `mlops-thu1-ekip-bike-demand`
* **Lead B:** Jerry (Data validator `validate.py`, splitting `split.py`)
* **Role C:** Romain Cortyl (Independent MLflow audit, PR review)
* **Role D:** Mathis (`train.py`, baseline model fitting)

## Repository and pull requests
* **PR #7 (Lab 1 Normalization):** `https://github.com/Chancelor2023/mlops-thu1-ekip-bike-demand/pull/7` (by Romain)
* **PR Lab 2 (Validator & Split):** `<LIEN_PR_B>` (by Jerry)
* **PR Lab 2 (Model Training & Tracking):** `<LIEN_PR_D>` (by Mathis)

## Setup, preflight and quality checks (commands and actual results)
* `uv run --locked ruff format src/ tests/` -> All files formatted or unchanged
* `uv run --locked ruff check src/ tests/` -> All checks passed!
* `uv run --locked pytest -q -m exercise` -> 35 passed, 0 failed

## Data identity, validator checks and added test
* **Data file:** `data/raw/hour.csv` (Bike Sharing dataset)
* **SHA-256 integrity verified** by validator contract.
* **Validator checks:** Verified non-empty columns, value ranges for temperature/humidity/windspeed, presence of contract predictors, and absence of target leakage.
* **Added test:** Validator tests ensure schema fidelity and raise on missing categorical levels.

## Partition counts, boundaries and held test rows
* **Split type:** Time-based temporal ordering (chronological split).
* **Partitions:**
  - Train split: ~70% of chronological records
  - Validation split: ~15%
  - Test split: ~15% held-out test rows
* **Boundary check:** Enforces no future data leakage into the training partition (`dteday` monotonicity preserved).

## Comparator and RF: run IDs, validation MAEs, metadata/readback
* **Comparator baseline (`naive_train_mean`):**
  - Run ID: verified in `tracking/mlflow.db`
  - Predicts constant target mean from training set.
* **Random Forest (`random_forest`):**
  - Model Run ID: `60124f94be80438eb223d5c1387daca1`
  - Experiment Name: `bike-demand-baseline`
  - Validation MAE: `86.84685685591091` (~`86.85`)
  - Status: `Finished`
  - Model metadata: verified in `artifacts/model-metadata.json` (model version `baseline-f2c5cffff169`).

## Optional stretch, after the core: unchanged-config repeat (new run IDs, history, differences)
not attempted

## Fault diagnosis and your own Fault B
* **Choice:** Tested behavior when including banned features (`cnt`, `casual`, `registered`) into `select_features`.
* **Reason:** Protects against data leakage where the target or components of the target contaminate input predictors.
* **Result:** `select_features` immediately raised contract error; baseline comparator and RF strictly rejected leaking columns, passing `test_banned_features_and_order`.

## Review observation and author's response
* **Observation (Reviewer C):** Reviewer noted that the tracking backend URI must point to `sqlite:///tracking/mlflow.db` to visualize runs locally without crashing on the default file store.
* **Response (Author D):** Acknowledged; verified local tracking launch command and validated that artifacts are safely output under `artifacts/` and logged in MLflow database.

## Contribution and assistance/recovery acknowledgement
* **Romain Cortyl (Role C):** Authored edge case test in Lab 1 (PR #7), reviewed Lab 2 PRs, and independently verified the MLflow tracking UI and metrics.
* **Mathis (Role D) & Jerry (Lead B):** Implemented training logic, pipeline scripts, and reviewed branch merges.
* **Assistance:** Starter code documentation, uv package management instructions.

## Blockers and next action
* **Resolved blockers:** MLflow UI SQLite path resolution (`sqlite:///tracking/mlflow.db`) and PowerShell debugging prompt interruption.
* **Next action:** Prepare Lab 3 workflow and integrate CI automated model packaging on `main`.

## Screenshots
Save images in `reports/images/`:
* `![MLflow runs](images/week-1-lab2-mlflow-runs.png)`: MLflow UI displaying experiment `bike-demand-baseline` with active run `random_forest` (`60124f94be80438eb223d5c1387daca1`), status `Finished`, and `validation_mae` = 86.8469.
* `![Lab 1 Test execution](images/Test_team.png)`: Successful local pytest execution for Lab 1 normalization.
* `![Lab 1 Test implementation](images/Test-team-program.png)`: Code view of the added edge-case test in `tests/lab1/test_team.py`.
