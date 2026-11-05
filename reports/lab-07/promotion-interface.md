# Promotion preflight: proposed interface for Brett and Mathis

Owner: Jerry. Reviewer: Mathis.

This is a proposed integration interface, not evidence of agreement by the team.
`bike_demand.promote` supports a read-only dry-run, local preparation and
versioned local installation. None loads a joblib, switches current accepted
state or deploys.

## Decision fields to coordinate before integration

The pipeline already preserves `model_version`, `status`, `reasons`, `checks`,
`model_sha256` and `model_run_id`. The preflight additionally expects:

- `checks.quality.passed`, `checks.operation.passed`, `checks.integrity.passed`:
  JSON boolean true, with every additional reported check also passed.
- `accepted_reference`: exactly `state_id`, `model_version`, `checksums` from
  `artifacts/accepted/current.json`, captured before candidate evaluation. The
  gate must verify that these identify the accepted bundle it actually compares.
- `policy_sha256`: SHA-256 of the policy bytes applied during evaluation.
- `evidence_sha256`: SHA-256 values for `model.joblib`, `model-metadata.json`,
  and `metrics.json`, captured from the final evaluated candidate files.

Brett needs to produce these fields after running all mandatory checks. Mathis
needs to preserve the three additional fields in the final `decision.json`;
the existing pipeline currently drops fields outside its explicit allowlist.
The promotion component must not invent or fill missing gate evidence.

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

- Agree the interface with Brett and Mathis and integrate their outputs.
- Integrate real gate evidence and verify installation from reviewed main.
- Add safe current-manifest finalization after verified cloud traffic switch.
- Add cloud deployment without production traffic, identity verification,
  explicit traffic switch and recovery tests.
- Extend the recovery archive/evidence with dependency and evaluation records.

Tests live in `tests/test_promote.py`. They are intentionally unmarked for now:
the existing full-suite CI step runs them, without claiming they are API,
baseline-regression or starter-infrastructure tests.
