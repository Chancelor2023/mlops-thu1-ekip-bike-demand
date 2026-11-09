# Lab 8 — Monitoring, Incident Diagnosis and Verified Recovery

## 1. Overview

Lab 8 focuses on preparing and documenting an incident-response exercise for the bike-demand prediction service. The team established an incident protocol, documented the recovery procedure, identified a recovery target and performed preliminary technical compatibility checks.

The report distinguishes preparation from the live solo Cloud Run drill subsequently executed by Jerry. Technical recovery is evidenced; independent blind diagnosis, peer runbook use and final review are not claimed.

## 2. Team contributions

### Romain — Lead and documentation

Romain coordinated the Lab 8 preparation and produced the main documentation:

- Created `reports/lab-08-contract.md`, defining the exercise scope, prerequisites, responsibilities and validation criteria.
- Defined the isolation strategy using a dedicated `lab8` tag, with production traffic explicitly protected.
- Specified the workload used for the exercise: 30 valid prediction requests and 3 invalid requests per phase, with frozen validation inputs.
- Defined the incident-detection criteria, including three consecutive failed valid predictions and immediate investigation in case of an unexpected service identity or unusable health endpoint.
- Documented the diagnostic methodology, requiring at least two plausible hypotheses and discriminating checks.
- Created `reports/lab-08-incident.md` as the incident record template.
- Prepared the structure for recording the timeline, observations, diagnosis, recovery and final verification.

### Jerry — Cloud preparation and recovery target

Jerry prepared the technical recovery reference and its supporting evidence.

The recovery target was identified as:

| Parameter | Reference |
|---|---|
| GCP project | `mlops-ece-group2` |
| Region | `europe-west1` |
| Service | `mlops-thu1-ekip-bike-demand` |
| Cloud Run revision | `mlops-thu1-ekip-bike-demand-00018-rng` |
| Model version | `baseline-4df84bfe8121` |
| Code revision | `ea37b8a45d4a6738585d9de7d0f95d624ad1d3be` |
| Container image | `sha256:bbf02e7850f3c282a1cda39d539f59459856cd541d81c713fbdebb19f8f3dd3f` |

Jerry's preparation included:

- Retrieving and preserving a versioned recovery archive.
- Checking the archive SHA256 and the checksums of the recovered model bundle.
- Checking the generation numbers and hashes of the stored model and metadata objects.
- Retrieving the target container image and checking its configuration.
- Checking the model directory, code revision and service resource configuration.
- Running local compatibility checks using the recovery image.

The local API checks returned:
- `/health`: HTTP 200, with the expected model and code identities.
- Valid prediction: HTTP 200, with a finite, non-negative prediction of `37.30960864135864`.
- Invalid request (`hr=24`): HTTP 422.

The evidence is stored in `reports/lab-08/`, including:
- `rollback-target.md`
- `rollback-target.json`
- `preflight-20261107T210602Z/health.json`
- `preflight-20261107T210602Z/revision-reference.json`
- `preflight-20261107T210602Z/archive-recovery-verification.json`
- `preflight-20261107T210602Z/live-storage-verification.json`

These checks establish the integrity of the retained recovery reference and its local compatibility. They do not represent a live Cloud Run recovery.

### Mathis — Operational and investigation preparation (taking over from Brett)

Mathis implemented the observation and diagnostic tooling in PR #38, taking over from Brett because Brett could not work due to a PC problem. This records the actual preparation contribution; a completed incident or investigation is not claimed.

Their work followed the contract's approach to:
- Observing service behavior through health checks and prediction requests.
- Distinguishing service, model, configuration and input-related failures.
- Building a diagnosis from observable evidence rather than immediately assuming the cause.
- Using multiple hypotheses and targeted checks to justify an incident diagnosis.
- Preserving the distinction between valid prediction failures and expected invalid-input responses.

Mathis was intended to act as investigator. He was unavailable during the actual solo drill; no diagnosis or runbook execution is attributed to him.

Romain is proposed to review the final incident evidence, rather than Mathis reviewing his own collector and diagnosis. That review is still pending and must check the retained target and fresh recovery evidence.

## 3. Recovery preparation and technical constraints

The team identified `baseline-4df84bfe8121` as the accepted model version associated with the recovery target.

The preparation also documented an important limitation: the target API does not expose a loaded-model hash. Consequently, model identity cannot be established from the Cloud Run revision alone. The stored model and metadata object generations and SHA256 hashes must also be checked.

The team additionally identified that the target revision reads model files from the bucket root. A revision reference therefore does not, by itself, pin the exact model bytes.

The contract records that only one accepted model version had been established at the time of preparation. The 18 Cloud Run revisions must not be confused with 18 distinct accepted model versions.

## 4. Runbook

The team documented the incident-response procedure in `RUNBOOK.md`.

