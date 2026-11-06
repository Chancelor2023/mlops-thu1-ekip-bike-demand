# Lab 7: Cloud Build and manual deployment handoff

Owner/operator: Jerry. Reviewer: Mathis, using screen sharing for cloud operations.
Jerry is the only team member with cloud access under the instructor's setup.

## Trigger observed on 2026-11-05

| Field | Observed value |
| --- | --- |
| Project | `mlops-ece-group2` |
| Trigger location | `global` |
| Trigger ID | `bd29fb61-b91a-43b1-8fc4-8668e4fbc772` |
| Trigger name | `rmgpgab-mlops-thu1-ekip-bike-demand-europe-west1-Chancelor20jfw` |
| Repository | `Chancelor2023/mlops-thu1-ekip-bike-demand` |
| Push branch | `^main$` |
| Build configuration | `cloudbuild.yaml` |
| Disabled | `false` |
| Cloud Run region | `europe-west1` |

These values were reported from Jerry's Cloud Shell inspection. The trigger's
location is distinct from the Cloud Run service's region. The raw trigger list
remains in Jerry's Cloud Shell capture; it is not included here because the
project is shared with other teams.

## Prepared repository change

`cloudbuild.yaml` keeps image construction, `GIT_SHA=$COMMIT_SHA`, publication
and image output. Its automatic `Deploy` step has been removed on Jerry's branch.
The trigger itself has not been edited or disabled. Existing unused trigger
substitutions remain permitted by `ALLOW_LOOSE`.

After review and merge, the trigger will read the updated file from main. This
change does not modify current traffic or model files. It has not yet been
verified by a cloud build. Other teams' triggers are outside this change.

## Verification after merge

1. Jerry captures the team's traffic and health before merge.
2. Mathis reviews the diff and the PR checks before merging.
3. Jerry retains the actual build ID and log. Confirm Build and Push complete,
   no Deploy step executes, and record the published image digest.
4. Compare traffic and serving identity before/after. Main advancing is not
   expected to advance the live code revision automatically anymore.

Keep the before/after evidence and report discrepancies rather than claiming
a successful verification based only on this configuration.

## Manual deployment implemented locally; live verification pending

`src/bike_demand/deploy.py` provides plan, no-traffic deployment and explicit
activation/finalization. The API verifies and reports the exact loaded model
digest. Cloud calls are simulated in tests. No live candidate deployment or
traffic switch has been performed as part of this implementation.
Follow [operator-guide.md](operator-guide.md) after code review/merge.

The implementation and eventual live verification cover:

- Use a reviewed main commit and an image pinned by digest, not a moving tag.
- Require real gate evidence and revalidate the staged candidate bytes.
- Store each model bundle under its own versioned prefix; never replace the
  root model files used by the existing revision.
- Bind each new revision to that bundle, deploy without production traffic
  and verify it through a revision tag using authenticated requests.
- Verify expected code/model identity and bundle integrity before switching.
- Switch traffic explicitly only after approval; retain the previous image,
  model bundle, revision and recovery evidence.
- Reconcile the local current manifest and journal with the observed cloud
  result. A local preparation alone must never mark a model as deployed.

The existing baseline revision reads the bucket root. Its model files must
remain available while that revision is retained for recovery.
