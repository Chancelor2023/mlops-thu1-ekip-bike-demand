# Week 4, Lab 7: training pipeline, quality gate and controlled promotion

> Status: integration, CI and clean-environment evidence are observed and filled in.
> Candidates 01 and 02 have measured rejections with before/after preservation evidence.
> The experiment campaign stopped after two rejected candidates. Peer challenges
> remain to be documented; no promotion was performed and the two-version
> handoff to Lab 8 is incomplete.
> Sections marked **TO FILL** must contain only observed results.

## Team and roles

| Member | Lab 7 responsibility | Reviewer |
|---|---|---|
| Mathis | Lead, unified training pipeline, shared contract | Brett (pipeline), Romain (contract) |
| Brett | Quality gate, versioned policy, gate tests | Romain |
| Jerry | Accepted-model archive, promotion, Cloud Run deployment | Mathis |
| Romain | Integration tests, CI, README, this report | Jerry |

- Team repository: https://github.com/Chancelor2023/mlops-thu1-ekip-bike-demand
- Shared contract: [reports/lab-07-contract.md](lab-07-contract.md)
- Operator procedure: [reports/lab-07/operator-guide.md](lab-07/operator-guide.md)

## Pull requests (merge order from the contract)

| Order | PR | Author | Content |
|---|---|---|---|
| 1 | #31 | Mathis | `src/bike_demand/pipeline.py`, candidate configurations `configs/candidate-0{1,2,3}.yaml` |
| 2 | #32 | Brett | `src/bike_demand/gate.py`, `configs/gate-policy.yaml`, `tests/test_gate.py` |
| 3 | #33 | Jerry | `promote.py`, `deploy.py`, Cloud Build without auto-deploy, accepted backup records |
| 4 | #34 | Romain | `tests/test_lab7_integration.py`, `lab7` marker and CI step, README, this report |

Policy and budget were committed before any candidate execution: candidate
configurations in `2b9b700` (2026-11-05 15:49 +0100), gate policy in `a5a1faf`
(2026-11-05 17:50 +0100). The first real candidate metadata timestamp is
`2026-11-07T20:02:36.952998+00:00`, later than both policy/configuration commits;
this records the metadata event, not an exact command start time.

## Decisions applied

- Data unchanged: train 2011, validation 2012-01..06, test 2012-07..12 never scored;
  same canonical CSV, same 12 ordered features. Only model settings vary.
- Quality: `MAE_candidate < MAE_train_mean` and `MAE_candidate <= MAE_accepted + 1e-6`,
  accepted model re-evaluated on the same validation rows.
- Operations: warm in-container latency, 20 warm-up + 100 sequential requests x 3,
  median of the three p95 <= 1.25 x accepted. Does not measure Cloud Run cold starts.
- Integrity: data contract, finite non-negative predictions, reload, metadata
  consistency, identical SHA-256 between evaluation and promotion.
- Outcomes: `eligible` (0, never auto-promoted), `rejected` (2), `blocked` (3).
- Promotion: manual from reviewed `main`, lock + journal, tagged Cloud Run revision
  with `--no-traffic`, explicit activation, previous revision and bundle retained.

## Integration tests and CI (observed)

New file `tests/test_lab7_integration.py` (38 cases) drives the real
`run_pipeline` -> gate -> promotion preflight -> API on a synthetic dataset. Only
training, MLflow and latency are stubbed. All Lab 7 test files now carry the
`lab7` marker, and CI runs them as a dedicated step `Tests (lab7)` after
`regression`, so a red step names the Lab 7 group.

