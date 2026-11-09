# Lab 8 collector: execution and evidence

This document is a procedure, not a completed drill. Observation code is reviewed
before the cloud exercise. The contract's accepted-version/scope blocker remains
explicit; no tool correction approves or bypasses it.

## Prerequisites

Jerry has the only cloud access. Mathis prepares/operates the investigation,
without seeing the injected fault; Jerry executes his requested cloud checks.
Romain records the timeline and is proposed to verify Mathis's results afterwards.
Confirm the updated roles and sign-off before injection.

Use a fresh clean checkout of reviewed main, the verified recovery-target manifest
and the same frozen payload file in every phase. Capture its SHA-256 and source
validation instant list before baseline. The endpoint must be the agreed isolated
lab8 tag URL, verified from the fresh service description, with normal production
routing preserved. Expected identity comes from retained records, never by copying
whatever the observed endpoint currently claims. No command below creates a tag,
injects a fault, moves traffic or trains a model.

## One phase (Cloud Shell)

Set LAB8_URL to the independently checked tag URL, EVID to the chosen drill folder
and PHASE to normal, incident or recovery. These values must already be set.
Use one shared UTC timeline; the active-fault time box is independent of this
collector and can require interrupting it. Thirty sequential 15-second timeouts
could exceed five minutes; do not wait for all attempts before aborting the fault.

```bash
: "${LAB8_URL:?Set the verified lab8 tag URL first}"
: "${EVID:?Set the drill evidence directory first}"
: "${PHASE:?Choose normal, incident or recovery}"
export EXPECTED_MODEL=baseline-4df84bfe8121
export EXPECTED_CODE=ea37b8a45d4a6738585d9de7d0f95d624ad1d3be
export ID_TOKEN="$(gcloud auth print-identity-token)"
mkdir -p "$EVID/$PHASE"
printf '* -text\n' > "$EVID/$PHASE/.gitattributes"
set -o pipefail
python3 -u scripts/lab8_observe.py \
  --url "$LAB8_URL" --phase "$PHASE" \
  --expected-model-version "$EXPECTED_MODEL" \
  --expected-code-revision "$EXPECTED_CODE" \
  --timeout 15 --output-dir "$EVID/$PHASE" \
  2>&1 | tee "$EVID/$PHASE/observer.log"
OBSERVER_EXIT=${PIPESTATUS[0]}
printf '%s\n' "$OBSERVER_EXIT" > "$EVID/$PHASE/exit-code.txt"
printf 'Observer exit: %s\n' "$OBSERVER_EXIT"
unset ID_TOKEN
```

If the expected target changes, update the retained manifest and review the
expectations before the exercise; do not edit a completed phase to relabel it.
Do not enable shell tracing or print the token. The client refuses credentials in
URLs, token-bearing plain HTTP requests and HTTP redirects. For a local HTTP
rehearsal unset ID_TOKEN and record that it does not prove cloud authentication.

## Interpret the outcome

- 0: both health checks have HTTP 200, status ok, expected model and code (and
  optional loaded hash), all 30 valid predictions pass, and all 3 invalid requests
  return 422. This is only an HTTP phase result.
- 2: collection completed with failed checks. Normal/recovery are not verified;
  during incident this is a legitimate measured outcome. Keep the evidence.
- 3: incomplete collection/error/interruption. Keep partial JSONL and stderr,
  count actual attempts and record the reason. Do not replace the exit with zero.

Record code revision, payload SHA-256, actual UTC bounds, elapsed time, count and
first signal. Successful-response latency uses a linear-interpolated p95 and is
separate from errors; no latency threshold has been added.

For the legacy target, omit --expected-model-sha256: the field is absent and must
not be reconstructed. Preserve generation/SHA-256 stored-file checks separately.
If a later approved target exposes the loaded hash, pass its independently retained
expectation explicitly.

Finally correlate retained X-Request-ID values with post-change Cloud Run events,
verify actual revision/tag routing and production state, and fill the incident
record. The collector's summary alone cannot declare recovery.

## Offline validation

```bash
python -m pytest -q -m lab8
```

Transport, token, identity, failure signal, malformed-response and CLI tests use
synthetic responses without network access. CI includes these tests in the full
pytest run. No real incident or cloud recovery is implied by a passing test.
