"""Offline demo guards; no Docker, cloud calls or real model predictions."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def demo(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    monkeypatch.delenv("ID_TOKEN", raising=False)
    spec = importlib.util.spec_from_file_location(
        "demo_checks_tested", ROOT / "scripts/demo_checks.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_local_hash_is_required_but_legacy_cloud_can_omit_it(demo):
    record = {
        "http_status": 200,
        "response": {"status": "ok", "model_version": "model", "code_revision": "code"},
    }
    demo.check_health(record, "model", "code")
    with pytest.raises(ValueError, match="identity differs"):
        demo.check_health(record, "model", "code", "expected-hash")
    record["response"]["model_sha256"] = "expected-hash"
    demo.check_health(record, "model", "code", "expected-hash")
    with pytest.raises(ValueError):
        demo.check_health(record, "model", "other-code", "expected-hash")


@pytest.mark.parametrize("prediction", [-1, float("nan"), float("inf"), True, "7"])
def test_invalid_prediction_cannot_pass(demo, prediction):
    with pytest.raises(ValueError):
        demo.check_prediction(
            {
                "http_status": 200,
                "response": {"prediction": prediction, "model_version": "model"},
            },
            "model",
        )
    demo.check_prediction(
        {"http_status": 200, "response": {"prediction": 7.0, "model_version": "model"}},
        "model",
    )


def test_image_revision_must_match_presented_commit(demo, tmp_path):
    path = tmp_path / "image.json"
    path.write_text(
        json.dumps(
            [
                {
                    "Id": "sha256:synthetic",
                    "Config": {
                        "Env": ["CODE_REVISION=wrong", "MODEL_DIR=/app/artifacts"]
                    },
                }
            ]
        )
    )
    with pytest.raises(ValueError, match="presented Git commit"):
        demo.verify_image(path, "expected")


def test_checksum_failure_stops_before_any_model_load(demo, tmp_path):
    (tmp_path / "reports").mkdir()
    bundle = tmp_path / "artifacts/accepted/model"
    bundle.mkdir(parents=True)
    (bundle / "model.joblib").write_bytes(b"not a valid model")
    (tmp_path / "reports/final-model-selection.json").write_text(
        json.dumps(
            {
                "bundle_path": "artifacts/accepted/model",
                "checksums": {"model.joblib": "wrong"},
            }
        )
    )
    with pytest.raises(ValueError, match="checksum mismatch"):
        demo.verify_bundle(tmp_path)


def test_expected_503_wait_preserves_initial_transport_failure(
    demo, tmp_path, monkeypatch
):
    args = SimpleNamespace(
        action="wait",
        cloud=False,
        url="http://127.0.0.1:8000",
        status=503,
        code="code",
        output=tmp_path / "requests.jsonl",
    )
    responses = iter(
        [
            {
                "http_status": None,
                "response": None,
                "request_id": None,
                "error": "connection refused",
            },
            {
                "http_status": 503,
                "response": {"detail": "Model unavailable"},
                "request_id": "server-id",
                "error": "Model unavailable",
            },
        ]
    )
    monkeypatch.setattr(demo, "send_request", lambda *a, **kw: next(responses))
    monkeypatch.setattr(demo.time, "sleep", lambda seconds: None)
    demo.run_http(args, {"model_version": "model"})
    records = [json.loads(line) for line in args.output.read_text().splitlines()]
    assert [r["http_status"] for r in records] == [None, 503]


def test_local_requests_refuse_inherited_bearer_token(demo, monkeypatch):
    monkeypatch.setenv("ID_TOKEN", "synthetic-not-a-real-token")
    args = SimpleNamespace(action="health", cloud=False)
    with pytest.raises(ValueError, match="Unset ID_TOKEN"):
        demo.run_http(args, {})


def test_readiness_timeout_is_failure_and_retains_attempt(demo, tmp_path, monkeypatch):
    args = SimpleNamespace(
        action="wait",
        cloud=False,
        url="http://127.0.0.1:8000",
        status=200,
        code="code",
        output=tmp_path / "timeout.jsonl",
    )
    monkeypatch.setattr(
        demo,
        "send_request",
        lambda *a, **kw: {
            "http_status": None,
            "response": None,
            "request_id": None,
            "error": "timeout",
        },
    )
    clock = iter([0, 121])
    monkeypatch.setattr(demo.time, "monotonic", lambda: next(clock))
    with pytest.raises(ValueError, match="Readiness deadline"):
        demo.run_http(args, {"model_version": "model"})
    assert json.loads(args.output.read_text())["error"] == "timeout"
