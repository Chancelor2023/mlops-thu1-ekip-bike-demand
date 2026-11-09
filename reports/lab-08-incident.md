# Lab 8 incident record: isolated model-directory fault

Status: **live incident and retained-state recovery observed; peer verification pending.**
Jerry executed the drill alone on 2026-11-09 because Mathis and Romain were unavailable.
He knew the fault. No independent blind diagnosis, live recorder participation by Romain,
or independent runbook execution is claimed. Preparation contributions remain attributed
to Romain (contract/runbook) and Mathis (collector, replacing Brett).

[Contract](lab-08-contract.md) | [Runbook](../RUNBOOK.md) |
[Evidence index](lab-08/drill-summary.md) | [Raw evidence](lab-08/drill-20261109T095859Z/)

## 1. Context and isolation

- Project `mlops-ece-group2`, region `europe-west1`, service `mlops-thu1-ekip-bike-demand`.
- Dedicated URL: `https://lab8---mlops-thu1-ekip-bike-demand-jdc2acx6uq-ew.a.run.app`.
- Production routing was explicitly pinned to `mlops-thu1-ekip-bike-demand-00018-rng`.
  Only the `lab8` tag was moved for the incident. Captured routing agrees with this;
  this is not a claim of continuous production health monitoring.
- Retained accepted model: `baseline-4df84bfe8121`; served code:
  `ea37b8a45d4a6738585d9de7d0f95d624ad1d3be`.
- Fault and reference use the same pinned image digest `sha256:bbf02e7850f3c282a1cda39d539f59459856cd541d81c713fbdebb19f8f3dd3f`.
- Collector source: `08b19816f1844293a7def88e0c64b293e097caba`, not peer-reviewed at execution.
- All phases used the same frozen validation payload bytes, SHA-256
  `7bce55409325391e49599f0b8e0ef51378c667d586f4f966d33b3dc8ccd92d91`.
- The team proceeded without instructor confirmation. Only one accepted model exists:
  this demonstrates recovery of retained state, not a two-accepted-version handoff.
  Contract signatures have not been filled retroactively.

## 2. Timeline (UTC, 2026-11-09)

Reconstructed afterwards from captured timestamps and command logs; not recorded live
by Romain. Paths below are relative to the raw evidence directory linked above.

| Time | Event | Evidence |
|---|---|---|
| 10:22:04.194745–10:22:38.893300 | Normal phase, Jerry; 30 successful predictions | `baseline/observations_normal_20261109T102204194163Z.jsonl` |
| 16:07:19.963495 | Private fault plan recorded | `private/fault-plan.json` |
| 16:35 / 16:46 | First local rehearsal failed; second passed with direct Python launch | `private/local-rehearsal-*/result.json` |
| 16:59:14.103447 | Fault revision preparation started, without traffic | `private/cloud-staging/deployment-started-at.txt` |
| 17:12:09.010203 | Solo execution and missing blind diagnosis recorded | `private/solo-preparation-20261109T171207065288Z/solo-execution-note.json` |
| 17:13:13–17:13:49 | First activation attempt interrupted by Ctrl+C; tag activation shown in output; restore command succeeded; no observation lot | `incident/`; `private/restore-routing-20261109T171346223018239.log` |
| 17:16:13–17:16:14 | First watchdog repeated restore successfully | `private/restore-routing-20261109T171613032486019.log` |
| 17:20:17–17:20:23 | Second activation command, exit 0 | `incident-02-20261109T172006107121Z/activation-*.txt` |
| 17:20:23.775409 | Incident collection starts | incident JSONL, `phase_start` |
| 17:20:38.826218 | First signal: initial health read timed out | incident JSONL, `signal` |
| 17:21:20.173280 | Incident collection complete, exit 2 | incident JSONL, `summary`; `observer-exit.txt` |
| 17:21:20–17:21:23 | Script immediately restores reference routing, exit 0 | `private/restore-routing-20261109T172120204308967.log` |
| 17:22:26.105967–17:23:01.313689 | Fresh recovery collection, exit 0 | `recovery/observations_recovery_20261109T172226105404Z.jsonl` |
| 17:23:17–17:23:19 | Second watchdog repeated restore successfully | `private/restore-routing-20261109T172317945442031.log` |
| 17:25 | Incident/recovery Cloud Run log correlation collected | phase `cloud-correlation-*.proof.json` and raw logs |
| 17:28:45.371770 | Healthy service template verified after no-traffic cleanup | `cleanup/20261109T172836143229Z/cleanup-verification.json` |
| 17:30:00.373715 | Stored object generations and downloaded hashes verified unchanged | `final-storage-verification/20261109T172952362546Z/storage-verification.json` |

