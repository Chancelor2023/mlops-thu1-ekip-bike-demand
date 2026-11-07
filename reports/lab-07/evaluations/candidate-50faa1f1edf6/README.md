# Candidate 02: observed rejection and accepted-state preservation

Jerry executed the second declared configuration (200 trees, max_depth 10,
random_state 42, n_jobs 1) from clean personal-branch commit
`5cb80324df5caa7d83cd775907274060f906db2c`. This commit includes the
per-repeat latency evidence correction but was not merged/reviewed main at the
time of the experiment. No promotion was attempted.

The metadata timestamp is `2026-11-07T20:37:07.174386+00:00`, not an exact
command start time. Local Docker image identity and its CODE_REVISION are
retained in [image-inspect.json](image-inspect.json).

| Observed quantity | Value |
|---|---|
| Candidate | candidate-50faa1f1edf6 |
| MLflow run | daa7e6964bc94f0cb09527da64240576 |
| Decision / exit | rejected / 2 |
| Candidate validation MAE | 86.6918618844724 |
| Accepted validation MAE | 86.84685685591091 |
| Train-mean validation MAE | 154.23179306864967 |
| Candidate median p95, ms | 25.538313900051435 |
| Accepted median p95, ms | 7.382474600262867 |
| Latency ratio / maximum | 3.4593161890651265 / 1.25 |
| Failed check | performance |

Every other mandatory gate check passed. Quality improvement does not override
the operating criterion. Latency measures warm in-process model.predict, not
HTTP or Cloud Run cold starts. The execution command used 2 CPU / 2g memory,
20 warm-ups, 100 sequential calls per repeat and 3 repeats, as for the pilot.

## Retained repetitions and limits

Candidate p95s (ms): 27.315712199879272, 25.538313900051435,
24.995795300264945. Accepted p95s (ms): 14.994433850461064,
7.110802450006304, 7.382474600262867. The first accepted repetition is much
higher than the others; repeat stability and the cause of this variation have
not been established. No timing was removed, reconstructed or substituted.

## Preservation and verification scope

The [before hash record](before-sha256.txt) and
[after checksum log](after-checksums.log) record unchanged current.json,
accepted model/metadata, policy and configuration. Actual omitted model bytes
and current.json were not independently rehashed from this archive.

The service captures and [preservation record](service-preservation.json) agree:
revision `mlops-thu1-ekip-bike-demand-00018-rng` retained 100 percent traffic;
health continued to announce `baseline-4df84bfe8121` and
`ea37b8a45d4a6738585d9de7d0f95d624ad1d3be`. The legacy API does not expose
the loaded model's hash, so no in-memory digest verification is claimed.

Candidate metadata/metrics hashes agree with [decision.json](decision.json).
The image ID and CODE_REVISION agree with the execution records. [SHA256SUMS](SHA256SUMS)
covers all 17 original archive members, preserved without modification.
Model binaries and MLflow remain on the execution host, outside Git.

## Source archive

`candidate-02-20261107T203537Z-evidence.zip`

SHA-256: `93b3e450093c7e318f015dd601ed62afb40de42893c08befd15d703246ac8b64`
