"""Manual Cloud Run deployment: plan, verify without traffic, then activate."""

import argparse
import json
import math
import os
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4

from bike_demand import promote

PAYLOAD = {
    "season": 1,
    "yr": 1,
    "mnth": 3,
    "hr": 8,
    "holiday": 0,
    "weekday": 2,
    "workingday": 1,
    "weathersit": 1,
    "temp": 0.4,
    "atemp": 0.4,
    "hum": 0.6,
    "windspeed": 0.2,
}


def traffic(service: dict) -> dict:
    result = {}
    for item in service["status"].get("traffic", []):
        percent = item.get("percent", 0)
        if percent:
            revision = item.get("revisionName")
            if not revision:
                raise ValueError("Traffic has no resolved revision identity")
            result[revision] = result.get(revision, 0) + percent
    if sum(result.values()) != 100:
        raise ValueError("Expected resolved traffic totaling 100 percent")
    return result


def create_record(path: Path, value: dict) -> None:
    if path.exists():
        if promote.read_object(path) != value:
            raise ValueError(f"Existing operation record differs: {path.name}")
    else:
        promote.write_new_json(path, value)


def make_plan(
    root: Path, operation: Path, image: str, revision: str, state: str
) -> dict:
    root = root.resolve()
    stage = promote.inside(root / operation, root / "artifacts/promotions")
    ready = promote.verify_prepared(root, stage, state)
    installed = promote.read_object(stage / "02-installed-local.json")
    expected_path = f"artifacts/accepted/{ready['model_version']}"
    if (
        installed.get("installation_code_revision") != revision
        or installed.get("expected_state_id") != state
        or installed.get("installed_bundle_path") != expected_path
        or installed.get("status") != "installed_local_pending_cloud"
    ):
        raise ValueError("Installation receipt does not match this plan")
    promote.verify_installed(root / expected_path, ready)
    current = promote.check_current(root)
    snapshot = current["deployment_snapshot"]
    project, region, service = (
        snapshot[key] for key in ("project", "region", "service")
    )
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Expected the full reviewed main commit SHA")
    prefix = f"{region}-docker.pkg.dev/{project}/"
    if not image.startswith(prefix) or not re.fullmatch(
        r"[^\s]+@sha256:[0-9a-f]{64}", image
    ):
        raise ValueError(
            "Use a digest-pinned image from the recorded project and region"
        )
    version = ready["model_version"]
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,50}", version):
        raise ValueError("Model version is not safe for a cloud prefix")
    suffix = f"l7-{stage.name.removeprefix('promotion-')[:10]}-{revision[:8]}"
    cloud_prefix = f"versions/{version}/{ready['evidence_sha256']['model.joblib']}"
    return {
        "operation_id": stage.name,
        "project": project,
        "region": region,
        "service": service,
        "image": image,
        "code_revision": revision,
        "expected_state_id": state,
        "model_version": version,
        "model_sha256": ready["evidence_sha256"]["model.joblib"],
        "bucket": snapshot["source_bucket"],
        "cloud_prefix": cloud_prefix,
        "model_dir": f"/app/artifacts/{cloud_prefix}",
        "revision_suffix": suffix,
        "candidate_revision": f"{service}-{suffix}",
        "tag": f"lab7-{stage.name.removeprefix('promotion-')[:10]}",
        "previous_revision": snapshot["revision"],
        "previous_model_version": current["model_version"],
        "previous_model_sha256": current["checksums"]["model.joblib"],
        "previous_code_revision": snapshot["observed_health"]["code_revision"],
        "new_state_id": stage.name.removeprefix("promotion-"),
    }


