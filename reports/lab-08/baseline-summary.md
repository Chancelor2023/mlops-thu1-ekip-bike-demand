# Lab 8 normal-phase evidence — 9 November 2026

Observed by Jerry from Cloud Shell, using collector commit
`08b19816f1844293a7def88e0c64b293e097caba` (not yet peer-reviewed at execution).
Mathis and Romain were unavailable for the coordinated incident session. This
record establishes the normal HTTP phase and its log correlation, not an incident,
independent diagnosis, successful rollback or complete Lab 8.

| Quantity | Observed |
|---|---|
| URL | https://lab8---mlops-thu1-ekip-bike-demand-jdc2acx6uq-ew.a.run.app |
| Revision | mlops-thu1-ekip-bike-demand-00018-rng |
| Model | baseline-4df84bfe8121 |
| Code served | ea37b8a45d4a6738585d9de7d0f95d624ad1d3be |
| UTC start | 2026-11-09T10:22:04.194745+00:00 |
| UTC end | 2026-11-09T10:22:38.893300+00:00 |
| Elapsed | 34.699 seconds |
| Valid predictions | 30/30 successful; finite, nonnegative, expected version |
| Invalid requests | 3/3 HTTP 422 |
| Health | 2/2 usable with expected model and code |
| Latency of successful valid requests | median 45.61 / p95 66.523 / max 70.6 ms |
| First signal | none |
| Exit | 0 |
| Cloud log correlation | 35/35 unique IDs; matching status, model, code and revision |

## Independent checks performed on the downloaded archive

All 31 recorded file hashes were checked. Raw responses, successful-request latency
statistics and all 35 client/cloud pairs were independently checked. Frozen inputs
match validation rows with selected instants 8821, 9484, 9557, 10008, 10256, 10852,
11594, 12582, 12897 and 12914. Payload SHA-256:
`7bce55409325391e49599f0b8e0ef51378c667d586f4f966d33b3dc8ccd92d91`.

The captured routing explicitly pins normal traffic at 100 percent on 00018-rng;
the lab8 tag also targets that revision. The production and tagged health probes
before the measured phase returned the expected identity. This is not continuous
production monitoring; a fresh post-incident production check remains necessary.

One pre-baseline production health request took 46916.29 ms, between
10:18:38.486503 and 10:19:25.402739 UTC. That observation is retained separately
in preparation/production-health-tag-ready.json. Its cause is not established;
do not label it a proven cold start or include it in the 30-prediction latency
population. This baseline does not establish cold-start performance or an SLA.

## Scope and pending work

The team decision reported by Jerry to proceed without instructor confirmation
is recorded in preparation/scope-decision.json at 10:44:02.756089 UTC. Recovery
would restore the retained accepted state, not switch between two accepted models.
The missing two-version handoff remains explicit, not instructor-approved.

Stored-object generation/hash checks are retained, but model binaries are excluded
and the legacy API exposes no loaded-model hash. No injection, incident diagnosis,
recovery phase, independent runbook attempt or final review has occurred here.
The signature/role confirmation table is not filled retroactively by these results.

Baseline timeline entries were reconstructed from the captured records afterwards;
no contemporaneous recorder participation by Romain is claimed.

## Source archive

`lab8-drill-20261109T095859Z-baseline-evidence.zip`

SHA-256: `936f6a66fc2872a549430a1899720a25cdb1719d6dca6d741599a706248b6442`

Original members and SHA256SUMS are preserved under
[drill-20261109T095859Z/](drill-20261109T095859Z/).

## Later execution

This page records the baseline-only checkpoint. A live solo incident, recovery and
template cleanup were subsequently performed on the same day. Their evidence and
remaining limitations are in [drill-summary.md](drill-summary.md). The baseline's
historical scope statements above do not describe the final drill status.
