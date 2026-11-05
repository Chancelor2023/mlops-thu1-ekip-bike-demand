# Promotion preflight: gate integration on Jerry's branch

Owner: Jerry. Reviewer: Mathis.

The integration below is implemented on Jerry's branch and still needs review
by Mathis and Brett. It is not evidence of team approval or real model eligibility.
`bike_demand.promote` supports a read-only dry-run, local preparation and
versioned local installation. None loads a joblib, switches current accepted
state or deploys.

## Decision fields and integration

The pipeline preserves the gate result, adding the candidate's `model_version`,
`model_sha256` and `model_run_id`. The preflight expects:

- Native Brett check records: `checks.<name>.status == "pass"`, including
  quality, performance and every integrity/provenance control listed in
  `promote.REQUIRED_CHECKS`. Every additional reported check must pass too.
  No translated `passed: true` fields or renamed performance checks are needed.
- `accepted_reference`: exactly `state_id`, `model_version`, `checksums` from
  `artifacts/accepted/current.json`, captured before candidate evaluation. The
  gate must verify that these identify the accepted bundle it actually compares.
- `policy_sha256`: SHA-256 of the policy bytes applied during evaluation.
- `evidence_sha256`: SHA-256 values for `model.joblib`, `model-metadata.json`,
  and `metrics.json`, captured from the final evaluated candidate files.

The pipeline verifies and captures current accepted state before training and
passes it to the gate. The gate binds this snapshot to the actual accepted
bundle and checks it again after evaluation. It hashes candidate files before
evaluation and checks those bytes and the policy again before deciding. The
pipeline preserves this evidence and preflights an eligible result before
returning success. Missing provenance is never filled by the promotion component.

A direct standalone gate evaluation without `accepted_state` remains supported
for isolated evaluation/tests, with `promotion_evidence_complete: false`. Its
verdict cannot pass promotion preflight because the binding check is absent.
The pipeline is the entry point for producing bound promotion evidence.

For the downloaded accepted baseline, the gate reads the existing
`reference-evidence/validation-reevaluation.json` when `metrics.json` is absent.
The accepted MAE is still recomputed on the same validation rows; no original
bundle file or metadata is rewritten and no historical metric is invented.

## Run locally once actual gate evidence is available

```bash
./.venv/Scripts/python.exe -m bike_demand.promote \
  --candidate artifacts/candidates/<candidate-version> \
  --policy configs/gate-policy.yaml --dry-run
```

Exit 0 means the read-only preflight passed. Exit 3 means blocked; the reason
is printed as JSON. A mode (`--dry-run`, `--prepare` or `--install-local`) is required. This is neither
a new model evaluation nor approval to deploy. Synthetic test decisions prove
validation behavior only; they are not eligible candidates for real promotion.

## Prepare a local staging bundle

```bash
./.venv/Scripts/python.exe -m bike_demand.promote \
  --candidate artifacts/candidates/<candidate-version> \
  --policy configs/gate-policy.yaml \
  --prepare --expected-state <state_id-from-current.json>
```

Preparation holds an exclusive `artifacts/.promotion.lock`, checks the expected
state, copies evaluated bytes and the policy to a unique `artifacts/promotions/`
directory, verifies the copies and rechecks the inputs. `00-started.json` retains
the previous accepted manifest; only `01-prepared.json` marks a completed copy.
A handled failure leaves `99-blocked.json` and releases the lock. Abrupt process
termination may leave a lock and partial staging folder: investigate the owner,
journal and current state before any manual recovery; never assume success or
automatically remove a lock. Previous attempts are never overwritten.

The lock coordinates cooperating processes on the **same local artifacts dir**.
It is not a distributed Cloud Run or GCS lock. Prepared does not mean accepted:
`current.json` and the old accepted bundle remain unchanged. Real promotion must
run from reviewed main and revalidate staged evidence under a lock again.

## Install a version locally, pending cloud verification

This mode is for use **after review/merge and gate interface integration**:

```bash
git fetch origin
# Use a clean main checkout matching the reviewed origin/main revision.
./.venv/Scripts/python.exe -m bike_demand.promote \
  --install-local --operation artifacts/promotions/<operation-id> \
  --expected-state <state-id> --expected-revision <full-reviewed-main-sha>
```

The guard checks branch main, HEAD, the locally fetched origin/main ref and a
clean working tree. It does not query GitHub reviews or refresh remote refs:
the operator/reviewer must verify the PR approval and fetched revision.

Installation holds the same local lock, revalidates the prepared operation,
original candidate, policy and accepted state, copies into a private sibling
directory, verifies the copy, and renames the completed directory into
`artifacts/accepted/<candidate-version>/`. It records `02-installed-local.json`
with status `installed_local_pending_cloud`. The previous accepted bundle and
`current.json` are unchanged. A directory under accepted is not automatically
current, promoted, or deployed.

Failed attempts retain a unique `install-failed-*.json` and any incomplete
private copy for diagnosis. An interruption after the rename but before the
receipt can be retried with the same operation, expected state and revision:
the existing version must have matching bytes and the same installation-origin
record. Other existing versions are never overwritten. Existing corrupt journal
records require investigation rather than automatic repair. A local lock does
not protect writes made from another PC/Cloud Shell.

Operations prepared before `candidate_path` and `policy_path` were recorded
must be prepared again; missing provenance is not reconstructed silently.
No real operation has been prepared or installed by the synthetic tests.

Current-state finalization is intentionally separate: only after Cloud Run
identity and traffic are verified should a later command replace current.json.
The cloud operation and local manifest are not a single transaction; the journal
and before/after observations must support recovery if either side is interrupted.

## Remaining work

- Have Brett and Mathis review the gate/pipeline integration changes.
- Integrate real gate evidence and verify installation from reviewed main.
- Add safe current-manifest finalization after verified cloud traffic switch.
- Add cloud deployment without production traffic, identity verification,
  explicit traffic switch and recovery tests.
- Extend the recovery archive/evidence with dependency and evaluation records.

Tests live in `tests/test_promote.py`. They are intentionally unmarked for now:
the existing full-suite CI step runs them, without claiming they are API,
baseline-regression or starter-infrastructure tests.

`tests/test_pipeline_promotion.py` connects real CSV validation, chronological
splitting, pipeline serialization, gate evaluation and promotion preflight on
temporary synthetic data. Training, MLflow persistence and timing are stubbed;
these tests do not consume the real candidate budget or prove service latency.
Real latency measurement in the agreed container environment and real gate
decisions remain to be captured after review; no Cloud Run call is made here.
