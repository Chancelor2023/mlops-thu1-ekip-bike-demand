# Lab 5 contract (agreed by the team before coding)

Decided on 2026-10-23 by Jerry, Romain, Brett and Mathis. Week 3 lead: Brett; main reviewer: Romain.
Each PR of Lab 5 must follow these names. Changing one requires telling the team first.

| # | Decision | Choice | Rejected option and why |
|---|---|---|---|
| 1 | "Deployed" | The image built from a known `main` commit is started with the README commands, `/health` returns `200` with the expected `model_version` and `code_revision`, and the check script exits `0`. The final check is run by a member who wrote neither the start-up nor the check. | "The container is running": a running container is not a verified deployment. |
| 2 | Identity | `/health` adds `model_version` (from `model-metadata.json`) and `code_revision` (full Git SHA). `status` is kept. If the revision is unknown, the service says `"unknown"` and the check must fail. | A separate `/version` endpoint: duplicates `/health`. |
| 3 | Settings | `MODEL_DIR=/app/artifacts` (volume, read-only); `GIT_SHA` as a **build** argument stored as `CODE_REVISION`; `LOG_LEVEL` at **run** time (`-e`); port fixed at 8000. | Passing the revision with `-e` at run time: anyone could claim a wrong revision for a given image. |
| 4 | Expected values | Expected model = `model_version` printed by the training step; expected revision = `git rev-parse HEAD` of the built commit. Both are passed **as arguments** to the check script. | Hard-coded in the script (wrong after retraining); asked to the service itself (circular). |
| 5 | Log line | One JSON line per request on stdout: `ts`, `event` (`predicted`, `rejected`, `model_unavailable`, `health`, plus `startup`), `request_id`, `method`, `path`, `status`, `duration_ms`, `model_version`, `code_revision`. Never: secrets, tokens, auth headers, environment dumps, request bodies (only the names of invalid fields). | Free text (`INFO: request ok`): hard to filter and compare. |
| 6 | Failure to provoke | Run an image whose `GIT_SHA` differs from the expected one: the check must fail on the revision line and the logs must show the real revision. Alternative: start without the volume (`503` + `startup` log "model not loaded"). | — |

## Owners (updated 2026-10-23: Jerry and Mathis swapped)

| Part | Owner | Reviewer |
|---|---|---|
| Start-up + identity (decisions 2–3) | Jerry | Brett |
| External check script (decision 4) | Brett | Romain |
| Logging (decision 5) | Mathis | Jerry |
| README "Deploy" + team report Lab 5 | Romain | Mathis |

Merge order: start-up → check → logging → README.
