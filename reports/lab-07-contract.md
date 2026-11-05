# Week 4 — Lab 7: Training Pipeline, Evaluation and Quality Gate

## 1. Objective

The objective of Lab 7 is to introduce a controlled model training and evaluation workflow.

The pipeline must validate the frozen dataset, train an isolated candidate model, save and reload it, collect evaluation evidence, and apply a quality gate before a candidate can become eligible for promotion.

A candidate must never overwrite or modify the currently accepted model during training or evaluation.

The workflow must be reproducible, auditable, and safe in case of rejection or interruption.

## 2. Dataset and feature contract

The dataset remains frozen:

- Source: `data/raw/hour.csv`
- Snapshot integrity: `data/manifest.json`
- Training period: January 1 to December 31, 2011
- Validation period: January 1 to June 30, 2012
- Test period: July 1 to December 31, 2012

The existing `preflight.check_snapshot()` function must validate the dataset before training.

The existing `split.py` implementation remains the source of truth for temporal partitioning.

The test partition must never be used for:
- Model fitting
- Hyperparameter selection
- Quality-gate decisions
- Candidate or accepted-model performance comparisons

Test metrics must not be calculated or reported during Lab 7.

The model must use exactly the existing 12 features, in the existing order:

1. `season`
2. `yr`
3. `mnth`
4. `hr`
5. `holiday`
6. `weekday`
7. `workingday`
8. `weathersit`
9. `temp`
10. `atemp`
11. `hum`
12. `windspeed`

Target: `cnt`.

Target leakage through `cnt`, `casual`, `registered`, `instant` or `dteday` is forbidden.

Only Random Forest model parameters may vary between candidate configurations. The dataset, target, features, feature order and temporal partitions remain unchanged.

## 3. Accepted model reference

Before candidate evaluation, the team must freeze the model currently served by Cloud Run.

The accepted reference must include:

- Model artifact
- Model metadata
- SHA-256 checksum of the model
- Dataset checksum
- Ordered feature list
- Model configuration and effective parameters
- Validation MAE
- MLflow run ID, when available
- Container image and Cloud Run revision information
- Dependencies and execution context

A model version name alone is not sufficient evidence.

The accepted model must be re-evaluated on the same validation rows as the candidate.

If the accepted model's artifact, checksum, configuration or validation evidence is missing or inconsistent, the evaluation must be blocked.

## 4. Candidate isolation and storage

Candidate models must be stored separately from the accepted model.

Proposed structure:

```text
artifacts/
    accepted/
        <accepted-version>/
            model.joblib
            model-metadata.json
            metrics.json
    candidates/
        <candidate-version>/
            model.joblib
            model-metadata.json
            metrics.json
            decision.json
```

Each candidate receives a unique version identifier.

Training and evaluation must never write to the accepted-model directory.

Rejected, blocked and interrupted attempts must not modify the accepted model.

Accepted bundles are immutable. Every candidate attempt and its evidence must be retained.

The accepted model must remain available for comparison and rollback.

## 5. Training and evaluation workflow

The pipeline must provide one command that performs the following operations:

1. Validate the project snapshot and candidate configuration.
2. Load and validate the dataset.
3. Create the existing temporal partitions.
4. Train the candidate using only the training partition.
5. Evaluate the candidate on the validation partition.
6. Save the candidate model in its isolated directory.
7. Reload the saved model.
8. Verify that reloaded predictions match the original predictions.
9. Verify that predictions are finite and nonnegative.
10. Generate metadata and SHA-256 checksums.
11. Log the training and evaluation evidence in MLflow.
12. Compare the candidate with the accepted reference.
13. Apply the quality gate.
14. Save the final decision and evidence.

An incomplete execution must never produce an eligible candidate.

## 6. Quality-gate policy

### 6.1 Predictive quality

The candidate must satisfy both conditions:

- Candidate validation MAE must be strictly lower than the train-mean predictor validation MAE.
- Candidate validation MAE must be less than or equal to the accepted model validation MAE plus epsilon.

Initial epsilon:

`1e-6`

This tolerance is intended to account for numerical differences. It does not justify claiming an improvement when the models are effectively equivalent.

The accepted model must be evaluated on exactly the same validation rows and target values.

### 6.2 Performance

Performance must be measured under equivalent conditions:

- Same container resources and request conditions
- 20 warm-up requests
- 100 sequential measured requests
- 3 independent repetitions
- Comparison using the median of the three p95 latency measurements

The candidate's measured latency must not exceed the accepted model's latency by more than 25%.

The reference protocol must first be checked for stability on the accepted model.

This protocol measures warm request latency. It does not measure Cloud Run cold-start latency.

The policy must be frozen before candidate evaluation.

### 6.3 Integrity

The quality gate must also verify:

- Dataset snapshot integrity
- Feature names and order
- Model artifact existence
- Successful model reload
- Finite and nonnegative predictions
- Consistent metadata and metrics
- Matching model checksum
- Matching evidence between evaluation and promotion

