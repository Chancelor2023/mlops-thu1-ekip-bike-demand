"""Cloud calls are simulated. No gcloud command, network or real model is used."""

import copy
import json

import pytest
from test_promote import scenario as scenario

from bike_demand import deploy, promote

REVISION = "a" * 40
IMAGE = "europe-west1-docker.pkg.dev/test-project/repo/team@sha256:" + "b" * 64


class FakeCloud:
    def __init__(self):
        self.active = "team-old"
        self.deployed = False
        self.calls = []
        self.plan = None
        self.objects = []
        self.bad_hash = False
        self.bad_prediction = False
        self.bad_invalid_status = False
        self.bad_revision = False

    def describe(self, plan):
        self.plan = plan
        entries = [{"revisionName": self.active, "percent": 100}]
        if self.deployed:
            entries.append(
                {
                    "revisionName": plan["candidate_revision"],
                    "tag": plan["tag"],
                    "url": "https://candidate.example",
                }
            )
        return {
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "volumeMounts": [
                                    {"name": "model", "mountPath": "/app/artifacts"}
                                ]
                            }
                        ],
                        "volumes": [
                            {
                                "name": "model",
                                "csi": {
                                    "driver": "gcsfuse.run.googleapis.com",
                                    "readOnly": True,
                                    "volumeAttributes": {"bucketName": "test-models"},
                                },
                            }
                        ],
                    }
                }
            },
            "status": {"url": "https://service.example", "traffic": entries},
        }

    def publish(self, plan, files):
        self.calls.append("publish")
        self.objects = [
            {
                "uri": f"gs://test-models/{plan['cloud_prefix']}/{name}",
                "sha256": promote.sha256(path),
                "generation": "123",
            }
            for name, path in files.items()
        ]
        return copy.deepcopy(self.objects)

    def verify_objects(self, receipts):
        if receipts != self.objects:
            raise ValueError("Remote generation changed")

    def deploy(self, plan):
        self.calls.append("deploy-without-traffic")
        self.deployed = True

    def revision(self, plan):
        return {
            "metadata": {"name": plan["candidate_revision"]},
            "spec": {
                "containers": [
                    {
                        "image": "wrong" if self.bad_revision else plan["image"],
                        "env": [{"name": "MODEL_DIR", "value": plan["model_dir"]}],
                    }
                ]
            },
            "status": {"imageDigest": plan["image"]},
        }

    def request(self, url, payload=None):
        plan = self.plan
        candidate = (
            url.startswith("https://candidate.example")
            or self.active == plan["candidate_revision"]
        )
        if url.endswith("/health"):
            if candidate:
                return 200, {
                    "status": "ok",
                    "model_version": plan["model_version"],
                    "code_revision": plan["code_revision"],
                    "model_sha256": "wrong" if self.bad_hash else plan["model_sha256"],
                }
            return 200, {
                "status": "ok",
                "model_version": plan["previous_model_version"],
                "code_revision": plan["previous_code_revision"],
            }
        if payload["hr"] == 24:
            return (200 if self.bad_invalid_status else 422), {}
        return 200, {
            "prediction": -1 if self.bad_prediction else 12.5,
            "model_version": plan["model_version"],
        }

    def route(self, plan):
        self.calls.append("route")
        self.active = plan["candidate_revision"]


@pytest.fixture
def cloud_operation(scenario, monkeypatch):
    root, candidate, policy, _ = scenario
    current_path = root / "artifacts/accepted/current.json"
    current = promote.read_object(current_path)
    current["deployment_snapshot"] = {
        "project": "test-project",
        "region": "europe-west1",
        "service": "team",
        "source_bucket": "test-models",
        "revision": "team-old",
        "image": "old-image@sha256:" + "c" * 64,
        "observed_health": {"code_revision": "d" * 40},
    }
    current_path.write_text(json.dumps(current), encoding="utf-8")
    (root / "uv.lock").write_text("synthetic lock", encoding="utf-8")
    monkeypatch.setattr(promote, "require_main_checkout", lambda *args: None)
    prepared = promote.prepare_promotion(root, candidate, policy, "state-1")
    stage = root / prepared["staging_path"]
    promote.install_local(root, stage, "state-1", REVISION)
    return root, stage, FakeCloud()


