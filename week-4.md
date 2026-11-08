# Week 4, Labs 7–8: training pipeline, quality gate, incident diagnosis and verified recovery

## Student / team

**Student:** Mathis Groult  
**Team:** Ekip  
**Week:** 4  
**Labs:** 7 and 8

## Links to code and pull requests

### Lab 7 — Training pipeline and quality gate
- `src/bike_demand/pipeline.py`
- `reports/lab-07-contract.md`
- `reports/lab-07-report.md`
- `reports/lab-07-gate-defects.md`
- Pull requests: **#34** (integration), **#35** (candidate evaluations).

### Lab 8 — Monitoring and incident recovery
- `reports/lab-08-contract.md`
- `reports/lab-08-incident.md`
- `reports/lab-08/rollback-target.md`
- `reports/lab-08/rollback-target.json`
- `reports/lab-08/payloads.json`
- `reports/lab-08/observation-plan.md`
- `reports/lab-08/diagnostic-checklist.md`
- `scripts/lab8_observe.py`
- Pull request **#36** (rollback target).
- Observation and diagnostic tooling committed on branch `Mathis-Groult's`.

## Test and execution results

### Lab 7

I implemented the candidate training pipeline and its quality-gate workflow.

The pipeline separates candidate evaluation from the currently accepted model. A candidate is trained and evaluated in an isolated location. The accepted artifact is not overwritten simply because a new candidate has been trained.

The intended sequence is:

1. Validate the frozen data snapshot and configuration.
2. Train the candidate.
3. Save it in its isolated candidate directory.
4. Read the saved candidate back.
5. Evaluate it against the validation criteria.
6. Make an explicit accept/reject decision.

The evaluation process preserves the agreed temporal split:
- Training: 2011.
- Validation: January–June 2012.
- Test: July–December 2012.

The test period is not used to select candidates.

**Execution evidence:**
- `uv run pytest -q`: 74 tests passed.
- Ruff import-order issue (`I001`) identified and corrected.
- Candidate evaluation results are documented in `reports/lab-07/`.

The Lab 7 results recorded two rejected candidates due to latency, while keeping the accepted model unchanged. A third candidate was not run.

### Lab 8

My initial work focused on preparing reproducible observation and diagnostic tooling.

I created:
- A frozen payload set containing 10 valid observations and 3 deliberately invalid inputs.
- An observation plan defining how to compare normal, incident and recovery periods.
- A diagnostic checklist to help investigate service, model, configuration and input boundaries.
- `scripts/lab8_observe.py` to automate requests and preserve observation results.

The planned workload uses the same 10 valid observations three times each, giving 30 valid attempts per phase, alongside 3 invalid requests. The same payloads are intended to be reused across all three periods.

**Local execution checks:**
- `uv run python -m py_compile scripts\lab8_observe.py`
- `uv run python scripts\lab8_observe.py --help`
- Ruff checks and the project test suite passed.

These checks establish that the observation tooling can be compiled and its command-line interface can be invoked. They do not establish that the Cloud Run drill itself was executed.

### Recovery target preflight evidence

I also reviewed the retained recovery target and its preflight evidence.

The documented target is:
- Cloud Run revision: `mlops-thu1-ekip-bike-demand-00018-rng`
- Model version: `baseline-4df84bfe8121`
- Code revision: `ea37b8a45d4a6738585d9de7d0f95d624ad1d3be`
- Image digest: `sha256:bbf02e7850f3c282a1cda39d539f59459856cd541d81c713fbdebb19f8f3dd3f`

The preflight files report:
- `/health` returned `status: ok` with the expected model and code identities.
- The retained recovery archive passed its integrity verification.
- The stored `model.joblib` and `model-metadata.json` matched their expected SHA-256 hashes and recorded GCS generations.
- Local compatibility checks returned HTTP 200 for a valid prediction and HTTP 422 for an invalid input.

However, the evidence explicitly records `cloud_run_modified: false` and `model_loaded: false`. It therefore demonstrates preparation and integrity checks, not a live Cloud Run recovery.

## Screenshots

The following screenshots will be added manually under `reports/images/`.

1. **Lab 7 pipeline implementation** — the candidate isolation and quality-gate workflow in `src/bike_demand/pipeline.py`. Include the relevant commit or PR reference.
2. **Lab 7 test results** — terminal output showing the passing test suite. Include the commit or run reference.
3. **Lab 8 observation tooling** — the payloads, observation plan and `lab8_observe.py` command-line interface. Include the relevant commit.
4. **Lab 8 recovery preflight** — the retained target identity and integrity-verification results. Clearly label this as preflight evidence, not a completed rollback.

## My contribution

### Lab 7 — Lead

I was the lead for Lab 7. My main contribution was implementing `src/bike_demand/pipeline.py` and documenting the quality-gate contract.

