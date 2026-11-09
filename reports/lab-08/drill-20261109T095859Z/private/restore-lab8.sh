#!/usr/bin/env bash
set -u
set -o pipefail

ROOT="${1:-}"
if [[ -z "$ROOT" || ! -d "$ROOT/preparation" ]]; then
  echo "STOP : dossier de preuves absent."
  exit 1
fi

STAMP="$(date -u +%Y%m%dT%H%M%S%N)"
LOG="$ROOT/private/restore-routing-$STAMP.log"

date -u +%Y-%m-%dT%H:%M:%SZ > "$LOG"

timeout --signal=INT --kill-after=5s 60s \
  gcloud run services update-traffic mlops-thu1-ekip-bike-demand \
  --project=mlops-ece-group2 \
  --region=europe-west1 \
  --to-revisions=mlops-thu1-ekip-bike-demand-00018-rng=100 \
  --update-tags=lab8=mlops-thu1-ekip-bike-demand-00018-rng \
  2>&1 | tee -a "$LOG"

RESULT=${PIPESTATUS[0]}
printf 'exit=%s\n' "$RESULT" | tee -a "$LOG"
date -u +%Y-%m-%dT%H:%M:%SZ >> "$LOG"
exit "$RESULT"
