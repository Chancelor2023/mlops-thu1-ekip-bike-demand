# Release identity endpoint — GET /version

## Contract

This endpoint supplies the identity output requested by the Week 5 release brief.
It describes the running process, independently of readiness:

| Field | Meaning |
|---|---|
| `code_revision` | CODE_REVISION embedded in the image from its source commit; `unknown` if absent |
| `model_loaded` | Whether startup successfully verified and deserialized the model |
| `model_version` | Version from that loaded bundle; null when unavailable |
| `model_sha256` | SHA-256 of the exact serialized bytes deserialized at startup; null when unavailable |

The endpoint returns HTTP 200 even without a model. `/health` retains 503 for
unavailable models, and `/predict` retains its existing validation/prediction rules.
A successful identity response is not a readiness check. `unknown` code revision
must not be accepted as verified release identity. The response does not claim
an image digest or GitHub release tag; those must be recorded separately.
Requests receive X-Request-ID and structured event `version` through the existing
logging middleware. Authentication and routing remain the platform's responsibility.

## Checks before merge

From Git Bash at the repository root:

```bash
./.venv/Scripts/ruff.exe check .
./.venv/Scripts/ruff.exe format --check .
./.venv/Scripts/python.exe -m pytest -q tests/test_api.py
```

Tests cover loaded identity, missing/corrupt bundles, unchanged readiness behavior,
request-ID/log correlation, and a mounted file modified after the original bytes
have been captured. The reported digest must identify the loaded bytes, not the
replacement file. Codex assisted with implementation, tests and documentation.

## Release verification sequence

1. Commit and push the source/tests/docs on `release/v1.0.0`; have the latest CI
   and reviewer check the change before merging.
2. Build an image with GIT_SHA set to the exact reviewed release commit. Verify
   it locally using the retained accepted bundle mounted read-only; check identity,
   health, a valid prediction and an invalid input. Do not retrain or rescore the test.
3. Jerry performs the deliberate Cloud Run deployment using a digest-pinned image
   and the existing accepted bundle. First create/check a no-traffic revision;
   retain the old revision as the recovery target and preserve normal traffic
   until verification. Refresh configuration and storage checks before operating.
4. Retain the actual authenticated `/version` JSON, HTTP status, request ID,
   revision/image identity and routing evidence. Verify code/model/hash against
   the reviewed release commit and frozen accepted selection. Repeat health and
   prediction checks before declaring the release deployed.
5. Include that dated output in Release notes. Do not reuse a sample or label the
   old image's `/health` response as `/version` evidence.

No Cloud Run changes are made by adding this source endpoint. The historical
revision `00018-rng`, code `ea37b8a45d4a6738585d9de7d0f95d624ad1d3be`,
does not expose it. Follow the existing [runbook](../RUNBOOK.md) and
[deployment notes](lab-07/cloud-deployment.md) for operational constraints;
this document is a sequence to prepare, not a record of a completed deployment.

## Local validation — 20 November 2026

Executed on the release working tree before committing this endpoint:

| Command | Observed result |
|---|---|
| `.venv/Scripts/ruff.exe check .` | All checks passed |
| `.venv/Scripts/ruff.exe format --check .` | 30 files already formatted |
| `.venv/Scripts/python.exe -m pytest -q tests/test_api.py` | 27 passed, 1 dependency deprecation warning |
| `.venv/Scripts/python.exe -m pytest -q` | 244 passed, 2 dependency deprecation warnings, 109.99 seconds |
| Documentation links and `git diff --check` | Passed |

The warnings concern Starlette/httpx and SQLAlchemy's noload strategy. No final
held-test evaluation command or Cloud Run operation was executed for this change.
The API tests use synthetic models; image/live deployment verification remains
outstanding. CI must still check the actual pushed commit.
