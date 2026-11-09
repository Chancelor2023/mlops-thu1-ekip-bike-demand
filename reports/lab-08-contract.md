# Lab 8 contract: monitoring, incident diagnosis and verified recovery

Lead: Romain. Contract reviewer: Jerry. Status: **draft for review**; validated only when the
four members have signed section 14 *before* any baseline observation or injection.

This contract fixes definitions and rules. It contains no observed result: what
actually happened is recorded in [lab-08-incident.md](lab-08-incident.md), and how to
act is in [RUNBOOK.md](../RUNBOOK.md).

## 1. Starting point and prerequisites

| Prerequisite | State | Evidence |
|---|---|---|
| Lab 7 merged on `main` | merged; the planned Mathis review of #35 was not completed | PR #34 (integration), #35 (candidate evaluations); do not equate merge with the missing peer review |
| Lab 7 outcome | two candidates rejected on latency; accepted model kept; third candidate not run | [lab-07-report.md](lab-07-report.md), [evaluations/](lab-07/evaluations/) |
| Recovery target named and reviewed | done (local compatibility only) | PR #36, [rollback-target.md](lab-08/rollback-target.md) |
| Live re-check of the target just before the drill | **pending** (Jerry) | to be stored with the drill evidence |
| Two distinct accepted versions (current + previous) | **missing: explicit blocker** | see section 2 |

## 2. Blocker: only one accepted version

The lab expects a current and a previous accepted version. We have one accepted model,
`baseline-4df84bfe8121`. The 18 Cloud Run revisions are not 18 accepted versions, and no
rejected Lab 7 candidate is relabelled as accepted to fill the gap.

Consequence for the drill: the fault is injected on an isolated tagged revision, and the
recovery restores the **retained accepted state** (section 3) on that tag. This
demonstrates notice, diagnosis and recovery to a verified retained state; it does not
demonstrate a handoff between two accepted model versions. The lead asks the instructor to
confirm this scope **before** the drill and records the answer here:

> Instructor answer: _pending_ (date, channel, wording).

## 3. Recovery target (fixed, from the reviewed record)

Source of truth: [rollback-target.json](lab-08/rollback-target.json). Never "the previous
revision" or `latest` without these checks.

| Field | Expected value |
|---|---|
| Service / project / region | `mlops-thu1-ekip-bike-demand` / `mlops-ece-group2` / `europe-west1` |
| Revision | `mlops-thu1-ekip-bike-demand-00018-rng` |
| Image | `…/mlops-thu1-ekip-bike-demand@sha256:bbf02e7850f3c282a1cda39d539f59459856cd541d81c713fbdebb19f8f3dd3f` |
| Code revision (`/health`) | `ea37b8a45d4a6738585d9de7d0f95d624ad1d3be` |
| Model version (`/health`, `/predict`) | `baseline-4df84bfe8121` |
| `model.joblib` SHA-256 / generation | `d24c050e…8c07` / `1792749083386751` |
| `model-metadata.json` SHA-256 / generation | `b09c2b06…bd8f` / `1792749083186741` |
| Configuration | `MODEL_DIR=/app/artifacts`, GCS FUSE read-only mount of `thu1-ekip-bike-demand-model`, 1 CPU, 512Mi, port 8000 |

Notes:
- The Lab 7 frozen reference recorded `00017-czt` (code `1ed240b`). `00018-rng` was created
  on 2026-11-05 by the auto-deploy of the #32 merge; serving code, dependencies and model
  are identical. `00017-czt` serves the same model and is **not** a second accepted version.
- The target API does not expose the loaded model hash. Model identity is therefore
  established by `model_version` plus the generation-pinned stored-object hashes.
- The retained revision reads bucket-root objects: a revision alone does not pin model
  bytes. Object generations and hashes are re-checked before the drill and after recovery.
- A checksum mismatch fails closed: the artifact is not loaded or relabelled, the drill stops.
  The target code (`ea37b8a`) does **not** verify the model hash at load time (only `main`
  does), so this guard is the external generation + SHA-256 check made before switching.

## 4. Roles (one shared timeline)

| Role | Member | Rule |
|---|---|---|
| Injector + Cloud operator | Jerry | Sole IAM access. Chooses one reversible fault, keeps its detail in a dated note readable by Romain, runs the checks Mathis asks for and shares raw results **without suggesting a cause**, performs recovery. |
| Operator (investigator) | Mathis | Investigates without knowing the fault, follows RUNBOOK.md without Romain dictating it, records the first signal and the hypotheses. |
| Recorder + lead | Romain | Keeps the UTC timeline in the incident record, owns this contract, the runbook and the report. Does not reveal the fault. |
| Final verifier | Romain | After the drill only: reconstructs the incident from the runbook and the files, leaves at least one concrete observation. |

The fault is revealed to Mathis only after his diagnosis is recorded (timestamped).

Role update proposed before the drill: Mathis delivered the observation tools in
place of Brett, whose PC was unavailable. Mathis leads the investigation; Romain
reviews the resulting evidence instead of Mathis reviewing his own collector and
diagnosis. Confirm this allocation in section 14 before injection. No signature
or completed independent review is implied by the update.

## 5. Isolation

- Our own service only, never another team's. Local rehearsal first is allowed.
- One dedicated Cloud Run tag `lab8`. The same tag URL is used for baseline, incident and
  recovery observations.
- **Before anything else**, production traffic is pinned explicitly to the target revision
  (it currently follows `latestRevision: true`), so a tagged deployment cannot take
  production traffic. Production routing and `/health` are checked before and after the drill.
