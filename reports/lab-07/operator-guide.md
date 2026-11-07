# Lab 7 operator procedure and review handoff

Owner/operator: Jerry. Reviewer: Mathis; Brett reviews gate evidence changes and
Romain coordinates the README/report integration. Only Jerry has cloud access.
Cloud operations can be reviewed over screen sharing. This document is a
procedure, not a claim that a real candidate was evaluated or deployed.

## Complete before marking the PR ready

1. Review the gate/pipeline/provenance integration with Mathis and Brett.
2. Run Ruff and the full test suite. Tests simulate cloud calls; no cloud secret
   is needed and no real candidate budget is consumed by synthetic fixtures.
3. Review the deployment diff: no automatic deployment in Cloud Build, digest
   pinning, no-traffic candidate deployment, explicit activation and state recovery.
4. Review changed API health contract (new model_sha256 field); ensure actual
   trusted model metadata contains its SHA-256. Missing/wrong hashes return 503.
5. Update the PR description with actual test results and remaining live checks.
6. Publish the branch, wait for both CI checks, then mark ready for peer review.
   The reviewer merges only after approval and green checks. No live promotion
   is required merely to request code review.

## Work remaining after review/merge

The commands below are executed by Jerry from a supported checkout with gcloud
authentication (Cloud Shell is suitable). Local artifact state is not transferred
by Git: restore the trusted bundle, evidence, current state and operation records
on the execution host. Keep model files and tracking databases out of Git.

Use a clean main checkout, freshly fetched from origin. Install using
`uv sync --locked`. Record the full reviewed main SHA and the built image digest.
The executable checks main/HEAD/local origin-main and clean tracked state; it
cannot verify GitHub approvals or that a local remote ref is up to date.

### 1. Verify the build and freeze a fresh serving reference

Capture service traffic/health before and after the merge build. Retain its
actual ID, log and image digest. Confirm the build has Build and Push, no Deploy,
and traffic/serving identity did not change.

The initial reference captured service revision 00017-czt. Main merges before
the auto-deploy removal may already have advanced the live code revision. Before
candidate training, inspect the actual active revision, image, MODEL_DIR, model
version and bytes. If the captured deployment snapshot is stale, re-establish
and record the accepted reference with a new state_id BEFORE candidate evaluation.
Preserve the old snapshot. Never patch a completed gate decision or prepared
operation to pretend it evaluated the new state. The scripts deliberately block
on a mismatch instead of guessing which live revision is accepted.

The initial reference manifest, backup receipt and recovery proof are in this
directory. Recovery consists of downloading the receipt's generation-pinned
archive, verifying its archive SHA-256, extracting to a fresh directory and
verifying both bundle file hashes. Retain the original image digest as the
runtime/dependency reference. These download/extraction checks have been done;
actual image restart/traffic rollback remains a live check for the Lab 8 handoff.
For new versions, deployment also retains policy and uv.lock in the cloud prefix.

### 2. Capture real gate evidence within the declared budget

Confirm the policy commit predates candidate evaluation. Pilot the latency
protocol on the accepted model before candidates. Run actual measurements in the
agreed container/resources and retain raw repeat p95s. The current gate's default
timer measures local model.predict, not HTTP/network or Cloud Run cold starts;
do not claim it proves endpoint latency. If the agreed operating criterion needs
HTTP timing, coordinate an actual measurement adapter and version its protocol
before candidate evaluation rather than substituting invented timings.

New gate decisions retain `candidate_repeat_p95_ms` and `accepted_repeat_p95_ms`
when the measurement adapter provides the individual p95s. Scalar-only adapters
record null for these fields; repetitions must never be reconstructed. These
fields add evidence without changing the median comparison or the 1.25 limit.
Historical decisions remain unchanged if they did not retain individual p95s.

Use at most the three declared configurations, preserve every attempt, and never
score the held test period. A genuine measured rejection is required; no better
model or promotion is guaranteed. If nothing qualifies, retain current state and
report the incomplete two-version handoff instead of forcing a pass.

```bash
uv run --locked python -m bike_demand.pipeline \
  --config configs/candidate-01.yaml \
  --accepted artifacts/accepted/<accepted-version>
```

Exit 0: eligible. Exit 2: measured rejection. Exit 3: blocked/incomplete evidence.
Save stdout AND stderr and the exit status (Git Bash/Cloud Shell):

```bash
set -o pipefail
# Run the real command with 2>&1 | tee reports/logs/lab-07/<attempt>.log
# Capture its actual status immediately; do not mask it with || true.
```

Keep copies of actual decision JSON in reports without binaries. Before/after
rejection evidence must include accepted bundle hashes, current state and served
identity. None of the synthetic tests substitutes for this real rejection proof.

### 3. Prepare and install an eligible version

Use actual values, not the placeholders below. Keep STATE from the gate's bound
reference and SHA from the reviewed main checkout. Paths are repository-relative.

