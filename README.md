# Bike Demand: Week 1 starter

Teams of 3–4 use one private GitHub repository throughout the course. Lab 1 is
repository setup, Git workflow and quality checks. Lab 2 adds validated data,
chronological splitting, a baseline comparison and local MLflow tracking.
No Docker, cloud account or MLflow server is needed this week.

## Setup: Lab 1

Install Git and [uv](https://docs.astral.sh/uv/getting-started/installation/)
(`>=0.12.19,<0.13`). Python **3.12** is required; uv can download it. From the
`bike-demand/` root:

```bash
uv python install 3.12
uv sync --locked
uv run --locked python -m bike_demand.preflight
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pytest -q -m infra
uv run --locked pytest -q -m lab1
```

First setup requires internet for Python and the locked dependencies, unless
these exact distributions are already cached. The frozen UCI CSV ships here;
preflight does not download/repair it. `uv.lock` is shared across platforms;
that is not evidence that every OS has been tested. macOS setup has been checked;
Windows and Linux remain unverified. Remote CI is unavailable until a permitted
repository is configured and a workflow actually runs on the checked revision.
Do not regenerate the lock just to bypass an installation failure.

## Expected failure and exercise: Lab 1

`pytest -m infra` must pass immediately. `pytest -m lab1` has **one intentional
behavior failure** in `src/bike_demand/team.py`: the helper
`normalize_team_slug` does not yet meet the contract in `tests/lab1/test_team.py`
(trim, lowercase, join whitespace with hyphens, reject blank names with
`ValueError`). Read the assertion, diagnose the cause, make a small repair and add
one useful test of your own. Do not weaken assertions, skip tests or disable
checks. Sync or import errors, or failures outside `lab1`, are setup problems:
diagnose them separately.

Fill in `WORKING-AGREEMENT.md`. Use a task branch, open a pull request, and get a
review from another member before merging. Rotate driver/reviewer roles and the
main PR author between labs. Keep actual evidence in `reports/lab-01.md` and
`reports/week-01-team.md`; templates contain no pre-filled results.

## Expected failures: Lab 2

The student export has bounded TODOs in `src/bike_demand/`:

| File | Your task |
| --- | --- |
| `validate.py` | Categorical domains, finite normalised ranges, nonnegative counts, date windows |
| `split.py` | Chronological nonempty/disjoint/complete partitions; sort `(dteday, hr, instant)` |
| `train.py` | Ordered predictors, train-mean comparator, RF fit and validation MAE |

`NotImplementedError("TODO(Week 1, Lab 2): ...")` and failing exercise tests are
**expected before implementation**, not environment failures. Infra must pass
immediately. Do not skip/mute exercise tests or fabricate metrics to get green.
Tracking, metadata/history, configuration and input parsing are already supplied.
Read the failing test, inspect the contract, implement one TODO, and rerun:

```bash
uv run --locked pytest -q -m exercise
uv run --locked python -m bike_demand.validate --data data/raw/hour.csv
uv run --locked python -m bike_demand.train --config configs/baseline.yaml
uv run --locked pytest -q
```

Keep `data/raw/hour.csv` unchanged; use copies and `tests/fixtures/` for deliberate
faults. `missing-temp.csv` is the worked Fault A; design your own Fault B by
breaking exactly one contract rule or split boundary on a tiny copy, with a valid
control and a test of your own. The supplied `hum-out-of-range.csv` is another
worked example, not your Fault B. Missing hours are valid. Features and splits are fixed in the config and
code. Fit only on 2011 training rows; compare both predictors on the same
2012 January–June validation rows. Hold July–December 2012 test rows throughout
Weeks 1–4; do not compute test metrics. MAE is rentals/hour, not accuracy, and
RF is not required to beat the comparator. The task uses supplied weather;
it does not forecast future weather or station-level demand.

## Outputs and readback

Each successful train execution creates two separate MLflow runs, a saved
`artifacts/model.joblib` and `model-metadata.json`, latest `reports/metrics.json`,
and one appended `reports/metrics-history.jsonl` line. Metadata records feature
order, data identity, model version and run ID. A commit is recorded when Git is
available; `working_tree_dirty` prevents uncommitted code being mistaken for a
committed revision. Train reloads the trusted local model and verifies validation
MAE/metadata and logged artifact bytes. Never load untrusted joblib files.
Optional stretch, only after the core is complete and reviewed: run train again
unchanged and compare both run IDs and observed MAEs/history. Do not promise
byte-identical models across systems/library versions.

Viewer is optional; training does not depend on it:

```bash
uv run --locked mlflow server --backend-store-uri sqlite:///tracking/mlflow.db --default-artifact-root tracking/artifacts --no-serve-artifacts --host 127.0.0.1 --port 5000 --workers 1
```

`artifacts/`, `tracking/` and `.venv/` are ignored by Git. Team metrics may be
committed as evidence; never commit credentials or individual private reports.
CI currently checks only infrastructure/quality; expand it in Week 3.

## Build, train and serve with Docker

The image contains the code, configuration, data snapshot and tests, installed strictly
from `uv.lock`. It does **not** contain a model: the model is trained once into a Docker
volume, and the API only loads it from there (read-only). The service never trains.

### Prerequisites

- Git and Docker Desktop (engine running: `docker info` must answer).
- Run every command from the repository root, in Git Bash.
  In Windows PowerShell, use `curl.exe` instead of `curl`.

### 1. Build the image and link it to its commit

```bash
git rev-parse HEAD
docker build --build-arg GIT_SHA=$(git rev-parse HEAD) \
  -t bike-demand:$(git rev-parse --short HEAD) -t bike-demand:latest .
docker image inspect --format '{{.Id}} {{.Architecture}}' bike-demand:latest
```

`.git/` is excluded from the build context, so runs inside the container report
`"training_commit": "unavailable"`. Record the commit SHA and the image ID above instead;
the image tag carries the short SHA.

The full commit SHA is passed at build time as `GIT_SHA` and is reported by
`/health` as `code_revision` (`"unknown"` if the image was built without it).


### 2. Run the tests inside the image

```bash
docker run --rm bike-demand:latest uv run --locked pytest -q
```

### 3. Train the Lab 2 baseline into a volume

Same data, configuration, features and chronological split as Lab 2; no tuning and no
test-set evaluation.

```bash
docker volume create bike-artifacts
docker run --rm -v bike-artifacts:/app/artifacts bike-demand:latest \
  uv run --locked python -m bike_demand.train --config configs/baseline.yaml
```

The output prints both validation MAEs (`naive_train_mean`, `random_forest`), both MLflow
run IDs and the `model_version`. Compare them with Lab 2; differences between machines
(e.g. arm64 vs amd64) must be explained, not hidden.

### 4. Serve the API

```bash
docker run --rm -d --name bike-api -p 127.0.0.1:8000:8000 \
  -v bike-artifacts:/app/artifacts:ro bike-demand:latest
curl -s -w " HTTP %{http_code}\n" http://127.0.0.1:8000/health
curl -s -w " HTTP %{http_code}\n" -X POST http://127.0.0.1:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"season":1,"yr":1,"mnth":3,"hr":8,"holiday":0,"weekday":2,"workingday":1,"weathersit":1,"temp":0.4,"atemp":0.4,"hum":0.6,"windspeed":0.2}'
docker logs bike-api
docker stop bike-api
```

Expected: `/health` returns `200` with
`{"status": "ok", "model_version": "baseline-...", "code_revision": "<full commit SHA>"}`; `/predict` returns `200` with
`{"prediction": <finite, non-negative number>, "model_version": "baseline-..."}`,
where `model_version` comes from `model-metadata.json`. The interactive contract is at
http://127.0.0.1:8000/docs.

API contract: one flat JSON object with exactly the twelve training features.
Missing fields, wrong types, out-of-range values, extra fields and target fields
(`cnt`, `casual`, `registered`) are rejected with `422` before inference.

### 5. Check the missing-model behaviour

Start the same image **without** the volume:

```bash
docker run --rm -d --name bike-api-nomodel -p 127.0.0.1:8000:8000 bike-demand:latest
curl -s -w " HTTP %{http_code}\n" http://127.0.0.1:8000/health
docker stop bike-api-nomodel
```

Expected: `503` with `{"detail":"Model unavailable"}` on `/health` and `/predict`.

### 6. Clean up

```bash
docker volume rm bike-artifacts
docker image rm bike-demand:latest
```

## Support and individual reports

If setup remains blocked after five minutes, contact the instructor using the
support route recorded in your working agreement. Do not spend the whole lab
repairing a laptop. Ask for an approved recovery function only if coding remains
blocked; acknowledge the supplied code and assistance in your report. Recovery
is instructor-controlled, not bundled here.

## Names, reports and screenshots

Repository names (lowercase, hyphens, the same for the whole course):

- Team repository: `mlops-<session>-<team-name>-bike-demand`, for example
  `mlops-thu1-sparrows-bike-demand`. Sessions: `thu1`, `thu2`, `fri1`, `fri2`
  (1 = morning, 2 = afternoon).
- Your private report repository: `mlops-<session>-<github-username>`, for example
  `mlops-thu1-minhtc`. You create it and invite the instructor (`minhtc-uca`). Start from the
  [report template](../report-template/README.md) and commit to `main`; no report
  pull request or CI is used.

Reports mix writing and images. Save screenshots in `reports/images/` and embed
them in the report (see the template). A screenshot supports, but does not replace,
the command, revision and your explanation. Never show tokens, passwords or
personal data. Team evidence goes in `reports/lab-01.md` and
`reports/week-01-team.md`, with team screenshots in `reports/images/`.
Each weekly report is due Sunday 23:59 of the same week (published time zone).
Assessment policy comes from the instructor, not this repository.
See `BACKLOG.md` for later labs.
