# Lab 5 contract (agreed by the team before coding)

Decided on 2026-10-23 by Jerry, Romain, Brett and Mathis. Week 3 lead: Brett; main reviewer: Romain.
Each PR of Lab 5 must follow these names. Changing one requires telling the team first.

| # | Decision | Choice | Rejected option and why |
|---|---|---|---|
| 1 | "Deployed" | Two targets, same image and same check. **Local**: the image built from a known `main` commit is started with the README commands. **Cloud Run**: the same commit is built by Cloud Build and served on the URL given in the README. In both, `/health` returns `200` with the expected `model_version` and `code_revision`, and the check script exits `0` against that URL. The final check is run by a member who wrote neither the start-up nor the check. | "The container is running" or "Cloud Run shows a green revision": neither proves which model and code answer. |
| 2 | Identity | `/health` adds `model_version` (from `model-metadata.json`) and `code_revision` (full Git SHA). `status` is kept. If the revision is unknown, the service says `"unknown"` and the check must fail. | A separate `/version` endpoint: duplicates `/health`. |
| 3 | Settings | `MODEL_DIR=/app/artifacts` (volume, read-only); `GIT_SHA` as a **build** argument stored as `CODE_REVISION`; `LOG_LEVEL` at **run** time (`-e`); port fixed at 8000. | Passing the revision with `-e` at run time: anyone could claim a wrong revision for a given image. |
| 4 | Expected values | Expected model = `model_version` printed by the training step; expected revision = `git rev-parse HEAD` of the built commit. Both are passed **as arguments** to the check script. | Hard-coded in the script (wrong after retraining); asked to the service itself (circular). |
| 5 | Log line | One JSON line per request on stdout: `ts`, `event` (`predicted`, `rejected`, `model_unavailable`, `health`, plus `startup`), `request_id`, `method`, `path`, `status`, `duration_ms`, `model_version`, `code_revision`. Never: secrets, tokens, auth headers, environment dumps, request bodies (only the names of invalid fields). | Free text (`INFO: request ok`): hard to filter and compare. |
| 6 | Failure to provoke | Run an image whose `GIT_SHA` differs from the expected one: the check must fail on the revision line and the logs must show the real revision. Alternative: start without the volume (`503` + `startup` log "model not loaded"). | — |
| 7 | Model on Cloud Run | The Lab 4 model files (`model.joblib`, `model-metadata.json`) are uploaded to a Cloud Storage bucket mounted read-only at `/app/artifacts`; no retraining. Container port set to 8000. Project: the instructor's shared project `mlops-ece-group2-and-group3`, region europe-west1; our resources contain `thu1-ekip` (service `mlops-thu1-ekip-bike-demand`, bucket `thu1-ekip-bike-demand-model`). The service requires authentication (instructor's choice): callers send a Google identity token (`gcloud auth print-identity-token`); the token is never logged. The service account only gets `roles/storage.objectViewer` on our bucket. | Training during the build (breaks "do not retrain"); committing the model to Git (large, untrusted joblib). |


## Owners (updated 2026-10-23: Jerry and Mathis swapped)

| Part | Owner | Reviewer |
|---|---|---|
| Start-up + identity (decisions 2–3) | Jerry | Brett |
| External check script (decision 4) | Brett | Romain |
| Logging (decision 5) | Mathis | Jerry |
| README "Deploy" + team report Lab 5 | Romain | Mathis |
| Cloud Run deployment (decision 7) | Jerry | Brett |

Merge order: start-up → check → logging → README.