```bash
uv run --locked python -m bike_demand.promote --dry-run \
  --candidate artifacts/candidates/<candidate-version>
uv run --locked python -m bike_demand.promote --prepare \
  --candidate artifacts/candidates/<candidate-version> --expected-state "$STATE"
uv run --locked python -m bike_demand.promote --install-local \
  --operation "$OP" --expected-state "$STATE" --expected-revision "$SHA"
```

OP is the artifacts/promotions/<operation-id> returned by preparation. Installation
keeps the old bundle/current state and writes 02-installed-local.json. Do not
retrain after deciding or swap files beneath a version name.

### 4. Plan, then deploy without production traffic

IMAGE must be the actual `$REGION-docker.pkg.dev/$PROJECT/...@sha256:...` built
from SHA. Project, region, service and bucket are taken from the accepted snapshot,
not arbitrary default CLI settings. Only the team's recorded service is targeted.

```bash
uv run --locked python -m bike_demand.deploy plan \
  --operation "$OP" --image "$IMAGE" \
  --expected-state "$STATE" --expected-revision "$SHA"
uv run --locked python -m bike_demand.deploy deploy \
  --operation "$OP" --image "$IMAGE" \
  --expected-state "$STATE" --expected-revision "$SHA"
```

Plan is read-only. Deploy is a real, potentially billable cloud operation: it
uploads new versioned objects with creation preconditions, downloads and checks
their exact generations, preserves the read-only full-bucket mount and sets
MODEL_DIR to that version's prefix. It deploys a digest-pinned tagged revision
with --no-traffic; it never overwrites the bucket-root baseline model files,
changes IAM, or routes production traffic. It checks the deployed image, code,
loaded model hash, valid prediction and invalid-input 422, then writes
04-cloud-verified.json. Preserve these records and the real Cloud Run logs.

No service/model traffic metrics are claimed by these contract probes. Existing
IAM, scaling and mount settings are inherited; they must be inspected by the
operator. The code deliberately rejects a changed/missing full-bucket mount.
Tokens are kept in memory and never written to journals or printed.

### 5. Explicit activation and local finalization

Mathis reviews the real no-traffic checks with Jerry before this action. CONFIRM
is the exact candidate revision in 04-cloud-verified.json, not latest.

```bash
uv run --locked python -m bike_demand.deploy activate \
  --operation "$OP" --expected-state "$STATE" --expected-revision "$SHA" \
  --confirm-revision "$CONFIRM"
```

Activation rechecks bytes, generations, tagged API and traffic. It writes intent,
switches 100% to the exact revision, verifies traffic and the service URL, and
only then replaces current.json using a same-directory temporary file. The new
state retains the full previous accepted manifest, image/revision references,
bundle hashes and exact cloud object generations. 06-finalized.json records
completion. Preserve both old and new Cloud Run revisions and all model objects.

### 6. Interruptions and recovery

- Before traffic changes: current.json remains unchanged. Inspect partial stage
  files, cloud objects and revision before retrying the same operation.
- If traffic changed but local finalization failed: keep the operation journal,
  inspect Cloud Run and retry activate with the SAME OP/SHA/STATE/CONFIRM. Tests
  cover interruption both before and after the atomic current-file replacement.
- If unrelated traffic or a different accepted state appears: stop and reconcile.
  The code does not silently roll back a deployment it cannot identify.
- An abrupt process kill can leave the local lock. Inspect its owner, journal and
  actual cloud traffic before manual recovery; never automatically delete it.
- A local lock does not coordinate another laptop/Cloud Shell. Jerry must keep
  one operator session and prevent concurrent manual deployments/build triggers.
- Cloud routing and local disk are not one transaction. Generation-checked
  objects prevent accepting changed bytes during checks, but the bucket has no
  permanent retention lock; retain permissions and never edit published prefixes.

If rollback is needed, use the retained OLD revision explicitly, verify its
bundle/image and health, and record the outcome; do not train a replacement:

```bash
gcloud run services update-traffic "$SERVICE" \
  --project="$PROJECT" --region="$REGION" \
  --to-revisions="$OLD_REVISION=100"
```

This is a real traffic change, to be reviewed and performed deliberately. A
manual rollback also needs a corresponding recorded local-state reconciliation;
do not claim current.json still represents serving state automatically. Lab 8
must verify the actual old/new revision handoff, not just saved filenames.

## Evidence checklist for the report

Retain policy commit, declared inputs/budget, all actual decisions and reasons,
raw validation/latency results, before/after rejection hashes and served identity,
review approval, image digest, object generations, no-traffic checks, traffic
switch/finalization journal and recovery locations. Separate local, CI and live
Cloud Run facts. At most three screenshots supplement the raw records. m4 follows
Labs 7 AND 8; each person's private week-4 report covers both labs.