class GCloud:
    """CLI/HTTP boundary. Tokens stay in memory and never enter journal records."""

    def __init__(self):
        self.token = None

    def run(self, *args, allow_failure=False):
        result = subprocess.run(
            ["gcloud", *map(str, args)], capture_output=True, text=True, timeout=900
        )
        if result.returncode and not allow_failure:
            raise RuntimeError(
                f"gcloud {args[0]} operation failed (exit {result.returncode}); inspect Cloud Console"
            )
        return result

    def describe(self, plan):
        return json.loads(
            self.run(
                "run",
                "services",
                "describe",
                plan["service"],
                f"--project={plan['project']}",
                f"--region={plan['region']}",
                "--format=json",
            ).stdout
        )

    def revision(self, plan):
        return json.loads(
            self.run(
                "run",
                "revisions",
                "describe",
                plan["candidate_revision"],
                f"--project={plan['project']}",
                f"--region={plan['region']}",
                "--format=json",
            ).stdout
        )

    def request(self, url, payload=None):
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or not parsed.hostname.endswith(".run.app")
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
        ):
            raise ValueError("Authenticated requests must target a Cloud Run HTTPS URL")
        if self.token is None:
            self.token = self.run("auth", "print-identity-token").stdout.strip()
        body = None if payload is None else json.dumps(payload).encode()
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        request = Request(
            url, data=body, headers=headers, method="GET" if payload is None else "POST"
        )
        try:
            with urlopen(request, timeout=120) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.loads(error.read())

    def object_receipt(self, uri, expected_hash):
        meta = json.loads(
            self.run("storage", "objects", "describe", uri, "--format=json").stdout
        )
        generation = str(meta["generation"])
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "object"
            self.run(
                "storage", "cp", "--do-not-decompress", f"{uri}#{generation}", target
            )
            if promote.sha256(target) != expected_hash:
                raise ValueError("Remote object bytes do not match evaluated evidence")
        return {"uri": uri, "generation": generation, "sha256": expected_hash}

    def publish(self, plan, files):
        receipts = []
        for name, path in files.items():
            uri = f"gs://{plan['bucket']}/{plan['cloud_prefix']}/{name}"
            # On a retry, a pre-existing object is accepted only after byte verification.
            self.run(
                "storage",
                "cp",
                "--if-generation-match=0",
                path,
                uri,
                allow_failure=True,
            )
            receipts.append(self.object_receipt(uri, promote.sha256(path)))
        return receipts

    def verify_objects(self, receipts):
        for receipt in receipts:
            if self.object_receipt(receipt["uri"], receipt["sha256"]) != receipt:
                raise ValueError("Remote object generation changed since verification")

    def deploy(self, plan):
        # A retry may encounter the already-created revision. The caller always
        # describes and checks the exact image and MODEL_DIR before accepting it.
        self.run(
            "run",
            "deploy",
            plan["service"],
            f"--image={plan['image']}",
            "--no-traffic",
            f"--tag={plan['tag']}",
            f"--revision-suffix={plan['revision_suffix']}",
            f"--update-env-vars=MODEL_DIR={plan['model_dir']}",
            "--port=8000",
            f"--project={plan['project']}",
            f"--region={plan['region']}",
            "--quiet",
            allow_failure=True,
        )

    def route(self, plan):
        self.run(
            "run",
            "services",
            "update-traffic",
            plan["service"],
            f"--to-revisions={plan['candidate_revision']}=100",
            f"--project={plan['project']}",
            f"--region={plan['region']}",
            "--quiet",
        )


def verify_mount(service, plan):
    spec = service["spec"]["template"]["spec"]
    containers = spec["containers"]
    if len(containers) != 1:
        raise ValueError("Expected the recorded single-container service")
    mounts = {m["name"]: m["mountPath"] for m in containers[0].get("volumeMounts", [])}
    for volume in spec.get("volumes", []):
        csi = volume.get("csi", {})
        attributes = csi.get("volumeAttributes", {})
        if (
            mounts.get(volume["name"]) == "/app/artifacts"
            and csi.get("driver") == "gcsfuse.run.googleapis.com"
            and csi.get("readOnly") is True
            and attributes == {"bucketName": plan["bucket"]}
        ):
            return
    raise ValueError("Expected the unchanged read-only full-bucket model mount")


def verify_health(backend, url, plan, candidate=True):
    status, body = backend.request(url.rstrip("/") + "/health")
    version = plan["model_version"] if candidate else plan["previous_model_version"]
    revision = plan["code_revision"] if candidate else plan["previous_code_revision"]
    if (
        status != 200
        or body.get("status") != "ok"
        or body.get("model_version") != version
        or body.get("code_revision") != revision
    ):
        raise ValueError(
            "Serving model/code identity differs; inspect or refresh baseline before preparing"
        )
    expected_hash = plan["model_sha256"] if candidate else plan["previous_model_sha256"]
    if (candidate or "model_sha256" in body) and body.get(
        "model_sha256"
    ) != expected_hash:
        raise ValueError("Serving model checksum differs from evaluated bytes")
    return body


