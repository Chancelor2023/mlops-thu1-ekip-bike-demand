# Release v1.0.0 readiness — 20 November 2026

This is a preparation record, not a published Release or a declaration of full
course compliance. Deadline in the Week 5 brief: 22 November 2026 at 23:59.

## Established evidence

- Public team repository; last checked main:
  `da65ed82cbadbaa4ff7d37bc7d2b9e41b8663b63`.
- That main revision passed [quality-and-tests](https://github.com/Chancelor2023/mlops-thu1-ekip-bike-demand/actions/runs/43442611997/job/131943794828)
  and [container](https://github.com/Chancelor2023/mlops-thu1-ekip-bike-demand/actions/runs/43442611884/job/131943794869).
  These are historical checks, not checks of this documentation branch.
- [Final evaluation](final-evaluation/README.md): one saved-model held-test
  evaluation, MAE 93.73505906420367 on 4,376 rows; no retraining.
- [Candidate experiments](lab-07-report.md): both rejected by the frozen latency
  policy, so the original accepted model was retained.
- [Incident/recovery](lab-08-incident.md) and [demo rehearsals](demo-rehearsal.md)
  retain observed results and their limits.

## Work before publication

- [ ] Review the documentation changes on `release/v1.0.0`, push the branch and
  obtain CI results for its latest commit. Record any review observation and response.
- [ ] Resolve or disclose the Week 5 `/version` requirement. The existing route is
  `/health`; no `/version` route or instructor acceptance of substitution is established.
  An intentional API change needs its own tests/review and deployment evidence.
- [ ] Export the final slides to `final-presentation.pdf` and inspect the PDF.
- [ ] Package the trusted accepted model and metadata as a Release asset, verify
  their frozen hashes, and provide a `.sha256` checksum file. Keep binaries out of Git.
- [ ] Draft Release notes with the exact release commit, accepted model/version/hash,
  image tag and digest, final held-test result, latest CI links, dated deployment
  evidence, interface output and known limitations. Do not rerun the held test.
- [ ] After review and CI, merge the release branch into main; identify the exact
  commit to grade and tag it `v1.0.0`. Build/publish and verify any image claimed for
  that commit. Build/Push success alone is not evidence of deployment.
- [ ] Publish GitHub Release `v1.0.0` with the verified model bundle, `.sha256`
  and `final-presentation.pdf`; check access for the instructor `minhtc-uca`.

At the 20 November repository audit, no GitHub Release or `v1.0.0` tag existed;
only milestone tags m1 and m2 were present. A missing milestone must not be created
retroactively as proof of checks that were never performed.

## Identity to retain

Model: `baseline-4df84bfe8121`.

Model SHA-256:
`d24c050e3631d5b4c2feb8cb571bef6382d8c975c42a5c11edd28de78a0b8c07`.

Metadata SHA-256:
`b09c2b06b0a90b829c3d1a89c3d544f9d0020f0a74b22a4931e0e676596dbd8f`.

The final evaluation used code `474a620de2ceeace6d0d7978c03cb8d7d10128ed`.
The historical Cloud Run reference used code
`ea37b8a45d4a6738585d9de7d0f95d624ad1d3be` and revision `00018-rng`.
Neither is automatically the future Release commit. The original model's
training commit is unavailable in its legacy metadata; do not reconstruct it.

Known gaps: no successful real candidate promotion, only one accepted model,
no independent blind incident diagnosis or peer runbook execution, and no formal
APPROVED review established by the later positive COMMENTED reviews.