| Critical case | Test | Expected | Observed |
|---|---|---|---|
| Eligible, rejected or blocked never change the accepted version | `test_no_gate_outcome_changes_accepted_version_or_served_model` | accepted bytes, `current.json` and `/health` identity identical before/after; no lock, no new accepted version | pass |
| Real (measured) rejection | `test_real_rejection_records_values_thresholds_and_is_refused` | exit 2, quality fail, reasons, preflight refuses | pass |
| Missing control (each of the 13 mandatory checks) | `test_missing_or_unpassed_control_blocks_promotion` | preflight refuses, missing or not passed | pass (26 cases) |
| File modified after evaluation | `test_file_modified_after_evaluation_cannot_be_promoted` | preflight and prepare refuse (model, metadata, metrics) | pass |
| Accepted reference became stale | `test_stale_accepted_reference_requires_reevaluation` | "evaluated a different accepted state", prepare refuses | pass |
| Accepted reference tampered | `test_tampered_accepted_reference_blocks_evaluation` | blocked before training | pass |
| Interrupted execution (Ctrl+C in training or gate) | `test_interrupted_execution_is_never_promotable` | no `decision.json`, preflight refuses | pass |
| Crash after saving the model | `test_crash_after_saving_model_is_blocked_and_rerun_is_isolated` | blocked; rerun in a new directory, partial attempt kept | pass |

Local results on this branch (Linux x86_64, uv 0.12.23 as pinned by CI):

| Step | Result |
|---|---|
| `uv lock --check`, `ruff check`, `ruff format --check`, preflight | pass |
| `pytest -m infra / lab1 / exercise / api / regression` | 9 / 4 / 37 / 25 / 2 passed |
| `pytest -m lab7` | 116 passed |
| full suite | 193 passed, 0 unmarked tests |

**TO FILL:** link to the green GitHub Actions run of the integration PR.

### Proof that the integration tests can fail

Three defects were injected in a throwaway clone, never committed
([log](logs/lab-07/romain-03-integration-tests-can-fail.log)):

| Injected defect | Failing tests | Explanation |
|---|---|---|
| M1, the original Lab 7 problem: training also writes into the accepted bundle | 4 (all three outcomes + rejection) | accepted bytes differ after the run |
| M2: preflight stops requiring every mandatory check | 13 (`missing-*` cases) | `not-passed-*` cases are still caught by the per-check status loop, as expected |
| M3: SHA-256 verification disabled | 4 (modified model/metadata/metrics, tampered accepted) | changed bytes are no longer detected |

The first run of M1 exposed a weakness: the synthetic candidate was byte-identical
to the accepted model, so an overwrite was invisible. The candidate is now a
distinct artifact with the same predictions, and the test asserts that its
SHA-256 differs from the served one, so it cannot become vacuous again.

### Clean environment

Fresh clone, new virtual environment, full CI chain: all green
([log](logs/lab-07/romain-01-clean-env-ci-chain.log)). The real entry point on that
clean checkout, before retrieving the accepted bundle, is **blocked with exit 3**
without training, and only its own candidate directory is created
([log](logs/lab-07/romain-02-clean-env-pipeline-blocked-without-accepted.log)).
This is expected: the accepted bundle and `current.json` are not in Git.

## Real experiments (team, manual; stopped after two candidates)

Synthetic tests do not replace this. Use `set -o pipefail`, `mkdir -p reports/logs/lab-07`
and `2>&1 | tee reports/logs/lab-07/<attempt>.log`, and keep the exit status.

| Attempt | Config (declared) | Exit | Status | MAE candidate | MAE accepted | MAE train mean | p95 median cand./acc. | Main reason |
|---|---|---|---|---|---|---|---|---|
| 1 | `candidate-01.yaml` | 2 | rejected | 86.74306881621092 | 86.84685685591091 | 154.23179306864967 | 13.844112050151123 / 10.112879650068862 ms | latency ratio 1.3689584499363496 > 1.25 |
| 2 | `candidate-02.yaml` | 2 | rejected | 86.6918618844724 | 86.84685685591091 | 154.23179306864967 | 25.538313900051435 / 7.382474600262867 ms | latency ratio 3.4593161890651265 > 1.25 |
| 3 | `candidate-03.yaml` | N/A | not executed | N/A | N/A | N/A | N/A | operator stopped the campaign due to limited time |

