# Jerry: local validation before peer review

Implementation is on Jerry-Cheng's-branch, based on bc9509c plus the uncommitted
deployment/API/documentation changes prepared for this review. These results do
not claim that bc9509c alone contains the deployment implementation.

## Observed local checks

- Ruff lint passed; formatting check: 23 files already formatted.
- Full pytest suite: **155 passed, 2 warnings in 68.80 s**.
- Warnings are existing Starlette TestClient and SQLAlchemy deprecations.
- No real cloud calls, candidate experiments or deployment were performed.
- Initial accepted model remains baseline-4df84bfe8121; local state identifier
  remains 73432c0c47554258aeea5f52a1bed896.

Commands used local .venv/Scripts executables; pytest used an isolated temporary
base directory and disabled its cache provider. The operator can reproduce with:

```bash
./.venv/Scripts/ruff.exe check .
./.venv/Scripts/ruff.exe format --check .
./.venv/Scripts/python.exe -m pytest -q
```

Cloud tests use a fake backend, synthetic bundle files and temporary state.
They verify no-traffic staging, identity mismatch refusals, generation mismatch,
explicit activation, retention of the old bundle, unchanged current state before
traffic verification, and recovery after interruption before/after atomic state
replacement. API tests refuse missing/wrong checksums before deserialization and
verify that health reports the exact bytes loaded even if a mounted file changes.

## Review points and practical limits

- Mathis reviews promotion/deployment; Brett reviews gate bindings; Romain
  coordinates integration/report evidence. No approval is implied by these tests.
- api.py was normalized from historical CRLF to LF while editing. Inspect its
  functional diff using `git diff --ignore-space-at-eol -- src/bike_demand/api.py`.
- A clean reviewed main checkout, fresh baseline snapshot and real eligible
  candidate are prerequisites for real deployment. Local locks are not distributed.
- GitHub CI for the final published revision and actual gcloud behavior still
  need verification. No live rollback or service latency result is claimed.
- README links the policy, entry point, decision locations and operator procedure.
- The initial archive recovery has separate real evidence. New-version recovery
  and Lab 8 require retained images/revisions plus live verification after merge.
