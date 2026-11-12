
# Lab 8 — Observation Plan

## 1. Objective

The objective of this observation protocol is to monitor the deployed bike demand prediction API across three phases:

1. Normal operation (baseline).
2. Incident (after the controlled failure has been introduced).
3. Recovery (after returning to the verified accepted revision).

The same payloads, request sequence and measurement rules must be used in all three phases to make the results comparable.

This protocol is designed for observation and diagnosis. It does not modify the deployed service or perform recovery operations.

## 2. Test population

The valid observations must come exclusively from the validation dataset.

- Source: `data/raw/hour.csv`
- Training period: January 1, 2011 – December 31, 2011.
- Validation period: January 1, 2012 – June 30, 2012.
- Test period: July 1, 2012 – December 31, 2012.

The test partition must never be used for this exercise.

A total of 10 distinct valid observations will be selected from the validation period.

Each observation will be submitted three times per phase.

Therefore, each phase contains:

- 10 distinct valid payloads.
- 3 attempts per payload.
- 30 valid prediction attempts in total.
- 3 deliberately invalid requests, recorded separately.

## 3. API contract

The prediction endpoint is:

`POST /predict`

Each valid payload must contain exactly the following 12 predictors:

- `season`
- `yr`
- `mnth`
- `hr`
- `holiday`
- `weekday`
- `workingday`
- `weathersit`
- `temp`
- `atemp`
- `hum`
- `windspeed`

The API must return HTTP 200 for a successful valid prediction.

A prediction is considered successful only if:

- The HTTP status is 200.
- The returned prediction is finite and non-negative.
- The returned model version matches the expected accepted model version for the phase.

A timeout or any other unsuccessful response counts as a failed valid attempt.

## 4. Observation procedure

The same procedure must be followed for each phase.

### Step 1 — Initial health check

Send a request to:

`GET /health`

Record:

- UTC timestamp.
- HTTP status.
- Returned health status.
- Model version.
- Code revision.
- Model SHA256, if exposed by the deployed service.

An unusable health endpoint or unexpected model identity must be reported immediately.

### Step 2 — Valid prediction requests

Submit the 10 valid payloads sequentially.

Each payload must be sent three times.

Wait approximately one second between consecutive requests.

Do not run requests concurrently.

For every attempt, record:

- UTC timestamp.
- Payload identifier.
- Attempt number.
- HTTP status.
- Request duration in milliseconds.
- Prediction value, when available.
- Returned model version, when available.
- Success or failure.
- Error or timeout details, when applicable.

### Step 3 — Deliberately invalid requests

Submit three deliberately invalid requests separately from the valid observations.

The expected response is HTTP 422 for each invalid request.

Record their status codes and response details.

These requests must not be included in the valid prediction success rate.

### Step 4 — Final health check

Send another request to:

`GET /health`

Record the same information as in the initial health check.

## 5. Measurement definitions

### Valid prediction success rate

`Successful valid predictions / Actual valid prediction attempts × 100`

The expected denominator is 30 per phase.

If fewer than 30 attempts are executed, report the actual denominator. Never silently discard failed attempts.

### HTTP latency

Measure the elapsed time between sending a request and receiving the response.

Report latency descriptively. Do not apply the Lab 7 model prediction latency threshold to HTTP request latency.

A fast HTTP 503 response is a failed prediction, not an improvement.

### Invalid request rejection

Count the number of deliberately invalid requests returning HTTP 422.

Expected result: 3/3 per phase.

### Availability and identity

Record the health endpoint result and the identity of the model serving predictions.

The deployed revision must be distinguished from the local source code. Do not assume that the local API implementation is the version currently deployed.

## 6. Incident detection

The investigation must begin when three consecutive valid prediction attempts fail.

An unexpected model identity or an unusable health endpoint must be reported immediately.

Record the timestamp of the first observed failure and the timestamp at which the investigation begins.

## 7. Comparison between phases

The following measurements must be compared across normal operation, incident and recovery:

- Number of valid attempts.
- Number of successful valid predictions.
- Number of failed valid predictions.
- Valid prediction success rate.
- Number of invalid requests rejected with HTTP 422.
- HTTP latency observations.
- Health endpoint results.
- Model version and other available identity information.
- UTC start and end timestamps.
- Actual elapsed duration.

The same measurement definitions must be preserved across all phases.

## 8. Evidence and limitations

Keep the raw observations, logs, standard output, standard error and exit codes.

All timestamps must be recorded in UTC.

Do not include authentication tokens, secrets or unnecessary personal information in logs.

If an expected identity field is unavailable from the deployed service, explicitly record this limitation rather than inferring its value.

If the exercise is interrupted, report the actual number of attempts and the reason for interruption.

The observation protocol does not authorize modifying the accepted model, overwriting accepted artifacts or retraining a model as a recovery method.

## Collector execution and verification scope

Use [observer-usage.md](observer-usage.md). The collector reads ID_TOKEN only from
the environment and sends it as a bearer header on HTTPS; it does not record
request headers or follow redirects. Unset ID_TOKEN for local HTTP probes.

Pass both independently retained expected model version and code revision. The
optional loaded-model hash is checked only when explicitly supplied; the legacy
recovery target has no such field. Both health calls use the same configured
15-second default timeout as predictions. Responses retain X-Request-ID and body
text; use those IDs for the separate Cloud Run log correlation.

Exit 0 means this HTTP phase satisfied all checks; 2 means observations completed
but at least one check failed (an expected possible outcome during incident);
3 means collection was incomplete. No exit code alone proves cloud recovery.
The first signal is recorded once when observed, and successful-request latency
is reported separately from errors. A missing final summary means an incomplete
phase; count the actual retained attempts and record the interruption.