It covers:
- Recognizing service, model-loading and prediction failures.
- Checking health responses, prediction responses and service identity.
- Investigating revision, image, configuration and artifact-storage compatibility.
- Comparing competing diagnostic hypotheses.
- Checking the recovery target before switching traffic.
- Using an isolated `lab8` tag for the recovery procedure.
- Verifying recovery through fresh health checks, prediction requests and Cloud Run logs.
- Recording limitations and escalating when the available evidence is insufficient.

The runbook also distinguishes a service that is Ready at the infrastructure level from one whose model has actually loaded and is usable.

## 5. Lab 7 integration

The Lab 8 preparation builds on the Lab 7 work integrated through PR #34 and the candidate evaluations documented in PR #35.

The Lab 7 outcome recorded in the Lab 8 contract was:
- Two candidate models rejected because of latency.
- The accepted model preserved.
- A third candidate not run.

The recovery preparation therefore uses the retained accepted model rather than treating rejected candidates as accepted versions.

## 6. Evidence and scope

The repository contains the Lab 8 contract, runbook, incident-record template, recovery-target documentation and preflight verification files.

The available preflight evidence confirms:
- The expected recovery revision identity.
- The expected container image and configuration.
- The integrity of the retained recovery archive.
- The expected generations and hashes of the stored model files.
- Successful local API compatibility checks.

The normal phase was subsequently collected by Jerry on 2026-11-09 from
10:22:04.194745 to 10:22:38.893300 UTC (34.699 seconds), using collector commit
08b1981. It produced 30/30 successful valid predictions, 3/3 invalid rejections
and 2/2 usable health checks. All 35 IDs/statuses match the expected revision,
model and code in Cloud Run logs. Successful prediction latency was median
45.61 ms, p95 66.523 ms and max 70.6 ms. These are HTTP observations, not quality
scores or a cold-start benchmark. See [baseline summary](reports/lab-08/baseline-summary.md).

An earlier production health probe took 46916.29 ms; it is retained separately,
with no established cause. The team chose to proceed without instructor scope
confirmation, explicitly retaining the single-accepted-model limitation.
Mathis/Romain were unavailable for the incident session: baseline rows were
reconstructed from raw records, not attributed to their live participation.
Jerry subsequently executed the live incident and recovery alone; no independent
diagnosis was performed. See the execution results below.

## 7. Conclusion

The team established the technical and procedural foundations for Lab 8. Romain structured the exercise and documented the incident protocol, Jerry prepared and checked the recovery reference, and Mathis implemented the operational and diagnostic preparation in place of Brett.

The resulting documentation provides a defined recovery target, a structured investigation methodology, explicit safety boundaries and concrete technical evidence supporting the preparation.
## 8. Live solo drill and remaining requirements — 9 November 2026

Jerry executed the cloud operations and retained the raw evidence, assisted by Codex
for collector corrections, scripts, archive checking and report drafting. No live
recorder participation by Romain or blind diagnosis by Mathis is claimed.

- Fault: a separate revision using the retained image with only MODEL_DIR changed to
  a missing path; only the lab8 tag was moved, normal traffic explicitly pinned.
- The first activation was interrupted and restored; it has no observation workload.
- Completed incident: 30/30 valid HTTP 503 responses, 3/3 invalid HTTP 422 responses,
  initial health timeout and final health 503. Logs match the faulty revision for
  34/35 requests; the timeout has no usable request ID and is not correlated.
- Recovery: health 2/2 usable, valid 30/30 successful, invalid 3/3 rejected; all 35
  request IDs/statuses/model/code match the retained revision in Cloud Run logs.
- Successful recovery prediction HTTP latency: median 58.19 ms, p95 76.6935 ms,
  max 108.31 ms (30 observations); descriptive only, no cold-start/SLA conclusion.
- Second activation-start to restore-success command window: 66 seconds; exact
  routing propagation and outage duration are not separately measured.
- The faulty service template was repaired via a no-traffic cleanup revision of
  the same image. Production and lab8 remain on 00018-rng; no new model was accepted.
- Stored object generations and recorded generation-pinned downloaded hashes match
  the retained accepted bytes after the drill. No retraining was used for recovery.

[Incident record](reports/lab-08-incident.md), [drill summary](reports/lab-08/drill-summary.md)
and [raw evidence](reports/lab-08/drill-20261109T095859Z/) contain the actual timeline,
rehearsal failures, checks and limitations. The archive's 151 file hashes and raw
HTTP/log pairs were independently checked on the review PC. Root production health
was not separately sampled after the second incident; final routing is captured.

Remaining: Romain's review of the latest commit and CI, an actionable observation
and Jerry's response/rerun, and an independent peer attempt with the runbook if
performed. Blind diagnosis and the two-accepted-model handoff are not demonstrated;
no instructor scope confirmation was obtained. Do not describe the lab as fully
reviewed or create m4 on the basis of these technical checks alone. This root file
is the team preparation/execution report, not evidence of each member's private
personal week-4 submission.
