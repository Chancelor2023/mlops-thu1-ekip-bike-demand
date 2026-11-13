#!/usr/bin/env bash
# Run from the repository root in Git Bash (Windows) or Bash (Linux).
# No build, training, held-test scoring, deployment or cloud traffic changes.
set +x
set -Eeuo pipefail
export MSYS_NO_PATHCONV=1

CHECK_ONLY=0
AUTO=0
CLOUD=0
WITH_TESTS=0
BONUS=0
IMAGE=""
PROD_URL="https://mlops-thu1-ekip-bike-demand-jdc2acx6uq-ew.a.run.app"
PROD_CODE="ea37b8a45d4a6738585d9de7d0f95d624ad1d3be"

usage() {
  cat <<'HELP'
Usage: bash demo.sh [--check] [--unattended] [--cloud] [--with-tests] [--bonus]
                    [--image TAG] [--cloud-code EXPECTED_SHA]
Default: interactive local demo; image bike-demand:<current full Git SHA>.
--check         Check prerequisites only. No container or HTTP request.
--unattended    Rehearse without Enter pauses; not a latency benchmark.
--cloud         Also check the fixed production URL; requires ID_TOKEN in memory.
--with-tests    Run the API tests inside the pinned image (optional on stage).
--bonus         Demonstrate local /health 503 without a model, then restore 200.
--cloud-code    Independently verified expected cloud code; never guessed from /health.
Cloud checks are read-only. This script never evaluates the held test.
HELP
}
while [[ $# -gt 0 ]]; do
  case "$1" in
    --check) CHECK_ONLY=1; shift ;;
    --unattended) AUTO=1; shift ;;
    --cloud) CLOUD=1; shift ;;
    --with-tests) WITH_TESTS=1; shift ;;
    --bonus) BONUS=1; shift ;;
    --image|--cloud-code)
      [[ $# -ge 2 ]] || { echo "Missing value for $1" >&2; exit 2; }
      if [[ "$1" == --image ]]; then IMAGE="$2"; else PROD_CODE="$2"; fi
      shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
  esac
done

case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) ROOT="$(pwd -W)" ;;
  *) ROOT="$PWD" ;;
esac
[[ -f scripts/demo_checks.py && -f reports/final-model-selection.json ]] || {
  echo "Run from the team repository root; scripts/ and selection must exist." >&2; exit 1;
}
[[ -z "$(git status --porcelain)" ]] || {
  echo "Commit the demo preparation first: the presented checkout must be clean." >&2; exit 1;
}
CODE="$(git rev-parse HEAD)"
[[ -n "$IMAGE" ]] || IMAGE="bike-demand:$CODE"
if [[ -x .venv/Scripts/python.exe ]]; then
  PYTHON="$ROOT/.venv/Scripts/python.exe"
elif [[ -x .venv/bin/python ]]; then
  PYTHON="$ROOT/.venv/bin/python"
else
  echo "Missing .venv Python; install the locked environment first." >&2; exit 1
fi
for CMD in docker git; do command -v "$CMD" >/dev/null || { echo "Missing $CMD" >&2; exit 1; }; done
if [[ "$CLOUD" == 1 && -z "${ID_TOKEN:-}" ]]; then
  echo "Cloud mode needs a fresh ID_TOKEN exported in this shell; never print it." >&2; exit 1
fi
[[ "$PROD_CODE" =~ ^[0-9a-f]{40}$ ]] || { echo "Cloud code must be a full Git SHA" >&2; exit 1; }
RUN="$(date -u +%Y%m%dT%H%M%SZ)-$$-$RANDOM"
EVID="$ROOT/artifacts/demo/$RUN"
mkdir -p "$EVID"
STARTED=$SECONDS

