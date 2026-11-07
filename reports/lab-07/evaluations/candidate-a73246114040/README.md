# Candidate 01: observed rejection and accepted-state preservation

This is the first real declared candidate attempt, executed by Jerry in Cloud
Shell using the image built from reviewed main commit
`8c5f89e2562482e605216005e3c3d2b7c2a474f0`. It predates the per-repeat
latency evidence correction in `8938df6`; these historical files are unchanged.
The model metadata timestamp is `2026-11-07T20:02:36.952998+00:00` (not the
start time of the command). Configuration: 100 trees, max_depth 10, seed 42,
n_jobs 1. Budget used so far: one declared candidate execution.

| Observed quantity | Value |
|---|---|
| Candidate | candidate-a73246114040 |
| MLflow run | bab0d2bc90ed4fd79b43a11d70301358 |
| Decision / exit | rejected / 2 |
| Candidate validation MAE | 86.74306881621092 |
| Accepted validation MAE | 86.84685685591091 |
| Train-mean validation MAE | 154.23179306864967 |
| Candidate median p95, ms | 13.844112050151123 |
| Accepted median p95, ms | 10.112879650068862 |
| Latency ratio / maximum | 1.3689584499363496 / 1.25 |
| Failed check | performance |

All other mandatory gate checks passed. Quality improvement does not override
the failed operating criterion. No promotion or deployment followed this attempt.

## Evidence and verification scope

- [decision.json](decision.json), [metrics.json](metrics.json),
  [model metadata](model-metadata.json) and [pipeline log](pipeline.log)
  retain the observed outcome, identities and validation context.
- [before-sha256.txt](before-sha256.txt) and
  [after-checksums.log](after-checksums.log) record unchanged current.json,
  accepted model, accepted metadata, policy and candidate configuration.
  The archive does not contain model binaries or current.json; this is retained
  command evidence, not a fresh independent rehash of those omitted files.
- Service captures before/after record the same revision
  `mlops-thu1-ekip-bike-demand-00018-rng` at 100 percent traffic.
  Health captures announce baseline-4df84bfe8121 and code revision
  `ea37b8a45d4a6738585d9de7d0f95d624ad1d3be` unchanged. This legacy API does
  not expose the hash of the model loaded in memory.
- Policy, metrics and candidate-metadata hashes were checked against the gate
  decision; configuration and policy match the before-execution hash record.
  [SHA256SUMS](SHA256SUMS) covers all 17 original archive members.
  `.gitattributes` preserves their bytes across operating systems.
- Candidate model bytes and the MLflow store remain outside Git on the execution
  host; this evidence directory alone is not a recoverable candidate bundle.

## Latency limits

The command used the same container limits as the pilot: 2 CPU and 2g memory.
The timer measures warm in-process model.predict on a single validation sample,
not HTTP latency or Cloud Run cold starts: 20 warm-ups, 100 sequential calls
per repeat, 3 repeats, median of the p95s.

The pilot medians were 6.467662050090439, 6.81404520007618 and
6.906381450198751 ms. The accepted-model median during candidate evaluation
was 10.112879650068862 ms. Stability across executions is therefore not
established; no cause for the difference has been demonstrated. Individual
repeat p95s from this candidate evaluation were not retained by the historical
gate and must not be reconstructed. The later correction retains them for future
evaluations without changing the comparison or threshold.

## Source archive

`candidate-01-20261107T195823Z-evidence.zip`

SHA-256: `069981fdc4e8faeb72bf253cc76055c95f75f7b90866e59282e9dcefb3e36e1f`