def snapshot(root):
    return {
        str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()
    }


def test_cloud_plan_has_no_writes_and_uses_versioned_model_path(cloud_operation):
    root, stage, cloud = cloud_operation
    before = snapshot(root)
    plan = deploy.make_plan(root, stage, IMAGE, REVISION, "state-1")
    assert snapshot(root) == before
    assert cloud.calls == []
    assert plan["cloud_prefix"].startswith("versions/candidate-v2/")
    assert plan["model_sha256"] in plan["cloud_prefix"]
    assert plan["model_dir"].startswith("/app/artifacts/versions/")


def test_deploy_verifies_candidate_without_switching_traffic(cloud_operation):
    root, stage, cloud = cloud_operation
    current = (root / "artifacts/accepted/current.json").read_bytes()
    receipt = deploy.deploy_candidate(root, stage, IMAGE, REVISION, "state-1", cloud)
    assert receipt["status"] == "verified_without_production_traffic"
    assert cloud.active == "team-old"
    assert cloud.calls == ["publish", "deploy-without-traffic"]
    assert (root / "artifacts/accepted/current.json").read_bytes() == current
    assert any(o["uri"].endswith("/uv.lock") for o in receipt["objects"])


@pytest.mark.parametrize(
    "problem", ["bad_hash", "bad_prediction", "bad_invalid_status", "bad_revision"]
)
def test_invalid_candidate_never_becomes_activatable(cloud_operation, problem):
    root, stage, cloud = cloud_operation
    setattr(cloud, problem, True)
    with pytest.raises(ValueError):
        deploy.deploy_candidate(root, stage, IMAGE, REVISION, "state-1", cloud)
    assert not (stage / "04-cloud-verified.json").exists()
    assert cloud.active == "team-old"
    assert promote.check_current(root)["state_id"] == "state-1"


def test_external_traffic_change_blocks_deployment_before_upload(cloud_operation):
    root, stage, cloud = cloud_operation
    cloud.active = "another-teams-revision"
    with pytest.raises(ValueError, match="traffic no longer matches"):
        deploy.deploy_candidate(root, stage, IMAGE, REVISION, "state-1", cloud)
    assert cloud.calls == []


def test_activation_verifies_traffic_then_updates_current_and_retains_old_bundle(
    cloud_operation,
):
    root, stage, cloud = cloud_operation
    before = snapshot(root / "artifacts/accepted/accepted-v1")
    receipt = deploy.deploy_candidate(root, stage, IMAGE, REVISION, "state-1", cloud)
    result = deploy.activate(
        root, stage, REVISION, "state-1", receipt["plan"]["candidate_revision"], cloud
    )
    current = promote.check_current(root)
    assert result["status"] == "promoted_and_verified"
    assert cloud.active == receipt["plan"]["candidate_revision"]
    assert current["model_version"] == "candidate-v2"
    assert current["previous_accepted"]["model_version"] == "accepted-v1"
    assert snapshot(root / "artifacts/accepted/accepted-v1") == before
    before_retry = snapshot(root)
    assert (
        deploy.activate(root, stage, REVISION, "state-1", cloud.active, cloud) == result
    )
    assert snapshot(root) == before_retry
    assert cloud.calls.count("route") == 1


def test_activation_requires_exact_explicit_revision_confirmation(cloud_operation):
    root, stage, cloud = cloud_operation
    deploy.deploy_candidate(root, stage, IMAGE, REVISION, "state-1", cloud)
    with pytest.raises(ValueError, match="Activation arguments"):
        deploy.activate(root, stage, REVISION, "state-1", "wrong", cloud)
    assert "route" not in cloud.calls


def test_remote_object_change_prevents_traffic_switch(cloud_operation):
    root, stage, cloud = cloud_operation
    receipt = deploy.deploy_candidate(root, stage, IMAGE, REVISION, "state-1", cloud)
    cloud.objects[0]["generation"] = "456"
    with pytest.raises(ValueError, match="Remote generation changed"):
        deploy.activate(
            root,
            stage,
            REVISION,
            "state-1",
            receipt["plan"]["candidate_revision"],
            cloud,
        )
    assert cloud.active == "team-old"


