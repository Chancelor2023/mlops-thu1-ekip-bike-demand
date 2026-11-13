# Final model selection and one held-test evaluation

Selection date: 13 November 2026. Jerry reports the team decision to retain
`baseline-4df84bfe8121`, before opening the final held-test metric.
Machine-readable identities and rules: [final-model-selection.json](final-model-selection.json).
The score has **not** been computed by preparing this protocol.

## Why retain the existing accepted model?

| Observation on validation / Lab 7 | Consequence |
|---|---|
| Accepted RF MAE 86.84685685591091 versus naive train-mean MAE 154.23179306864967 | The retained model has useful measured validation performance relative to the simple baseline. |
| Candidate 01 MAE 86.74306881621092, latency ratio 1.3689584499363496 | Slightly better quality, but fails unchanged maximum ratio 1.25. |
| Candidate 02 MAE 86.6918618844724, latency ratio 3.4593161890651265 | Slightly better quality, but also fails latency. |
| Accepted artifacts have retained hashes, compatible image and verified API/recovery evidence | Reuse the exact retained bytes and known operational configuration. |

This is a constrained operational decision, not a claim of the best possible model,
statistical significance, timing stability, universal performance or a new all-pass
gate record. The current model has 50 trees, depth 10, random_state=42 and n_jobs=1.
Neither evaluated replacement passed every gate check. Candidate 03 was not run.
The choice does not depend on the held-test result and does not cure the missing
two-accepted-version handoff or the unavailable original training commit.

## Evaluation boundary

- Load the trusted saved `model.joblib`; do not run training or the candidate pipeline.
- Keep the existing 2011-trained model: no refit on validation and no hyperparameter changes.
- Use the frozen `hour.csv`, ordered 12-feature contract and target `cnt`.
- Test window: 1 July to 31 December 2012 inclusive; 4,376 observed hourly rows.
- Primary and only selection-independent final metric: MAE, in rentals per observed hour.
- One prediction pass on that preselected saved model; no candidate comparison on test.
- Keep the result even if worse than validation. Investigate limits without tuning
  against the same held test and then presenting it as unseen again.
- This evaluates offline prediction quality, not HTTP latency, availability or promotion.

## Preparation and execution (Git Bash, Windows)

First sync the working branch with reviewed main if appropriate, inspect and commit
this selection, evaluator and synthetic tests, then publish/review that preparation.
The course's final integration branch is `release/v1.0.0`; coordinate it with the team.
Use one designated operator and machine for the real evaluation.

```bash
./.venv/Scripts/python.exe scripts/evaluate_final.py --dry-run
```

The default/dry run checks bytes, metadata, configuration, lock and test population.
It neither deserializes the model nor predicts/scores. The result must say
`ready_not_evaluated` and `held_test_scored: false`.

After preparation is committed and the working tree is clean, run exactly once:

```bash
set -o pipefail
./.venv/Scripts/python.exe scripts/evaluate_final.py --execute-held-test \
  2>&1 | tee artifacts/final-evaluation-console.log
RESULT=${PIPESTATUS[0]}
printf 'Final evaluation exit: %s\n' "$RESULT"
```

Do not rerun automatically after an error: preserve the attempt and examine the failure.
The fixed output directory is created exclusively. An existing `reports/final-evaluation/`
blocks another scoring attempt on the same checkout; do not delete or rename it to
bypass that guard. This is a local safeguard, not a distributed lock across teammates.
The program refuses to execute while Git has uncommitted changes. An ignored console
log under artifacts does not alter this precondition.

## Outputs and reporting

- `reports/final-evaluation/started.json`: retained start record, including incomplete attempts.
- `result.json`: actual MAE, population/dates, model/data/metadata/selection hashes,
  evaluator source revision/hash, lock hash and observed environment.
- `predictions.csv`: observed identities, labels and predictions supporting that MAE.
- `failure.json`, if the attempt fails; keep it, never replace failure with an expected result.

Verify model/data hashes remain unchanged, retain the actual console output, then
commit the observed outputs and link them from the README and Release notes.
The evaluation commit can precede the final release tag: record both identities
accurately rather than claiming the result ran on a commit that did not exist yet.
Never invent a score in advance. Explain that MAE is a mean absolute count error,
not accuracy percent or a guarantee on every hour. Compare validation and final
MAE descriptively; the populations and seasons differ.

## Tests and assistance

`tests/test_final_evaluation.py` uses only synthetic fixture data/model stubs.
It checks dry-run separation, no fitting, exclusive execution/output preservation,
checksum failure before prediction and mutation detection during prediction.
It never loads the real retained model or scores real course held-test labels.
Codex assisted with this protocol, selection record, evaluator and synthetic tests;
Jerry is the designated operator for the real evaluation.
