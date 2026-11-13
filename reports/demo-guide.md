# Final presentation demo: preparation and rehearsal

Run `demo.sh` from the team repository root in Git Bash on Windows. The maintained
script calls `scripts/demo_checks.py`, reusing the authenticated observer transport.
It never builds/trains, scores the held test, deploys or changes Cloud Run routing.
Docker containers are local and uniquely labelled. Actual requests/logs and exit
status are retained under ignored `artifacts/demo/<run>/`. The cold-start readiness
attempts are retained too; successful readiness does not erase earlier failures.

## 1. Record the preparation

Inspect the script, helper, tests, this guide and `.gitattributes`; commit/push them
on the working branch. Normal team review applies. Before presenting, use the exact
clean revision agreed by the team (normally reviewed main/release candidate).
Do not change the checkout after building the image without rebuilding it.

`demo.sh` has LF line endings enforced by `.gitattributes`; execute with Bash.
The local environment must be installed from uv.lock with Python 3.12 and a compatible
uv version (`0.12.23` matches the course pin). The script runs the installed .venv
Python directly, avoiding an extra host `uv run` sync during the presentation.

## 2. Start Docker Desktop and build before the presentation

Start Docker Desktop manually and wait for its Linux engine. In Git Bash:

```bash
cd /c/Users/Jerry/Downloads/mlops-thu1-ekip-bike-demand
git status --short
docker info --format '{{.OSType}} {{.ServerVersion}}'
REV="$(git rev-parse HEAD)"
mkdir -p artifacts
set -o pipefail
docker build --build-arg GIT_SHA="$REV" -t "bike-demand:$REV" . \
  2>&1 | tee "artifacts/demo-build-$REV.log"
```

Git status must be empty and Docker must report linux. A failed build must be fixed
before continuing. The image tag names the source commit; demo.sh additionally
checks image CODE_REVISION against HEAD and resolves/uses the immutable image ID
for every Docker command. Never substitute `latest` to hide an identity mismatch.
Only use the trusted accepted model in the frozen selection. Both model and metadata
must match their stored hashes. The script checks the local port 8000 is available;
if occupied, identify the owner rather than stopping arbitrary containers.

## 3. Check then rehearse locally

```bash
bash demo.sh --check
bash demo.sh --unattended --with-tests
```

`--check` only checks local prerequisites, no container or HTTP call. The unattended
rehearsal runs API tests inside the image, starts the original image command, waits
for verified health, checks valid/invalid requests and prints recent structured logs.
Expected: healthy 200 with expected model/code/hash, valid 200 with finite nonnegative
prediction and expected version, invalid hr=24 returns 422, final exit=0.
The script is not a latency benchmark. Default container startup retains `uv run`;
it may need network access for bootstrap, so rehearse with the planned network.
If startup fails, keep artifacts and inspect container logs; do not label a bootstrap
failure as the deliberately missing-model fault.

The optional extra rehearsal is:

```bash
bash demo.sh --unattended --bonus
```

This checks 503 without a model, then restarts with the read-only accepted bundle
and verifies health/prediction again. Allow time for two extra starts; keep it optional
on stage. Stopping local containers does not modify Cloud Run. Cleanup stops/removes
only script-created labelled containers, with logs retained before removal. Ctrl+C
also triggers cleanup. Check the printed exit code and cleanup logs if interrupted.

## 4. Independently recheck Cloud Run before using cloud mode

Only Jerry has cloud access. In Cloud Shell (not in front of the projector):

```bash
gcloud run services describe mlops-thu1-ekip-bike-demand \
  --project=mlops-ece-group2 --region=europe-west1 \
  --format='yaml(status.url,status.traffic)'
gcloud run revisions describe mlops-thu1-ekip-bike-demand-00018-rng \
  --project=mlops-ece-group2 --region=europe-west1 \
  --format='yaml(spec.containers[0].image,status.imageDigest)'
curl --silent --show-error --connect-timeout 15 --max-time 120 \
  --header "Authorization: Bearer $(gcloud auth print-identity-token)" \
  --write-out '\nHTTP %{http_code}\n' \
  https://mlops-thu1-ekip-bike-demand-jdc2acx6uq-ew.a.run.app/health
```

Compare with retained expectations: revision 00018-rng, accepted model
baseline-4df84bfe8121, code ea37b8a45d4a6738585d9de7d0f95d624ad1d3be, image digest
bbf02e7850f3c282a1cda39d539f59459856cd541d81c713fbdebb19f8f3dd3f.
If different, investigate and retain the observation. Do not simply replace expected
identity with whatever /health says. `--cloud-code` is for an independently verified
intentional release change. A prep probe may warm the service; this demonstration
does not claim cold-start performance. Cloud checks have a 15-second request timeout;
an unexpected timeout stops the run and remains in the evidence.

## 5. Transfer authentication without displaying or saving it

If gcloud is installed/authenticated on the presenting PC, obtain ID_TOKEN in a
subshell via command substitution. Otherwise, use Cloud Shell privately to obtain
`gcloud auth print-identity-token`, copy the token, then use silent input in Git Bash:

```bash
(
  read -r -s -p 'Paste fresh Cloud Run identity token, then Enter: ' ID_TOKEN
  printf '\n'
  export ID_TOKEN
  bash demo.sh --unattended --cloud
)
```

Never send the token in chat, put it in a file, paste it into an export command saved
in history, show it on the projector, or use `set -x`. Clear it from the clipboard
after entry. The subshell's token disappears when it ends; unset any separately
exported parent-shell token too. Local requests explicitly remove ID_TOKEN from
the helper environment; the container never receives it. Cloud mode uses only the
fixed HTTPS service URL, refuses redirects and retains responses, not headers.
The historical cloud health has no loaded-model hash; only local health requires it.

## 6. Presentation mode

```bash
bash demo.sh
```

Press Enter at each local step. For cloud mode, use the token subshell above but
omit `--unattended`. Add `--with-tests` or `--bonus` only if the timed rehearsal fits.
Build/pull and dependency setup belong before the slot. Target roughly 3–4 minutes
for hands-on actions; measure your real run and leave time for data/gate/incident
slides. Explain local code and historical cloud code are different retained releases.
Use stored gate decisions and the existing final test result in slides; never run
`scripts/evaluate_final.py --execute-held-test` during the demo. A local 503 example
does not replace the retained Lab 8 cloud incident/recovery record.

## Validation scope

Syntax/help and offline guards are tested separately from Docker/cloud. A green
unit-test run does not establish that Docker Desktop, image startup, IAM, tokens
or Cloud Run are working. Record the exact successful rehearsal revision and real
outputs after executing these steps. Codex assisted with the correction and tests;
Jerry executes and verifies the live rehearsal.
