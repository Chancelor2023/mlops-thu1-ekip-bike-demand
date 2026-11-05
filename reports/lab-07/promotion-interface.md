# Promotion preflight: proposed interface for Brett and Mathis

Owner: Jerry. Reviewer: Mathis.

This is a proposed integration interface, not evidence of agreement by the team.
The initial implementation of `bike_demand.promote` supports **dry-run only**.
It never loads a joblib, writes accepted state, copies a candidate or deploys.

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
is printed as JSON. Invocation without `--dry-run` is refused. This is neither
a new model evaluation nor approval to deploy. Synthetic test decisions prove
validation behavior only; they are not eligible candidates for real promotion.

## Remaining work

- Agree the interface with Brett and Mathis and integrate their outputs.
- Add manual promotion from reviewed main, an exclusive lock, journal and
  state revalidation under the lock. A dry-run is not a concurrency guarantee.
- Retain immutable accepted bundles and switch the current manifest safely.
- Add cloud deployment without production traffic, identity verification,
  explicit traffic switch and recovery tests.
- Extend the recovery archive/evidence with dependency and evaluation records.

Tests live in `tests/test_promote.py`. They are intentionally unmarked for now:
the existing full-suite CI step runs them, without claiming they are API,
baseline-regression or starter-infrastructure tests.