def verify_api(backend, url, plan):
    health = verify_health(backend, url, plan)
    status, body = backend.request(url.rstrip("/") + "/predict", PAYLOAD)
    prediction = body.get("prediction")
    if (
        status != 200
        or body.get("model_version") != plan["model_version"]
        or isinstance(prediction, bool)
        or not isinstance(prediction, (int, float))
        or not math.isfinite(prediction)
        or prediction < 0
    ):
        raise ValueError("Valid prediction contract failed")
    status, _ = backend.request(url.rstrip("/") + "/predict", {**PAYLOAD, "hr": 24})
    if status != 422:
        raise ValueError("Invalid request was not rejected with 422")
    return {"health": health, "valid_prediction": "pass", "invalid_request": "pass"}


def verify_revision(value, plan):
    if value["metadata"]["name"] != plan["candidate_revision"]:
        raise ValueError("Wrong candidate revision")
    containers = value["spec"]["containers"]
    env = {e["name"]: e.get("value") for e in containers[0].get("env", [])}
    digest = value.get("status", {}).get("imageDigest")
    if (
        len(containers) != 1
        or containers[0]["image"] != plan["image"]
        or digest not in {plan["image"], plan["image"].split("@", 1)[1]}
        or env.get("MODEL_DIR") != plan["model_dir"]
    ):
        raise ValueError("Revision image or model directory differs from the plan")


def deploy_candidate(root, operation, image, revision, state, backend=None):
    backend = backend or GCloud()
    root = root.resolve()
    promote.require_main_checkout(root, revision)
    stage = promote.inside(root / operation, root / "artifacts/promotions")
    with promote.promotion_lock(root):
        plan = make_plan(root, stage, image, revision, state)
        create_record(stage / "03-cloud-plan.json", plan)
        service = backend.describe(plan)
        if traffic(service) != {plan["previous_revision"]: 100}:
            raise ValueError(
                "Production traffic no longer matches the captured reference"
            )
        verify_mount(service, plan)
        verify_health(backend, service["status"]["url"], plan, candidate=False)
        ready = promote.verify_prepared(root, stage, state)
        bundle = root / "artifacts/accepted" / plan["model_version"]
        promote.verify_installed(bundle, ready)
        files = {
            name: bundle / name for name in (*promote.EVALUATED_FILES, "decision.json")
        }
        files.update(
            {
                "gate-policy.yaml": stage / "gate-policy.yaml",
                "uv.lock": root / "uv.lock",
            }
        )
        promote.require_main_checkout(root, revision)
        objects = backend.publish(plan, files)
        promote.verify_installed(bundle, ready)
        promote.require_main_checkout(root, revision)
        backend.deploy(plan)
        verify_revision(backend.revision(plan), plan)
        after = backend.describe(plan)
        verify_mount(after, plan)
        if traffic(after) != {plan["previous_revision"]: 100}:
            raise ValueError(
                "Unexpected production traffic change during candidate deployment"
            )
        urls = [
            t["url"]
            for t in after["status"]["traffic"]
            if t.get("tag") == plan["tag"]
            and t.get("revisionName") == plan["candidate_revision"]
        ]
        if len(urls) != 1:
            raise ValueError("Candidate tag URL not found unambiguously")
        checks = verify_api(backend, urls[0], plan)
        promote.verify_prepared(root, stage, state)
        backend.verify_objects(objects)
        receipt = {
            "plan": plan,
            "objects": objects,
            "tag_url": urls[0],
            "service_url": after["status"]["url"],
            "checks": checks,
            "status": "verified_without_production_traffic",
        }
        create_record(stage / "04-cloud-verified.json", receipt)
        return receipt