- No accepted artifact overwritten or deleted, no change to the CSV, no retraining as a repair.

## 6. Fault rules

Exactly one reversible fault, of type **release, configuration or artifact access**, on the
`lab8` tagged revision only. It must be reversible by moving the tag back to the target of
section 3. The injector records the exact change, its UTC time and how it is reverted.

## 7. Workload (identical in every phase)

- **Valid inputs:** 10 observations from the validation period (2012-01-01 to 2012-06-30,
  `instant` 8646–13003), the 12 predictors only, in contract order; `cnt`, `casual`,
  `registered`, `instant` and `dteday` are never sent. Each observation is sent 3 times:
  **30 valid attempts**, sequential, 1 second apart.
- **Invalid inputs:** 3 deliberately invalid payloads (for example out-of-range `hr`, a
  missing field, a wrong type), counted separately.
- `GET /health` at the start and at the end of each phase.
- Payload files are frozen before the baseline: their list of `instant` values, the files
  and their SHA-256 are prepared by Mathis (taking over from Brett). The same files are reused unchanged.
- Client timeout per request: **15 s** (same as `check_service.py`).
- No metric is computed on the held test period (2012-07 to 2012-12).

## 8. Signal definitions

All signals are computed per phase, on the attempts of that phase only.

| Signal | Population (eligible) | Numerator | Denominator | Unit / window |
|---|---|---|---|---|
| Valid-prediction success | valid attempts actually sent | HTTP 200 **and** finite **and** ≥ 0 **and** `model_version` = expected | attempts actually sent (timeouts and connection errors count as failures) | count and %, phase UTC bounds |
| Invalid-input rejection | the 3 invalid attempts | HTTP 422 | 3 | count, phase UTC bounds |
| Health usability | the 2 `/health` calls | HTTP 200, `status=ok`, expected `model_version` and `code_revision` | 2 | count, phase UTC bounds |
| Identity | every `/health` and successful `/predict` | values equal to section 3 | — | mismatch flagged per response |
| HTTP latency (descriptive) | successful valid attempts | — | — | ms: median, p95, max; no threshold |

Missing data: attempts not sent are reported as missing (not imputed and not counted as
successes); the actual number sent, the UTC start/end and real duration are recorded.
Intentional rejections never enter the valid-prediction success rate. The Lab 7 +25 %
threshold is not reused: it measured `model.predict`, not HTTP. A fast 503 is not a
latency improvement.

## 9. Detection

- **Investigation trigger:** 3 consecutive failed valid predictions.
- **Immediate signal:** unexpected identity (`model_version` or `code_revision`) or
  unusable `/health` (non-200, timeout, `status` not `ok`).
- The first signal is recorded with its UTC time, affected scope (tag, path), observed
  revision/identity and a link to the raw response or log event. Raw evidence is never
  rewritten afterwards.

## 10. Diagnosis

- At least **two plausible hypotheses**. For each: expected observation, discriminating
  check, actual result, conclusion and what remains uncertain. Rejected hypotheses and
  inconclusive checks stay in the record.
- Boundaries checked, cheapest first: service (revision, image digest, traffic/tags),
  model (version, stored bytes and generations), configuration (environment, mount,
  resources, port), inputs (payload validity, schema). Unchecked boundaries are listed.
- A mismatch is evidence; the record explains whether it causes the symptom.

## 11. Recovery and its declaration

- Action: manual, by Jerry, move the `lab8` tag back to the target revision of section 3
  (no retraining, no new model). Production routing is not changed by this action.
- Then a fresh run of the same workload on the same tag URL.
- **Recovery is declared only if all hold:** identity equal to section 3; `/health` usable
  (2/2); **30/30** valid predictions successful; **3/3** invalid inputs rejected with 422;
  Cloud Run logs after the change show the recovery request IDs with matching statuses and
  identity. The observation window and how the three sources agree are written down.
- A successful command or a stopped alert alone does not prove recovery.

## 12. Time box and abort

Target: **at most 5 minutes of active fault.** If the diagnosis is incomplete at that point,
or an unexpected change appears, Jerry restores the target immediately. The real duration,
the abort and the limits of the diagnosis are recorded; an interrupted drill is a result,
not a failure to hide.

## 13. Evidence

- Raw files under `reports/lab-08/drill-<UTC start>/` with one folder per phase
  (`baseline/`, `incident/`, `recovery/`): responses, Cloud Run log extracts, `gcloud`
  outputs, stdout + stderr, exit codes, UTC bounds, `SHA256SUMS` and a `.gitattributes`
  with `* -text`.
- No identity token or secret is ever written to a file, log or screenshot.
- At most three screenshots, as a complement to raw files.
- Links: README (section Lab 8) → this contract, RUNBOOK.md, incident record, raw evidence;
  team report Lab 8 section → the same.

## 14. Sign-off (before the baseline)

| Member | Role | Agreed (date UTC) |
|---|---|---|
| Romain | lead, recorder, final verifier | |
| Brett | unavailable during preparation; any later contribution/review must be recorded | |
| Jerry | injector, cloud operator | |
| Mathis | observation tooling, investigator | |

## 15. Work order

Jerry/Mathis/Romain preparations in parallel → review of preparations → instructor scope
answer (section 2) → drill (three members) → incident record and runbook completed →
Romain's final verification → corrections and merges → annotated tag `m4` prepared by Romain with
a note listing remaining limits.