cleanup() {
  local RESULT=$?
  trap - EXIT INT TERM
  set +e
  for FILE in "$EVID"/*.cid; do
    [[ -f "$FILE" ]] || continue
    local CID OWNER
    CID="$(cat "$FILE")"
    [[ "$CID" =~ ^[0-9a-f]{64}$ ]] || continue
    OWNER="$(docker inspect --format '{{index .Config.Labels "mlops.demo.run"}}' "$CID" 2>/dev/null)"
    [[ "$OWNER" == "$RUN" ]] || continue
    docker logs --tail 100 "$CID" > "$FILE.container.log" 2>&1
    if ! docker stop --time 10 "$CID" > "$FILE.stop.log" 2>&1; then
      echo "Cleanup not confirmed for own container $CID; inspect $FILE.stop.log" >&2
      [[ "$RESULT" != 0 ]] || RESULT=1
    elif ! docker rm "$CID" > "$FILE.remove.log" 2>&1; then
      echo "Stopped own container $CID, but its removal failed; see $FILE.remove.log" >&2
      [[ "$RESULT" != 0 ]] || RESULT=1
    fi
  done
  unset ID_TOKEN
  printf '%s\n' "$RESULT" > "$EVID/exit-code.txt"
  printf '\nDemo exit=%s; elapsed=%ss (includes pauses). Evidence: %s\n' "$RESULT" "$((SECONDS - STARTED))" "$EVID"
  exit "$RESULT"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

local_check() { env -u ID_TOKEN "$PYTHON" scripts/demo_checks.py "$@"; }
step() {
  local TITLE="$1"; shift
  printf '\n== %s ==\n' "$TITLE"
  printf '$'; printf ' %q' "$@"; printf '\n'
  if [[ "$AUTO" == 0 ]]; then read -r -p '[Enter] ' || return 1; fi
  "$@"
}

docker info --format '{{.OSType}} {{.ServerVersion}}' > "$EVID/docker-info.txt"
grep -q '^linux ' "$EVID/docker-info.txt" || { echo "Use Docker's Linux engine" >&2; exit 1; }
IMAGE_ID="$(docker image inspect --format '{{.Id}}' "$IMAGE")"
docker image inspect "$IMAGE_ID" > "$EVID/image-inspect.json"
local_check image --image-inspect "$EVID/image-inspect.json" --code "$CODE"
local_check bundle
local_check port
printf '%s\n' "$CODE" > "$EVID/source-commit.txt"
printf '%s\n' "$IMAGE_ID" > "$EVID/image-id.txt"
if [[ "$CHECK_ONLY" == 1 ]]; then echo "PASS prerequisites; no HTTP request or container started."; exit 0; fi

BUNDLE="artifacts/accepted/baseline-4df84bfe8121"
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) HOST_BUNDLE="$(pwd -W)/$BUNDLE" ;;
  *) HOST_BUNDLE="$ROOT/$BUNDLE" ;;
esac
MAIN_NAME="bike-demo-$RUN"
start_healthy() {
  docker run -d --cidfile "$EVID/healthy.cid" --name "$MAIN_NAME" \
    --label "mlops.demo.run=$RUN" -p 127.0.0.1:8000:8000 \
    --mount "type=bind,source=$HOST_BUNDLE,target=/app/artifacts,readonly" \
    "$IMAGE_ID"
  local_check wait --url http://127.0.0.1:8000 --code "$CODE" --output "$EVID/local-readiness.jsonl"
}
step 'Presented source revision' git log -1 --oneline
step 'Accepted model: verify actual bytes' local_check bundle
if [[ "$WITH_TESTS" == 1 ]]; then
  step 'API tests inside the exact image' docker run --rm --entrypoint /app/.venv/bin/python \
    "$IMAGE_ID" -m pytest -q -m api
fi
step 'Start API with read-only accepted bundle; wait for verified health' start_healthy
for ACTION in health valid invalid; do
  step "Local $ACTION check" local_check "$ACTION" --url http://127.0.0.1:8000 \
    --code "$CODE" --output "$EVID/local-requests.jsonl"
done
step 'Recent structured request logs' docker logs --tail 12 "$MAIN_NAME"

if [[ "$BONUS" == 1 ]]; then
  bonus() {
    docker stop --time 10 "$MAIN_NAME" > "$EVID/healthy-stop-before-bonus.log"
    local CID
    CID="$(cat "$EVID/healthy.cid")"
    docker logs --tail 100 "$CID" > "$EVID/healthy-before-bonus.log" 2>&1
    docker rm "$CID" > "$EVID/healthy-remove-before-bonus.log"
    # Keep the stopped container/logs, but do not stop it a second time at exit.
    mv "$EVID/healthy.cid" "$EVID/healthy-stopped.cid.txt"
    docker run -d --cidfile "$EVID/nomodel.cid" --name "bike-demo-nomodel-$RUN" \
      --label "mlops.demo.run=$RUN" -p 127.0.0.1:8000:8000 "$IMAGE_ID"
    local_check wait --status 503 --code "$CODE" --output "$EVID/nomodel-readiness.jsonl"
    docker logs --tail 20 "bike-demo-nomodel-$RUN"
    docker logs --tail 100 "bike-demo-nomodel-$RUN" > "$EVID/nomodel-container.log" 2>&1
    docker stop --time 10 "bike-demo-nomodel-$RUN" > "$EVID/nomodel-stop.log"
    docker rm "bike-demo-nomodel-$RUN" > "$EVID/nomodel-remove.log"
    mv "$EVID/nomodel.cid" "$EVID/nomodel-stopped.cid.txt"
    MAIN_NAME="bike-demo-restored-$RUN"
    start_healthy
    local_check valid --code "$CODE" --output "$EVID/local-restored.jsonl"
  }
  step 'Optional local failure: 503 without model, then verified restoration' bonus
fi

if [[ "$CLOUD" == 1 ]]; then
  echo 'Cloud mode: fixed production URL, read-only requests; legacy health has no model hash.'
  for ACTION in health valid invalid; do
    step "Cloud Run $ACTION check" "$PYTHON" scripts/demo_checks.py "$ACTION" \
      --cloud --url "$PROD_URL" --code "$PROD_CODE" --output "$EVID/cloud-requests.jsonl"
  done
fi
echo 'PASS demo checks. Cleanup follows; held-test evaluation was not run.'