Attempt 1 used reviewed main `8c5f89e`, before the later per-repeat evidence
correction. Its [raw evidence and scope](lab-07/evaluations/candidate-a73246114040/README.md)
include the real log, decision, policy, metrics and service captures. The accepted
pilot and evaluation medians differ; stability across executions is not established.
The historical decision has no individual repeat p95s. No values were reconstructed.
Attempt 2 used personal-branch commit `5cb8032`, including the evidence-retention
correction. Its [raw evidence and scope](lab-07/evaluations/candidate-50faa1f1edf6/README.md)
retain all three p95s for both models, the image identity, unchanged accepted-file
checks and service captures. The first accepted p95 was 14.994433850461064 ms,
versus 7.110802450006304 and 7.382474600262867 ms; stability is not established.
Both experiments used the same policy hash and neither was promoted.
Jerry decided to stop the campaign after two candidates due to limited time.
Configuration 03 remains declared but was not executed; it is neither a rejected
nor a blocked attempt and has no measurements or exit status. The maximum is
three configurations, not a requirement to use all three. No threshold or
configuration was changed to obtain an eligible outcome.

**Before/after proof of the real rejection** (same commands before and after):

```bash
sha256sum artifacts/accepted/<accepted-version>/model.joblib artifacts/accepted/<accepted-version>/model-metadata.json
sha256sum artifacts/accepted/current.json
uv run --locked python check_service.py ...   # served model_version, model_sha256, code_revision
```

| Evidence | Before | After |
|---|---|---|
| accepted `model.joblib` SHA-256 | `d24c050e3631d5b4c2feb8cb571bef6382d8c975c42a5c11edd28de78a0b8c07` | same; after-checksums.log reports OK |
| `current.json` SHA-256 / `state_id` | `c0ba8ad27fcc6f95c9a2531efb8b2a973228714f89259a448b111e0957f103ef` / `246c8505253a4252a63809b66c04b7f3` | same; after-checksums.log reports OK |
| served `model_version` / `model_sha256` (Cloud Run `/health`) | baseline-4df84bfe8121 / unavailable in legacy API | unchanged / still unavailable |

**Actual outcome: retain the accepted model; no promotion.** Neither evaluated
candidate is eligible. Both before/after evidence sets record preservation of
`baseline-4df84bfe8121`, its accepted state, and the existing Cloud Run revision
`mlops-thu1-ekip-bike-demand-00018-rng` at 100 percent traffic. No new candidate
revision was deployed, no traffic activation was performed, and there is no
`04-cloud-verified.json` or `06-finalized.json` for these rejected candidates.
Promotion/deployment code has synthetic test coverage, not a successful live
promotion demonstration. Latency stability remains a documented limitation.

**Lab 8 handoff: incomplete.** The existing accepted bundle, its recovery archive
and runtime references are retained. These experiments did not establish two
accepted versions with their own Cloud Run revisions or verify a live rollback.
Report this gap before the Lab 8 drill; do not claim the full handoff is complete.
Future promotion, if an independently eligible candidate becomes available,
must follow the [operator procedure](lab-07/operator-guide.md) from reviewed main.

## Review challenges (one significant defect per reviewer)

Defect PRs stay drafts titled `DO NOT MERGE: lab7 defect ...`.

| Reviewer -> area | Defect | Expected | Observed | Explanation |
|---|---|---|---|---|
| Brett -> candidate isolation (Mathis) | TO FILL | | | |
| Romain -> gate decisions (Brett) | TO FILL | | | |
| Mathis -> preservation and promotion (Jerry) | TO FILL | | | |
| Jerry -> integration tests and instructions (Romain) | TO FILL | | | |

Review finding from integration: the README "Pipeline and gate" draft described
commands that do not exist (`promote --execute`, `promote --rollback`,
`artifacts/archive/`). It was rewritten from `promote.py`, `deploy.py` and the
operator guide before review.

## Limits

- CI never trains on the canonical data, measures latency or calls Cloud Run.
- The gate's default timer measures local `model.predict`, not HTTP or cold starts.
- The local promotion lock does not coordinate two laptops; one operator session (Jerry).
- No tag `m4` after Lab 7 alone: it follows Labs 7 and 8.

## Screenshots (at most three)

Raw evidence is linked above. If screenshots are added, keep at most three and
use observed rejection decisions, preserved serving identity or actual CI runs.
No screenshot of a new candidate deployment is available: none was performed.

## Assistance acknowledgement

Romain used Claude (Anthropic) to write the integration tests, check the tests
with defect injection, run the clean-environment check and correct the README.
All results above were re-run and checked locally.
