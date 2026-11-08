
# Lab 8 — Diagnostic Checklist

## 1. Incident identification

- [ ] Record the UTC timestamp of the first observed failure.
- [ ] Record the UTC timestamp when the investigation starts.
- [ ] Identify the affected endpoint.
- [ ] Record the HTTP status codes and error messages.
- [ ] Check whether three consecutive valid prediction attempts have failed.
- [ ] Check whether `/health` is still usable.
- [ ] Record the model version and code revision returned by the service, when available.
- [ ] Record the actual number of attempts executed.

An unexpected model identity or unusable health endpoint must be reported immediately.

## 2. Initial observations

Before proposing a cause, collect:

- [ ] Initial `/health` response.
- [ ] Last successful prediction, if available.
- [ ] First failed prediction.
- [ ] Consecutive failure count.
- [ ] HTTP status codes.
- [ ] Request durations.
- [ ] Error messages.
- [ ] Model identity information.
- [ ] Relevant structured logs.

Do not modify the service or accepted artifacts during diagnosis.

## 3. Hypothesis investigation

At least two plausible hypotheses must be investigated.

For each hypothesis, document:

- Hypothesis.
- Expected observation if the hypothesis is correct.
- Discriminating check.
- Actual result.
- Conclusion: confirmed, rejected or inconclusive.
- Supporting evidence.

### Hypothesis 1 — Model artifact unavailable or unreadable

Possible explanation: the deployed service cannot access or load the expected model artifact.

Expected observations:

- `/health` may return HTTP 503.
- Logs may report model loading or artifact access errors.
- Predictions may fail because the model is unavailable.

Discriminating checks:

- Inspect the `/health` response.
- Inspect startup and application logs.
- Check the deployed revision's configured model artifact location and access permissions, if available.

Actual result:

_To be completed during the exercise._

Conclusion:

_To be completed during the exercise._

### Hypothesis 2 — Deployed revision or model identity mismatch

Possible explanation: the service is running a different revision or model version from the verified accepted target.

Expected observations:

- Unexpected model version.
- Unexpected code revision.
- Different model SHA256, if exposed.
- Traffic may be routed to an unexpected Cloud Run revision.

Discriminating checks:

- Inspect `/health`.
- Inspect the Cloud Run revision receiving traffic.
- Compare the deployed image digest and available model identity information with the verified recovery target.

Actual result:

_To be completed during the exercise._

Conclusion:

_To be completed during the exercise._

### Hypothesis 3 — Request validation or API contract issue

Possible explanation: the requests do not satisfy the API input contract.

Expected observations:

- HTTP 422 for invalid payloads.
- Validation errors identifying missing, extra or out-of-range fields.
- Valid requests may succeed if only specific payloads are malformed.

Discriminating checks:

- Confirm that valid payloads contain exactly the 12 expected predictors.
- Inspect validation error details.
- Compare failed payloads with the prepared `payloads.json`.

Actual result:

_To be completed during the exercise._

Conclusion:

_To be completed during the exercise._

## 4. Diagnostic conclusion

Summarize:

- Most likely root cause.
- Evidence supporting the conclusion.
- Hypotheses rejected and reasons.
- Remaining uncertainty.
- Checks that could not be performed.
- Reason for selecting the recovery action.

A hypothesis must not be described as confirmed without supporting evidence.

## 5. Recovery verification

After Jerry performs the recovery:

- [ ] Record the recovered Cloud Run revision.
- [ ] Compare it with the previously verified recovery target.
- [ ] Compare available image and model identity information.
- [ ] Check `/health`.
- [ ] Execute the same 30 valid prediction attempts.
- [ ] Confirm 30/30 successful predictions.
- [ ] Execute the same 3 invalid requests.
- [ ] Confirm 3/3 HTTP 422 responses.
- [ ] Confirm that the recovered identity matches the expected target.
- [ ] Preserve post-recovery logs and timestamps.

Recovery is not considered verified if the service merely returns HTTP 200 without matching the expected identity.

## 6. Final incident record

Record:

- Incident start and end timestamps (UTC).
- Actual outage duration.
- First detection signal.
- Number of failed valid attempts.
- Root cause and supporting evidence.
- Recovery action performed by Jerry.
- Recovery target identity.
- Post-recovery observations.
- Diagnostic limitations.
- Any deviations from the runbook.