A checksum change between evaluation and promotion invalidates the candidate.

## 7. Quality-gate outcomes

The pipeline must return one of three outcomes:

| Outcome | Exit code | Meaning |
|---|---:|---|
| `eligible` | 0 | All required checks passed. Candidate may be considered for promotion. |
| `rejected` | 2 | Evaluation completed, but one or more quality policies failed. |
| `blocked` | 3 | Required evidence is missing, invalid, or execution was incomplete. |

Eligibility does not automatically promote a candidate.

A rejected or blocked candidate must leave the accepted model unchanged.

## 8. Candidate budget and reproducibility

A maximum of three candidate configurations may be evaluated.

All configurations must be declared before candidate evaluation begins.

Every attempt must retain its configuration, model artifact, metadata, metrics, MLflow run ID, checksums and final decision.

A deliberately poor configuration may be used to demonstrate rejection, provided that the attempt is explicitly documented.

The training and evaluation process must record:

- Git commit
- Working-tree state
- Dataset checksum
- Configuration
- Effective model parameters
- Feature order
- Partition summaries
- Model checksum
- MLflow run ID
- Evaluation metrics
- Quality-gate decision

MLflow databases and generated model artifacts must not be committed to Git.

## 9. Promotion and deployment

Promotion is a separate, manual operation.

Only an eligible candidate can be considered.

Promotion must:

1. Run from the reviewed `main` branch.
2. Recheck the candidate decision and checksums.
3. Acquire a lock to prevent concurrent promotions.
4. Preserve the previous accepted model.
5. Install the candidate as a new immutable accepted version.
6. Deploy a new Cloud Run revision without production traffic.
7. Verify the deployed revision and its loaded model.
8. Shift production traffic only after explicit approval.

Each Cloud Run revision must load its own immutable model bundle.

An eligible candidate is not automatically a production model.

## 10. Responsibilities and interfaces

### Mathis — Pipeline lead

- Maintain this shared contract.
- Implement `src/bike_demand/pipeline.py`.
- Adapt the training code without breaking the existing baseline.
- Isolate candidate artifacts.
- Record configuration, metadata, metrics, MLflow IDs and checksums.
- Ensure interrupted executions cannot be marked eligible.
- Review Brett's pipeline quality-gate implementation and regression tests.

### Brett — Quality gate

- Implement `src/bike_demand/gate.py`.
- Define `configs/gate-policy.yaml`.
- Implement predictive-quality, latency and integrity checks.
- Return a structured decision with status and reasons.
- Review Mathis's pipeline.

Expected interface:

```python
evaluate_candidate(
    root: Path,
    candidate_dir: Path,
    accepted_dir: Path,
    policy_path: Path,
) -> dict
```

Expected result:

```python
{
    "status": "eligible",  # eligible, rejected or blocked
    "reasons": [],
    "checks": {},
}
```

### Jerry — Promotion

- Archive the current accepted model and its evidence.
- Implement `src/bike_demand/promote.py`.
- Ensure candidate verification and checksum integrity.
- Implement safe promotion and Cloud Run revision handling.
- Preserve the previous accepted version.
- Review Romain's promotion/integration work as agreed by the team.

### Romain — Integration and documentation

- Integrate the pipeline, quality gate and promotion components.
- Add integration and regression tests.
- Verify CI and the shared contract.
- Update documentation and the Lab 7 report.

## 11. Required tests

The team must verify at least:

- Frozen dataset checksum mismatch blocks execution.
- Invalid or reordered features block execution.
- Candidate training does not overwrite the accepted model.
- Model reload succeeds and predictions match.
- Non-finite or negative predictions block execution.
- Missing accepted-model evidence blocks evaluation.
- A candidate failing predictive quality is rejected.
- A candidate failing latency policy is rejected.
- A candidate with changed checksums cannot be promoted.
- An interrupted or incomplete execution cannot be eligible.
- A rejected or blocked candidate leaves the accepted model unchanged.
- An eligible candidate does not automatically trigger promotion.

## 12. Merge and integration order

The agreed order is:

1. Contract and quality-gate policy.
2. Mathis's candidate pipeline.
3. Brett's quality gate.
4. Jerry's promotion component.
5. Romain's integration, regression tests and documentation.

All changes must go through reviewed pull requests.

Defect-test pull requests remain drafts and must not be merged.

No direct push to `main`.

The existing Lab 6 CI protections must remain active.

## 13. Lab 7 completion criteria

Lab 7 is complete when:

- The shared contract has been reviewed and validated by all four team members.
- The candidate pipeline runs as one command.
- Candidate artifacts are isolated from the accepted model.
- Predictive quality, latency and integrity policies are enforced.
- Eligible, rejected and blocked outcomes behave correctly.
- All required tests and CI checks pass.
- The accepted model remains unchanged unless a separate manual promotion is approved.
- Evidence and documentation are available for review.

The accepted model and previous version must remain available for Lab 8.