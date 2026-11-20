# Release v1.0.0 — Bike Demand

DRAFT ONLY: complete the release identity, latest CI and live deployment evidence
after merge and verification. Do not publish this draft unchanged.

## Change and owner

Team Ekip's hourly bike-demand API: validated temporal data splits, reproducible
training/tracking, container serving, CI, candidate quality/latency gates, retained
state recovery and final held-test evaluation. Jerry prepared the release identity
endpoint, documentation, model assets and local verification; normal team review
of the exact release revision remains required. Codex assisted with implementation,
tests, documentation and evidence/asset verification.

## Identities

- Release commit: pending the reviewed merge on main; tag must identify that commit.
- Accepted model: `baseline-4df84bfe8121`.
- Model SHA-256: `d24c050e3631d5b4c2feb8cb571bef6382d8c975c42a5c11edd28de78a0b8c07`.
- Metadata SHA-256: `b09c2b06b0a90b829c3d1a89c3d544f9d0020f0a74b22a4931e0e676596dbd8f`.
- Published release image tag and digest: pending Cloud Build for the release commit.

## Final evaluation and model choice

The preselected saved model achieved test MAE **93.73505906420367 rentals/hour**
on 4,376 observed hours, July–December 2012. Evaluated once on 13 November 2026,
without retraining, using evaluation code
`474a620de2ceeace6d0d7978c03cb8d7d10128ed`. See the repository's
`reports/final-evaluation/README.md` and raw results.

The baseline was retained before scoring the test: both evaluated candidates
slightly improved validation MAE but exceeded the frozen latency ratio of 1.25.
The test result was not used for further model selection or tuning.

## Verification

- Local Docker source `569f2920c0587912a5996bad70957a12fd6c8543`: 27 API tests
  passed; health/version identities matched the retained model with a read-only
  mount. Platform: Linux ARM64. See `reports/release/local-image-20261120T153721Z/`.
- Latest CI links for the final release commit: pending.
- Cloud Build ID, published image digest, deployment revision and routing: pending.
- Actual authenticated deployed `/version` output, plus health/prediction checks:
  pending. The historical Cloud Run revision does not expose this endpoint.

## Assets

- `accepted-model-baseline-4df84bfe8121.zip`: original accepted model and metadata,
  internal SHA256SUMS and README; no retraining.
- `accepted-model-baseline-4df84bfe8121.zip.sha256`: archive checksum.
- `final-presentation.pdf`: pending export and visual verification.

## Known limitations

Only one accepted model was established. Neither measured candidate was promoted;
there is no successful live candidate promotion or two-accepted-version handoff.
The incident recovery was executed solo with knowledge of the fault; independent
blind diagnosis and peer runbook execution were not demonstrated. Original model
training commit is unavailable. Timings do not establish a general SLA, cold-start
performance or stability across machines. Local image checks do not establish
cloud deployment. Positive historical COMMENTED reviews are not formal approvals.
