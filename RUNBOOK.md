# RUNBOOK: Bike Demand prediction service (Cloud Run)

For the next operator. It tells you how to act; what actually happened during the Lab 8
drill is in [reports/lab-08-incident.md](reports/lab-08-incident.md). Definitions and team
rules are in [reports/lab-08-contract.md](reports/lab-08-contract.md).

## 0. Last verified context

| Item | Value | Last verified |
|---|---|---|
| Service | `mlops-thu1-ekip-bike-demand`, project `mlops-ece-group2`, region `europe-west1` | 2026-11-07T21:06Z (capture) |
| Accepted model | `baseline-4df84bfe8121` (only accepted version) | same |
| Recovery target | revision `mlops-thu1-ekip-bike-demand-00018-rng`, code `ea37b8a…`, image `sha256:bbf02e…` | same; **live re-check pending before the drill** |
| Full expectations | [reports/lab-08/rollback-target.json](reports/lab-08/rollback-target.json) | reviewed in PR #36 |
| Cloud access | Jerry only (IAM) | — |

Update this table after every real use, with the UTC time and who verified it.

## 1. Before you start

Set the variables once per shell (Git Bash or Cloud Shell). Never write the token to a file,
a log or a screenshot.

```bash
set -o pipefail
export PROJECT=mlops-ece-group2 REGION=europe-west1 SERVICE=mlops-thu1-ekip-bike-demand
export TARGET_REV=mlops-thu1-ekip-bike-demand-00018-rng
export EXPECTED_MODEL=baseline-4df84bfe8121
export EXPECTED_CODE=ea37b8a45d4a6738585d9de7d0f95d624ad1d3be
export ID_TOKEN="$(gcloud auth print-identity-token)"   # in memory only
EVID=reports/lab-08/drill-$(date -u +%Y%m%dT%H%M%SZ); mkdir -p "$EVID"
```

Find the URL you are checking (production URL, or the `lab8` tag URL during the drill):

```bash
gcloud run services describe "$SERVICE" --project "$PROJECT" --region "$REGION" \
  --format='yaml(status.url,status.traffic)' | tee "$EVID/service-traffic.yaml"
export URL=<status.url or the url of the traffic entry tagged lab8>
```

## 2. Symptoms → what they usually mean

| Symptom | First interpretation (a hypothesis, not a cause) |
|---|---|
| `/predict` with a valid input returns 503 | service is up but has no usable model |
| `/health` returns 503 | model or metadata missing/unreadable at startup (code from `main` also refuses a checksum mismatch; the target code `ea37b8a` does **not**) |
| `/health` 200 but unexpected `model_version` or `code_revision` | the URL routes to another revision, image or model than expected |
| Timeouts / connection errors / 5xx other than 503 | revision not started, crashed, wrong port, or platform issue |
| Valid input rejected with 422 | client payload or schema changed (check the payload first) |
| Invalid input **accepted** (200) | validation changed in the served code: treat as a release problem |
| Revision "Ready" but requests fail | the startup probe is TCP only: Ready does **not** mean the model is loaded |

Escalate to investigation after **3 consecutive failed valid predictions**; report an
unexpected identity or an unusable `/health` **immediately** (contract §9).

## 3. First checks (cheapest first, keep every output)

Record the UTC time of each check in the incident timeline.

1. **Behaviour from outside** (identity, valid prediction, 422):
   ```bash
   uv run --locked python check_service.py --url "$URL" \
     --expected-model "$EXPECTED_MODEL" --expected-revision "$EXPECTED_CODE" \
     --valid-payload <frozen valid payload>.json 2>&1 | tee "$EVID/check-service.log"
   echo "exit=$?" | tee -a "$EVID/check-service.log"
   curl -sS -w '\nHTTP %{http_code}\n' -H "Authorization: Bearer $ID_TOKEN" "$URL/health"
   ```
2. **Service boundary:** which revision serves the URL, which image, since when.
   ```bash
   gcloud run revisions list --service "$SERVICE" --project "$PROJECT" --region "$REGION" \
     --format='table(metadata.name,metadata.creationTimestamp,status.conditions[0].status)' \
     | tee "$EVID/revisions.txt"
   gcloud run revisions describe <REVISION> --project "$PROJECT" --region "$REGION" \
     --format='yaml(spec.containers[0].image,status.imageDigest,spec.containers[0].env,spec.containers[0].ports,spec.containers[0].resources,spec.volumes,spec.containers[0].volumeMounts)' \
     | tee "$EVID/revision-<REVISION>.yaml"
   ```
   Compare image digest, `MODEL_DIR`, `CODE_REVISION`, mount, port and resources with
   `rollback-target.json`.
