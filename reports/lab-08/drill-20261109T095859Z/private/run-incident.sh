#!/usr/bin/env bash
set -eu
set -o pipefail

ROOT="$HOME/lab8-drill-20261109T095859Z"
REPO="$HOME/mlops-thu1-ekip-bike-demand"
TARGET="mlops-thu1-ekip-bike-demand-00018-rng"
FAULT="mlops-thu1-ekip-bike-demand-lab8-fault-67f152fd40"
STAGE="$ROOT/incident"
ARMED=0

cd "$REPO"

test -x ".venv/bin/python"
test -f "scripts/lab8_observe.py"
test -f "$ROOT/preparation/frozen-inputs/payloads.json"
test -f "$ROOT/private/cloud-staging/staging-result.json"

bash -n "$ROOT/private/restore-lab8.sh"
bash -n "$ROOT/private/auto-restore-lab8.sh"

# Refuser d'écraser une précédente tentative.
if [[ -e "$STAGE" ]]; then
  echo "STOP : le dossier incident existe déjà. Ne pas le supprimer."
  exit 1
fi
mkdir "$STAGE"

gcloud run services describe mlops-thu1-ekip-bike-demand \
  --project=mlops-ece-group2 \
  --region=europe-west1 \
  --format=json \
  > "$STAGE/service-before.json"

python3 - "$STAGE/service-before.json" "$TARGET" <<'PY'
import json
import sys

with open(sys.argv[1]) as stream:
    service = json.load(stream)

traffic = service["status"].get("traffic", [])
target = sys.argv[2]

if sum(item.get("percent", 0) for item in traffic) != 100:
    raise SystemExit("STOP : répartition du trafic inattendue.")

if any(
    item.get("percent", 0) > 0
    and item.get("revisionName") != target
    for item in traffic
):
    raise SystemExit("STOP : trafic habituel hors de la référence.")

tags = [item for item in traffic if item.get("tag") == "lab8"]
if len(tags) != 1 or tags[0].get("revisionName") != target:
    raise SystemExit("STOP : tag lab8 hors de la référence.")

print("PASS : routage initial conforme.")
PY

# Le jeton reste en mémoire et n'est pas enregistré dans les preuves.
export ID_TOKEN="$(gcloud auth print-identity-token)"
test -n "$ID_TOKEN"
URL="$(cat "$ROOT/preparation/lab8-url.txt")"

git rev-parse HEAD > "$STAGE/observer-source-commit.txt"

cleanup() {
  RESULT=$?
  trap - EXIT
  unset ID_TOKEN

  if [[ "$ARMED" == 1 ]]; then
    echo "Retour à la référence..."
    if bash "$ROOT/private/restore-lab8.sh" "$ROOT"; then
      date -u +%Y-%m-%dT%H:%M:%SZ \
        > "$STAGE/restore-command-succeeded-at.txt"
      echo "Commande de retour réussie ; vérifications à effectuer."
    else
      echo "ATTENTION : retour non confirmé."
      echo "Le secours automatique tentera également la récupération."
      RESULT=1
    fi
  fi

  exit "$RESULT"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

date -u +%Y-%m-%dT%H:%M:%SZ \
  > "$STAGE/watchdog-started-at.txt"

# Ne pas transmettre le jeton au processus de secours.
nohup env -u ID_TOKEN \
  bash "$ROOT/private/auto-restore-lab8.sh" "$ROOT" \
  > "$ROOT/private/auto-restore.log" 2>&1 < /dev/null &

WATCHDOG_PID=$!
ARMED=1
printf '%s\n' "$WATCHDOG_PID" > "$STAGE/watchdog.pid"
kill -0 "$WATCHDOG_PID"

date -u +%Y-%m-%dT%H:%M:%SZ \
  > "$STAGE/activation-started-at.txt"

set +e
timeout --signal=INT --kill-after=5s 60s \
  gcloud run services update-traffic mlops-thu1-ekip-bike-demand \
  --project=mlops-ece-group2 \
  --region=europe-west1 \
  --to-revisions="$TARGET=100" \
  --update-tags="lab8=$FAULT" \
  > "$STAGE/activation.stdout.log" \
  2> "$STAGE/activation.stderr.log"
ACTIVATION_EXIT=$?
set -e

printf '%s\n' "$ACTIVATION_EXIT" \
  > "$STAGE/activation-exit.txt"
date -u +%Y-%m-%dT%H:%M:%SZ \
  > "$STAGE/activation-command-ended-at.txt"

if [[ "$ACTIVATION_EXIT" != 0 ]]; then
  echo "Activation non confirmée ; récupération immédiate."
  exit 1
fi

echo "Activation commandée. Début des observations."
date -u +%Y-%m-%dT%H:%M:%SZ

set +e
timeout --signal=INT --kill-after=5s 90s \
  .venv/bin/python -u scripts/lab8_observe.py \
  --url "$URL" \
  --phase incident \
  --expected-model-version baseline-4df84bfe8121 \
  --expected-code-revision ea37b8a45d4a6738585d9de7d0f95d624ad1d3be \
  --payloads "$ROOT/preparation/frozen-inputs/payloads.json" \
  --output-dir "$STAGE" \
  --timeout 15 \
  2>&1 | tee "$STAGE/observer.log"
OBSERVER_EXIT=${PIPESTATUS[0]}
set -e

printf '%s\n' "$OBSERVER_EXIT" > "$STAGE/observer-exit.txt"
date -u +%Y-%m-%dT%H:%M:%SZ \
  > "$STAGE/observation-ended-at.txt"

echo "Code de sortie des observations : $OBSERVER_EXIT"
echo "Collecte terminée ; récupération immédiate."