@pytest.mark.parametrize("after_replace", [False, True])
def test_resume_when_traffic_switched_but_finalization_was_interrupted(
    cloud_operation, monkeypatch, after_replace
):
    root, stage, cloud = cloud_operation
    receipt = deploy.deploy_candidate(root, stage, IMAGE, REVISION, "state-1", cloud)
    target = receipt["plan"]["candidate_revision"]
    original = deploy.os.replace

    def interrupted(source, destination):
        if after_replace:
            original(source, destination)
        raise OSError("simulated finalization interruption")

    with monkeypatch.context() as patch:
        patch.setattr(deploy.os, "replace", interrupted)
        with pytest.raises(OSError, match="finalization interruption"):
            deploy.activate(root, stage, REVISION, "state-1", target, cloud)
    assert cloud.active == target
    assert not (stage / "06-finalized.json").exists()
    result = deploy.activate(root, stage, REVISION, "state-1", target, cloud)
    assert result["status"] == "promoted_and_verified"
    assert promote.check_current(root)["model_version"] == "candidate-v2"
    assert cloud.calls.count("route") == 1


def test_main_guard_runs_before_any_cloud_call(cloud_operation, monkeypatch):
    root, stage, cloud = cloud_operation

    def refuse(*args):
        raise ValueError("Installation requires the main branch")

    monkeypatch.setattr(promote, "require_main_checkout", refuse)
    with pytest.raises(ValueError, match="main branch"):
        deploy.deploy_candidate(root, stage, IMAGE, REVISION, "state-1", cloud)
    assert cloud.calls == []


def test_gcloud_deploy_command_never_routes_production(monkeypatch):
    commands = []
    backend = deploy.GCloud()
    monkeypatch.setattr(backend, "run", lambda *args, **kwargs: commands.append(args))
    plan = {
        "service": "team",
        "image": IMAGE,
        "tag": "test-tag",
        "revision_suffix": "l7-test",
        "model_dir": "/app/artifacts/versions/candidate/hash",
        "project": "test-project",
        "region": "europe-west1",
    }
    backend.deploy(plan)
    assert "--no-traffic" in commands[0]
    assert f"--image={IMAGE}" in commands[0]
    assert (
        "--update-env-vars=MODEL_DIR=/app/artifacts/versions/candidate/hash"
        in commands[0]
    )
    assert not any("--allow-unauthenticated" in arg for arg in commands[0])


def test_installed_bytes_changed_during_traffic_switch_do_not_finalize(
    cloud_operation, monkeypatch
):
    root, stage, cloud = cloud_operation
    receipt = deploy.deploy_candidate(root, stage, IMAGE, REVISION, "state-1", cloud)
    original = cloud.route

    def tamper_after_route(plan):
        original(plan)
        (root / "artifacts/accepted/candidate-v2/model.joblib").write_bytes(b"tampered")

    monkeypatch.setattr(cloud, "route", tamper_after_route)
    with pytest.raises(ValueError, match="Checksum mismatch"):
        deploy.activate(
            root,
            stage,
            REVISION,
            "state-1",
            receipt["plan"]["candidate_revision"],
            cloud,
        )
    assert promote.check_current(root)["model_version"] == "accepted-v1"
    assert not (stage / "06-finalized.json").exists()


@pytest.mark.parametrize(
    "url",
    [
        "http://service.run.app/health",
        "https://other.example/health",
        "https://user@service.run.app/health",
    ],
)
def test_token_is_not_requested_for_an_unexpected_host(monkeypatch, url):
    backend = deploy.GCloud()

    def must_not_authenticate(*args):
        pytest.fail("No identity token should be obtained for this host")

    monkeypatch.setattr(backend, "run", must_not_authenticate)
    with pytest.raises(ValueError, match="Cloud Run HTTPS"):
        backend.request(url)