I focused on making the training workflow safer and more reproducible. In particular, I wanted to prevent a candidate model from replacing the accepted model before it had passed the agreed evaluation criteria.

I also worked on preserving the temporal data split and ensuring that candidate evaluation did not use the held-out test period.

### Lab 8 — Observation tooling and final verification

My assigned role for Lab 8 was final evidence verification, with Romain as my reviewer.

I also took responsibility for preparing the observation tooling and diagnostic material originally assigned to Brett. This included the frozen payloads, observation plan, diagnostic checklist and Python observation script.

For the final verification work, I started by comparing the contract, runbook, incident record and retained recovery evidence. My goal was to distinguish what had actually been demonstrated from what was only planned or prepared.

This review identified several important limitations:
- The incident record still states that no drill has been performed.
- The Lab 8 contract remains a draft, with the four sign-offs empty.
- The instructor's answer concerning the single accepted model version is still pending.
- The live re-check of the recovery target immediately before a drill is still pending.
- No live recovery or post-recovery Cloud Run observations have been recorded.

I therefore did not consider the recovery verified.

## Decisions and rationale

### Lab 7

The main design decision was to isolate candidate artifacts from the accepted model.

This avoids a situation where a candidate that performs poorly can accidentally replace the model currently used by the service.

I also kept the validation and test periods separate. The validation period is used for candidate selection, while the test period remains untouched to avoid data leakage and overly optimistic evaluation.

The quality gate makes the decision explicit rather than relying on the fact that training completed successfully.

### Lab 8

The observation protocol was designed to compare three periods using the same workload:
- Baseline.
- Incident.
- After recovery.

This makes the comparison more meaningful because the payloads and success definitions remain consistent.

Valid predictions and deliberately invalid inputs are counted separately. An HTTP 422 response for an invalid payload is expected behaviour, not a failed valid prediction.

I also kept HTTP latency descriptive rather than reusing the Lab 7 latency threshold. The two measurements do not represent the same thing: Lab 7 measured model prediction latency, whereas Lab 8 observes HTTP requests through the service.

Another important decision concerns the recovery target. The team has only one established accepted model version, `baseline-4df84bfe8121`. A different Cloud Run revision does not automatically represent a different accepted model version. We should not relabel a rejected candidate as accepted just to satisfy the requirement.

The contract therefore proposes a narrower recovery scope: restoring the retained accepted state on an isolated `lab8` tag, subject to instructor approval. This would demonstrate recovery to a retained state, but not a handoff between two accepted model versions.

## Review and response

My review focused on checking whether the available evidence supports the claims made in the Lab 8 preparation documents.

The preflight evidence is consistent on several points:
- The target revision and image identity are recorded.
- The stored model and metadata match the retained hashes.
- The recovery archive passed its integrity checks.
- Local compatibility checks returned the expected responses.

However, these results must not be confused with a completed recovery.

The incident record is still a template, and the contract is still marked as a draft. The sign-off table is empty, the instructor's scope decision has not been recorded, and the live drill evidence is absent.

My main review observation is therefore that the current evidence supports **recovery preparation and retained-artifact integrity**, but does not support a claim of **incident diagnosis and verified Cloud Run recovery**.

The next review step is to check the completed incident record and raw drill evidence once the team has performed the exercise. Any correction must be followed by a fresh evidence check.

## Blockers / missing evidence

The main blockers identified during my review are:

1. **No completed drill:** `reports/lab-08-incident.md` explicitly states that no drill has been performed.
2. **Contract approval missing:** the four required sign-offs in section 14 are empty.
3. **Instructor scope decision missing:** the contract asks for confirmation of the proposed scope given that only one accepted model version is established.
4. **Live target re-check missing:** the target must be checked again immediately before the drill.
5. **No two-version history:** the current and previous accepted model versions required by the original exercise have not been established.
6. **No recovery evidence:** there are no baseline, incident and recovery observations proving the required behaviour, identity and Cloud Run log agreement.
7. **No final diagnosis or fault reveal:** the incident record has no completed hypotheses, diagnosis, injected-fault description or response timeline.

These are not details to fill with expected values. They must be resolved through the actual exercise and recorded evidence.

## Assistance and recovery acknowledgement

I used assistance to help structure the implementation, review the pipeline logic and prepare the observation and diagnostic workflow.

I checked the resulting commands, code and test outputs locally rather than treating generated suggestions as proof of successful execution.

For Lab 8, I also reviewed the distinction between local compatibility tests and an actual Cloud Run recovery. The retained archive and storage hashes provide useful integrity evidence, but they do not prove that the service was switched back to the target revision or that it successfully served the post-recovery workload.

**Final status:** Lab 7 implementation and testing evidence are available. Lab 8 observation tooling and recovery preflight are prepared, but the live incident drill and verified recovery remain outstanding. I have not declared recovery successful.