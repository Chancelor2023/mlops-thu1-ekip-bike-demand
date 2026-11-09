# Lab 8 incident record

Recorder: Romain. Operator: Mathis (proposed replacement for Brett). Injector: Jerry. Final verifier: Romain.
Status: **template, no drill performed yet.** Every value below is filled from raw evidence
during or after the drill; nothing is pre-filled with an expected result. An empty cell
means "not observed". Rules and definitions: [lab-08-contract.md](lab-08-contract.md).

## 1. Context at the start

| Item | Observed value | Evidence file |
|---|---|---|
| Drill evidence folder | `reports/lab-08/drill-<UTC>/` | |
| Contract signed (section 14) | | |
| Instructor answer on scope (contract §2) | | |
| Production traffic pinned to target (UTC, revision, %) | | |
| Target live re-check: revision Ready, image digest, env, mount | | |
| Stored objects: generations + SHA-256 | | |
| `lab8` tag URL and revision before the drill | | |
| Frozen payloads: `instant` list and SHA-256 of files | | |

## 2. Timeline (UTC)

One line per event, written at the time it happens. Never rewritten afterwards; a correction
is a new line that references the earlier one.

| # | Time (UTC) | Who | Event / check | Raw evidence |
|---|---|---|---|---|
| 1 | | | baseline start | |

## 3. Three periods (same workload and definitions)

| | Baseline | Incident | After recovery |
|---|---|---|---|
| UTC start / end, real duration | | | |
| Revision behind the `lab8` URL | | | |
| Identity from `/health` (model, code) | | | |
| `/health` usable (start, end) | | | |
| Valid attempts sent / planned | / 30 | / 30 | / 30 |
| Valid successes (count, %) | | | |
| Invalid rejected with 422 | / 3 | / 3 | / 3 |
| Timeouts / connection errors | | | |
| HTTP latency of successes, ms (median / p95 / max) | | | |
| Cloud Run log events matching request IDs | | | |
| Production `/health` and routing | | | |

Differences between periods (time of day, cold starts, cohort) and how they affect the
comparison: _to write after the drill._

## 4. First signal

| Field | Value |
|---|---|
| Signal (what was observed) | |
| UTC time | |
| Affected scope (URL/tag, path) | |
| Revision / identity observed | |
| Rule that fired (3 consecutive failures, identity, `/health`) | |
| Raw evidence (file, request ID) | |
| Interpretation (hypothesis to test, not a cause) | |

If the signal was missed or late, write it here: it is a result.

## 5. Hypotheses and checks (at least two)

| Hypothesis | Expected observation if true | Discriminating check | Actual result (UTC, evidence) | Conclusion | Remaining uncertainty |
|---|---|---|---|---|---|
| A | | | | | |
| B | | | | | |

Rejected hypotheses and inconclusive checks stay in this table.

## 6. Boundaries checked

| Boundary | Checked? | What was compared | Supports the diagnosis? |
|---|---|---|---|
| Service: revision, image digest, traffic/tags | | | |
| Model: version, stored bytes, generations | | | |
| Configuration: env, mount, resources, port | | | |
| Inputs: payload validity, schema | | | |

## 7. Diagnosis

- Diagnosis recorded by Mathis at (UTC):
- Statement:
- Evidence it rests on:
- What it does not explain:

## 8. Fault reveal (Jerry, after section 7 is timestamped)

- Dated note reference (time it was written):
- Exact change, UTC time injected, how it was reverted:
- Diagnosis vs actual fault: match / partial / mismatch, and why.

## 9. Response

- Why rollback fits this fault (or why another response was chosen):
- Target used and compatibility checks passed (reference RUNBOOK §4):
- Command, UTC time, exit code (no token):
- Active fault duration (injection → rollback):
- What could still fail:

## 10. Recovery verification

| Source | Expected (contract §11) | Observed | Evidence |
|---|---|---|---|
| Identity | target of contract §3 | | |
| Behaviour | `/health` 2/2, valid 30/30, invalid 3/3 → 422 | | |
| Post-change signals | recovery request IDs in Cloud Run logs, matching status/identity | | |

Observation window: . How the three sources agree: .
Recovery declared: yes / no, by whom, at (UTC).

## 11. What we know, what we do not

- Observed:
- Unknown / not established:
- What evidence would falsify the recovery claim:
- Next actions (owner, concrete blocker):

## 12. Runbook use and corrections

| RUNBOOK step | What Mathis did | Missing or ambiguous instruction | Correction (commit) |
|---|---|---|---|
| | | | |

## 13. Final verification (Romain)

| Observation (contradiction, missing proof, non-reproducible step) | Author response | Recheck result |
|---|---|---|
| | | |
