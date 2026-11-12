# Lab 8 live drill evidence — 9 November 2026

Jerry executed the isolated Cloud Run drill alone. Technical recovery is supported
by fresh requests and Cloud Run request logs. Final peer review is pending; blind
diagnosis and an independent runbook attempt were not performed.

[Incident record](../lab-08-incident.md) | [Raw evidence](drill-20261109T095859Z/) |
[Independent download audit](drill-20261109T095859Z/download-audit.json)

| Phase | Valid successes | Invalid 422 | Usable health | Correlated requests |
|---|---|---|---|---|
| Normal (10:22 UTC) | 30/30 | 3/3 | 2/2 | 35/35 |
| Incident (17:20 UTC) | 0/30; all 503 | 3/3 | 0/2 | 34/35; initial health timeout has no usable ID |
| Recovery (17:22 UTC) | 30/30 | 3/3 | 2/2 | 35/35 |

Fault: only MODEL_DIR points to a missing directory in a separate tagged revision,
using the same pinned image. Normal production remains pinned to `00018-rng` in
captured routing. Second activation-start to restore-success command window: 66 s;
exact routing-propagation/outage duration is not measured. The first interrupted
attempt and both local rehearsals are retained separately.

The service template was subsequently repaired without traffic via cleanup revision
`lab8-clean-877ded52e9`; it has matching config/Ready evidence, no HTTP test. Final
model/metadata generations and recorded downloaded hashes match the retained target.
One accepted model is used; loaded-memory hash is not exposed. No separate root-URL
health check after the second incident is included, and there is no continuous
production-monitoring claim. See the incident record for all limitations.

## Archive and byte preservation

Source: `lab8-drill-final-evidence-20261109T173112486545Z.zip`.
SHA-256: `e9a03d3187ee1ef1d658ff2aa1ae3aec83f3eb7bd10dca780f5c566c5f33da86`.
All 151 manifest-listed files were checked, along with ZIP integrity and exact
membership (152 entries including the manifest). Original bytes are preserved;
`.gitattributes` disables text conversion. `FINAL-SHA256SUMS` mirrors the manifest;
`download-audit.json` records independent raw-response/log/spec checks. Pre-existing
baseline evidence remains intact. The package excludes model binaries and contains
no detected JWT or OAuth access-token strings; scripts reference tokens in memory.

The local check independently recalculated the successful-request median/p95/max
and checked all available request-ID/status/model/code/revision pairs. It verified
fault/cleanup specs and captured routing against rollback-target.json. Post-drill
model hashes are the cloud executor's recorded checks, not a rehash of absent model
bytes on the review PC. Historical plan/staging status files remain unchanged.

## Evidence directories

- `baseline/`: normal phase and its cloud log correlation.
- `incident/`: first interrupted activation, no observation workload.
- `incident-02-20261109T172006107121Z/`: completed incident and 34 log pairs.
- `recovery/`: fresh recovery workload, routing and 35 log pairs.
- `private/`: dated plan, solo decision, scripts, local rehearsals, staging and restore logs;
  disclosed after the solo drill, never presented as a blind peer diagnosis.
- `cleanup/`: no-traffic template repair and configuration/Ready checks.
- `final-storage-verification/`: unchanged generations and recorded downloaded hashes.

No new runtime change or cloud call was performed while importing this archive.

Archived Python diagnostic scripts are raw evidence. The evidence directory has a
local Ruff exclusion for those snapshots so lint/format cannot rewrite their bytes;
application, tests and maintained scripts retain the normal repository checks.