The second activation-start to restore-command-success window is **66 seconds**.
This is a conservative command-level window, not an exact measurement of routing
propagation or outage duration. The first attempt has a separate 36-second command
window and no measured incident workload. Neither attempt is hidden or merged into
the other's observations.

## 3. Three periods, same workload

| Measure | Baseline | Incident (second attempt) | Recovery |
|---|---|---|---|
| UTC start | 10:22:04.194745 | 17:20:23.775409 | 17:22:26.105967 |
| UTC end | 10:22:38.893300 | 17:21:20.173280 | 17:23:01.313689 |
| Elapsed seconds | 34.699 | 56.398 | 35.208 |
| Valid successful / attempted | 30/30 (100%) | 0/30 (0%); all 30 HTTP 503 | 30/30 (100%) |
| Invalid rejected with 422 | 3/3 | 3/3 | 3/3 |
| Usable health checks | 2/2 | 0/2: initial read timeout, final 503 | 2/2 |
| Client timeouts | 0 | 1 health timeout, no usable request ID | 0 |
| Successful valid HTTP latency median / p95 / max, ms | 45.61 / 66.523 / 70.6 | Not applicable: no successful predictions | 58.19 / 76.6935 / 108.31 |
| Request-ID/status/identity/revision correlations | 35/35 | 34/35; timeout not correlated | 35/35 |
| Observed serving revision | `00018-rng` | `lab8-fault-67f152fd40` | `00018-rng` |
| Collector exit | 0 | 2 (completed, unhealthy phase) | 0 |

Latency is descriptive HTTP latency of successful valid predictions. A fast 503 is
not an improvement. No Lab 7 `model.predict` threshold, quality score, test-period
metric or cold-start conclusion is inferred. A separate pre-baseline production health
probe took 46916.29 ms; its cause remains unknown (see baseline summary).

## 4. First signal and technical explanation

At 17:20:38.826218 UTC, the collector emitted
`health_unusable_or_identity_mismatch` after a read timeout on the tagged `/health`.
This response establishes unavailability to the client, not a server HTTP status or
revision identity. Its request ID is null; the log-correlation script's `passed`
result explicitly permits this case and must not be described as 35/35 correlation.
The timeout's precise cause is not established. Subsequent observations establish
30 prediction HTTP 503s and a final health HTTP 503 on the faulty revision.

## 5. Competing explanations checked retrospectively

These are evidence comparisons by an injector who knew the fault. They are **not**
two hypotheses independently proposed or tested by Mathis during a blind diagnosis.

| Explanation | Discriminating evidence | Actual result and limit |
|---|---|---|
| Different application release/image caused prediction failures | Compare fault/reference image and request log code revision | Same pinned image and served code; weakens a changed-release explanation. Does not explain the initial timeout. |
| Accepted bucket files were replaced or corrupted | Compare recorded pre/post generations and generation-pinned downloaded hashes | Both files unchanged; rejects replacement of the accepted stored bytes in these checks. No loaded-memory hash is available. |
| Configured model path points outside the retained bundle | Compare revision specs, mount and MODEL_DIR; compare behavior before/after restoring tag | Only spec difference is `MODEL_DIR=/app/artifacts/lab8-missing-67f152fd40`. Fault requests report null model identity and 503; retained target succeeds. Supports configuration/model-unavailability diagnosis. |
| Frozen valid inputs became invalid | Same payload SHA across phases; status separation | Valid inputs get 503 during incident, 200 after recovery; deliberate invalid inputs remain 422 throughout. |