def activate(root, operation, revision, state, confirm_revision, backend=None):
    backend = backend or GCloud()
    root = root.resolve()
    promote.require_main_checkout(root, revision)
    stage = promote.inside(root / operation, root / "artifacts/promotions")
    with promote.promotion_lock(root):
        receipt = promote.read_object(stage / "04-cloud-verified.json")
        plan = receipt["plan"]
        if (
            plan != promote.read_object(stage / "03-cloud-plan.json")
            or plan["code_revision"] != revision
            or plan["expected_state_id"] != state
            or plan["candidate_revision"] != confirm_revision
        ):
            raise ValueError("Activation arguments do not match the verified operation")
        current_path = root / "artifacts/accepted/current.json"
        current = promote.check_current(root)
        finalized = current.get("promotion_operation") == stage.name
        if not finalized:
            if make_plan(root, stage, plan["image"], revision, state) != plan:
                raise ValueError("Plan changed before activation")
        else:
            expected = promote.read_object(stage / "05-activation-intent.json")[
                "next_current"
            ]
            if current != expected:
                raise ValueError("Current state differs from the completed operation")
        backend.verify_objects(receipt["objects"])
        verify_revision(backend.revision(plan), plan)
        verify_api(backend, receipt["tag_url"], plan)
        service = backend.describe(plan)
        observed = traffic(service)
        if observed not in (
            {plan["previous_revision"]: 100},
            {plan["candidate_revision"]: 100},
        ):
            raise ValueError(
                "Traffic changed outside this operation; stop and reconcile"
            )
        if finalized and observed != {plan["candidate_revision"]: 100}:
            raise ValueError("Finalized state and live traffic differ")
        if not finalized:
            ready = promote.verify_prepared(root, stage, state)
            next_current = {
                "schema_version": 1,
                "state_id": plan["new_state_id"],
                "origin": "verified_manual_cloud_promotion",
                "promotion_operation": stage.name,
                "model_version": plan["model_version"],
                "bundle_path": f"artifacts/accepted/{plan['model_version']}",
                "checksums": {
                    name: ready["evidence_sha256"][name]
                    for name in promote.BUNDLE_FILES
                },
                "previous_accepted": ready["previous_accepted"],
                "remote_objects": receipt["objects"],
                "deployment_snapshot": {
                    "project": plan["project"],
                    "region": plan["region"],
                    "service": plan["service"],
                    "revision": plan["candidate_revision"],
                    "image": plan["image"],
                    "source_bucket": plan["bucket"],
                    "model_dir": plan["model_dir"],
                    "observed_health": receipt["checks"]["health"],
                },
            }
            create_record(
                stage / "05-activation-intent.json",
                {"plan": plan, "next_current": next_current},
            )
            if observed == {plan["previous_revision"]: 100}:
                verify_health(backend, service["status"]["url"], plan, candidate=False)
                promote.require_main_checkout(root, revision)
                backend.route(plan)
        after = backend.describe(plan)
        if traffic(after) != {plan["candidate_revision"]: 100}:
            raise ValueError(
                "Traffic transition not verified yet; rerun activation after inspection"
            )
        verify_api(backend, after["status"]["url"], plan)
        backend.verify_objects(receipt["objects"])
        if not finalized:
            promote.verify_prepared(root, stage, state)
            promote.verify_installed(root / next_current["bundle_path"], ready)
            promote.require_main_checkout(root, revision)
            temporary = current_path.with_name(f".current-{uuid4().hex}.json")
            promote.write_new_json(temporary, next_current)
            os.replace(temporary, current_path)
        promote.check_current(root)
        result = {
            "status": "promoted_and_verified",
            "plan": plan,
            "current_state_id": plan["new_state_id"],
        }
        create_record(stage / "06-finalized.json", result)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("plan", "deploy", "activate"))
    parser.add_argument("--operation", type=Path, required=True)
    parser.add_argument("--image")
    parser.add_argument("--expected-revision", required=True)
    parser.add_argument("--expected-state", required=True)
    parser.add_argument("--confirm-revision")
    args = parser.parse_args()
    if args.phase in {"plan", "deploy"} and not args.image:
        parser.error("plan/deploy requires --image pinned by digest")
    if args.phase == "activate" and not args.confirm_revision:
        parser.error("activate requires --confirm-revision")
    try:
        if args.phase == "activate":
            result = activate(
                Path.cwd(),
                args.operation,
                args.expected_revision,
                args.expected_state,
                args.confirm_revision,
            )
        else:
            function = make_plan if args.phase == "plan" else deploy_candidate
            result = function(
                Path.cwd(),
                args.operation,
                args.image,
                args.expected_revision,
                args.expected_state,
            )
        print(json.dumps(result, indent=2))
        return 0
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        RuntimeError,
        subprocess.TimeoutExpired,
    ) as error:
        # A remote operation may already have taken effect. Never claim rollback.
        try:
            stage = promote.inside(
                Path.cwd() / args.operation, Path.cwd() / "artifacts/promotions"
            )
        except ValueError:
            stage = None
        failure = {
            "status": "blocked",
            "phase": args.phase,
            "reasons": [str(error)],
            "remote_state_requires_inspection": args.phase != "plan",
        }
        if args.phase != "plan" and stage is not None and stage.is_dir():
            promote.write_new_json(stage / f"cloud-failed-{uuid4().hex}.json", failure)
        print(json.dumps(failure))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
