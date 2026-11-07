# Lab 8: retained recovery target for peer review

Owner: Jerry. Reviewer: Romain. Status: prepared for review; no Cloud Run
incident or recovery has been performed by these checks.

## Target identity

| Field | Observed value |
|---|---|
| Project / region | mlops-ece-group2 / europe-west1 |
| Service | mlops-thu1-ekip-bike-demand |
| Retained revision | mlops-thu1-ekip-bike-demand-00018-rng |
| Model | baseline-4df84bfe8121 |
| Code | ea37b8a45d4a6738585d9de7d0f95d624ad1d3be |
| Image | `europe-west1-docker.pkg.dev/mlops-ece-group2/cloud-run-source-deploy/mlops-thu1-ekip-bike-demand/mlops-thu1-ekip-bike-demand@sha256:bbf02e7850f3c282a1cda39d539f59459856cd541d81c713fbdebb19f8f3dd3f` |
| Model directory | /app/artifacts |
| Cloud limits | 1 CPU / 512Mi; concurrency 80; request timeout 300 seconds |
| Mount | model -> /app/artifacts; GCS FUSE, read-only |
| Bucket | thu1-ekip-bike-demand-model |
| Startup probe | TCP port 8000; this is not model readiness |

Full configuration, pinned objects, expected hashes and recovery archive are
recorded in [rollback-target.json](rollback-target.json). Its expectations derive
from the retained Lab 7 reference and captured cloud state, not from the later
faulty revision. Production traffic was observed at 100 percent on this revision,
with latestRevision enabled; later deployment/tag operations must explicitly
preserve production routing and verify it afterwards.

## What was verified

- The generation-pinned recovery archive was downloaded; its SHA-256 and both
  recovered bundle hashes match the retained expectations.
- Generation-pinned current bucket objects have the same model/metadata hashes.
- The exact retained image was retrieved; its MODEL_DIR and CODE_REVISION match
  the expected mount and captured service health.
- The recovered archive bundle was mounted read-only in that image locally,
  limited to 1 CPU and 512Mi. /health returned 200 and the expected identity.
- A permitted validation observation (instant 8646, 2012-01-01) returned HTTP
  200 and prediction 37.30960864135864, finite and nonnegative, with the
  expected model version. An invalid hr=24 returned 422. No quality metric was
  computed and no model was trained.
- All three request IDs/statuses match structured container events. The container
  was then stopped manually: exit code 143, no OOM;
  logs record application shutdown. This is not a failed prediction check.

[Raw evidence](preflight-20261107T210602Z/) contains 21 original captured files,
SHA256SUMS and an attributes rule preserving their bytes. Archive SHA-256:
`2aadce1531b56afce58bcd676101f3dee78cd0e31f8112ad77142f56a57343d2`.

## Limits and pending work

This establishes local compatibility and retained identity evidence, not a live
Cloud Run rollback. The legacy API has no loaded-model hash. The cloud mount uses
bucket-root object names, so re-check actual object generations and stored bytes
before the drill; a retained revision alone does not pin model object generations.
Raw model files are deliberately outside Git and this package.

Two distinct accepted model versions are not established. The 18 Cloud Run
revisions are not proof of 18 model versions. Record this handoff gap and clarify
the expected drill prerequisites with the instructor before claiming the complete
Lab 8 outcome. No rejected Lab 7 candidate becomes accepted by relabeling it.

## Romain's review

- Trace the revision/image/code/model expectations to the independent records.
- Check archive/object generations and the local API responses against the logs.
- Confirm compatibility scope, required pre-drill refresh and remaining blockers.
- Record one actionable observation, Jerry's response and actual recheck evidence.

Review observation: pending. Author response: pending. Recheck: pending.
This document does not record an approval or disclose a fault scenario.

## Next sequence

1. Complete Lab 7 review/merge and Romain's target review; resolve or explicitly
   report missing accepted-version prerequisites.
2. Agree the Lab 8 contract/runbook and Brett's observation tools; capture normal
   behavior with frozen definitions and workload before injection.
3. Prepare the isolated tagged rehearsal, preserving normal service routing.
4. Perform the controlled incident and recovery only in the agreed session.
5. Preserve fresh cloud identity, behavior and post-change logs as recovery proof.