## 6. Actual fault and response

Jerry's retained plan has SHA-256
`d16e9a43d2ac64d77b0e07fa49c545f25f8d59e04ece15fe5e92575bb0850066`.
The fault revision overrides only `MODEL_DIR`, pointing to a missing directory under
the mounted artifacts path. Image, mount, resources, port, service account and other
revision-spec fields match the retained target. The default image command was retained.
The revision's TCP Ready condition did not establish usable model loading.

The script armed a detached restore process before activation, used bounded commands
and observation time, and restored both production=100% and the `lab8` tag to the
verified retained target after collection. The watchdog subsequently repeated the
same restore. No training, model promotion, bucket edit, IAM change or revision deletion
was performed as the repair. Scripts and restore logs are retained under `private/`;
that directory name describes their pre-drill handling, not an ongoing secret.
The immutable plan still says `planned_not_executed`; staging still says
`incident_activated=false`. These are historical snapshots, not final status files.

## 7. Recovery verification and template cleanup

Fresh tagged HTTP requests established health 2/2, valid 30/30, invalid 3/3, correct
model/code and finite nonnegative predictions. All 35 request IDs/statuses/model/code
values match Cloud Run logs for `00018-rng`. Captured post-recovery routing also points
production and `lab8` to that target. Together these support the technical recovery
claim; command success alone was not used to declare it. Review and human sign-off
remain pending; no retroactive independent declaration time is invented.

Moving the tag back left the service template with the faulty MODEL_DIR. Cleanup
therefore used the same pinned image with `--remove-env-vars=MODEL_DIR --no-traffic`,
creating `mlops-thu1-ekip-bike-demand-lab8-clean-877ded52e9`. Its spec and the service
template match the healthy reference, and Ready is true. It was not HTTP-tested or
routed to users. Production and `lab8` remain on `00018-rng`; the cleanup revision is
not a new accepted model. Final recorded bucket generations/hashes are unchanged.
A separate production HTTP check after the second incident is absent; root health
was captured after the first interrupted attempt. Do not claim continuous production
availability or infer a production request from a tagged request.

## 8. Rehearsals, runbook corrections and limitations

- First offline local rehearsal failed during `uv run` bootstrap: resolving `uv-build`
  required PyPI while network was disabled; API never started. Retained as a failed
  prerequisite attempt, not evidence of the planned model-directory fault.
- Second local rehearsal passed with installed Python/uvicorn directly: health 503,
  valid prediction 503, invalid input 422, container stopped, no OOM. It did not test
  the image's default command offline. Cloud injection used the original command.
- Collector fixes and tests precede this evidence: authentication, model/code identity,
  exit codes and request IDs; user-reported local validation was 226 tests passed with
  two dependency deprecation warnings. No new test run is claimed by this report.
- A timeout may have no returned request ID; retain it without inventing a correlation.
- Returning traffic does not repair the service template. The runbook now includes
  template cleanup and explicit verification of production routing.
- Only one accepted model exists; no two-version handoff, independent blind diagnosis,
  independent peer runbook attempt, or final peer approval has been demonstrated.
- No cloud startup-log extract proving the exact load exception is included; config,
  behavior, request logs and retained local rehearsal support the technical explanation.

## 9. Final review still required

Romain is the proposed final reviewer. He should inspect the latest PR commit/CI,
verify the recorded limits and leave one actionable observation. Jerry records the
response and any rerun. No approval or signature is filled on Romain's behalf.
Codex assisted with collector corrections, execution scripts, archive verification
and report drafting; Jerry executed the Cloud Shell operations. Independent reviewer
execution of the runbook remains unperformed and must be recorded if later attempted.