3. **Model / artifact boundary:** stored objects still the accepted bytes?
   ```bash
   gcloud storage objects describe gs://thu1-ekip-bike-demand-model/model.joblib \
     --format='yaml(generation,size,md5_hash,update_time)' | tee "$EVID/object-model.yaml"
   gcloud storage objects describe gs://thu1-ekip-bike-demand-model/model-metadata.json \
     --format='yaml(generation,size,md5_hash,update_time)' | tee "$EVID/object-metadata.yaml"
   ```
   Expected generations: `1792749083386751` and `1792749083186741`. If they differ,
   download and compare SHA-256 before concluding (`sha256sum`).
4. **Application events:** what the container says around the first failure.
   ```bash
   gcloud logging read \
     'resource.type="cloud_run_revision" AND resource.labels.service_name="'"$SERVICE"'" AND resource.labels.revision_name="<REVISION>" AND timestamp>="<UTC start>"' \
     --project "$PROJECT" --limit 200 --format=json | tee "$EVID/logs-<REVISION>.json"
   ```
   Look for `event: startup` with `status: unavailable` (model not loaded), request events
   with `status` 503, and `model_version` / `code_revision` values. Platform messages
   (failed start, mount errors, port) appear as text entries in the same query.
5. **Input boundary:** resend the frozen payload unchanged; a 422 on a frozen valid payload
   means the served schema changed, not the client.

Write at least two hypotheses with their expected observation and the check that separates
them **before** concluding (contract §10). Keep rejected ones.

## 4. Decision

| Evidence | Response |
|---|---|
| Fault is in the release, configuration or artifact access of the served revision, and the target of §0 passes the compatibility checks below | **Roll back** to the target (§5) |
| Stored accepted bytes changed (hash/generation mismatch) | **Stop.** Fail closed: do not load or relabel. Escalate (§7) |
| Client payload problem | No rollback; fix the client or the payload |
| Cause unknown after the time box (5 min of active fault in the drill) | Roll back to the target anyway, then continue the diagnosis on evidence |

Compatibility checks before switching (all must pass): target revision still exists and is
`Ready`; its image digest, `MODEL_DIR`, mount and resources equal `rollback-target.json`;
stored model objects have the expected generations **and SHA-256** (the target code does not
check the model hash when loading, so this check is the only fail-closed guard); the target
accepts the same 12-feature request schema as current clients (`BikeDemandFeatures` is
identical between `ea37b8a` and `main`). Never "the previous
revision" or `latest` without these checks: `00017-czt` is older but **not** the target.

## 5. Safe action (Jerry, manual)

**Drill (isolated `lab8` tag)**: move the tag back to the target. Production percentages
are not changed by this command.
```bash
gcloud run services update-traffic "$SERVICE" --project "$PROJECT" --region "$REGION" \
  --update-tags lab8="$TARGET_REV" 2>&1 | tee "$EVID/rollback.log"; echo "exit=$?" | tee -a "$EVID/rollback.log"
```

**Production**: route 100 % to the verified target (this is also the pre-drill pinning step,
contract §5, because traffic otherwise follows `latestRevision`).
```bash
gcloud run services update-traffic "$SERVICE" --project "$PROJECT" --region "$REGION" \
  --to-revisions "$TARGET_REV=100" 2>&1 | tee "$EVID/pin-production.log"
```

Do not retrain, delete revisions, edit bucket objects or change IAM as a repair.

## 6. Verify recovery (fresh evidence only)

1. **Identity:** `/health` returns 200, `status=ok`, `model_version=$EXPECTED_MODEL`,
   `code_revision=$EXPECTED_CODE`; the URL's traffic entry points to `$TARGET_REV`.
2. **Behaviour:** rerun the full contract workload on the same URL: 30/30 valid predictions
   (200, finite, ≥ 0, expected version) and 3/3 invalid inputs rejected with 422.
3. **Signals:** Cloud Run logs **after** the change contain the recovery request IDs with the
   same statuses and identity (§3 step 4 with the new start time).

Declare recovery only if the three agree; write the observation window. A successful
`gcloud` command is not a proof of recovery.

## 7. Escalation

| Situation | Who | Action |
|---|---|---|
| Any cloud operation needed | Jerry | only member with IAM |
| Target fails a compatibility check, or stored bytes changed | Jerry + Romain | stop the drill, record the state, do not improvise a target |
| Cloud Run access or quota blocker | Romain | record the exact message; drill locally with the retained image and bundle |
| Production `/health` not 200 or identity unexpected outside the drill | whole team | pin production to the target (§5), then investigate |

## 8. Limits

- Only one accepted model version exists: rollback restores the retained accepted state,
  not a previous accepted version (contract §2).
- The target API reports `model_version` and `code_revision`, **not** the loaded model hash,
  and does not verify the model checksum when loading: stored-object checks are mandatory.
- The revision reads bucket-root objects: it does not pin model bytes by itself.
- TCP startup probe: a `Ready` revision may still answer 503.
- Latency figures are descriptive HTTP measurements, without threshold.
- Local checks do not reproduce Cloud Run IAM or GCS FUSE.

## 9. Change log

| Date (UTC) | Change | Author |
|---|---|---|
| 2026-11-08 | First version, before the drill and before the peer attempt | Romain |
