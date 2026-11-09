"""Offline transport and contract tests; never call Cloud Run or train a model."""

import importlib.util
import io
import json
import sys
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.lab8
ROOT = Path(__file__).resolve().parents[1]
MODEL = "baseline-4df84bfe8121"
CODE = "ea37b8a45d4a6738585d9de7d0f95d624ad1d3be"


@pytest.fixture
def observer(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "lab8_observe_tested", ROOT / "scripts/lab8_observe.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.delenv("ID_TOKEN", raising=False)
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)
    return module


class Response:
    def __init__(self, body=b"{}", code=200, request_id="response-id"):
        self.body = body
        self.code = code
        self.headers = {"X-Request-ID": request_id}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.body


def transport(observer, monkeypatch, response):
    calls = []

    def open_request(request, timeout):
        calls.append((request, timeout))
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(
        observer.urllib.request,
        "build_opener",
        lambda *args: SimpleNamespace(open=open_request),
    )
    return calls


def test_token_is_sent_only_in_header_and_request_id_is_retained(observer, monkeypatch):
    token = "synthetic-token-not-a-real-credential"
    monkeypatch.setenv("ID_TOKEN", token)
    calls = transport(observer, monkeypatch, Response(b'{"status":"ok"}'))
    record = observer.send_request("https://service.example/health", timeout=17)
    assert calls[0][0].get_header("Authorization") == "Bearer " + token
    assert calls[0][1] == 17
    assert record["request_id"] == "response-id"
    assert token not in json.dumps(record)


def test_local_http_does_not_require_a_token(observer, monkeypatch):
    calls = transport(observer, monkeypatch, Response())
    observer.send_request("http://127.0.0.1:8000/health")
    assert not calls[0][0].has_header("Authorization")


def test_token_is_not_sent_over_http(observer, monkeypatch):
    monkeypatch.setenv("ID_TOKEN", "synthetic-token")
    calls = transport(observer, monkeypatch, Response())
    with pytest.raises(ValueError, match="requires HTTPS"):
        observer.send_request("http://127.0.0.1:8000/health")
    assert not calls


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/test",
        "https://user:password@service.example/health",
        "https://service.example/health?token=test",
        "https://service.example/health#x",
    ],
)
def test_unsafe_urls_are_rejected_before_transport(observer, monkeypatch, url):
    calls = transport(observer, monkeypatch, Response())
    with pytest.raises(ValueError):
        observer.send_request(url)
    assert not calls


def test_redirects_do_not_forward_credentials(observer):
    assert (
        observer.NoRedirect().redirect_request(
            None, None, 302, "Found", {}, "https://other.example/"
        )
        is None
    )


def test_http_errors_keep_body_and_request_id(observer, monkeypatch):
    error = urllib.error.HTTPError(
        "https://service.example/predict",
        422,
        "invalid",
        {"X-Request-ID": "invalid-id"},
        io.BytesIO(b'{"detail":"bad input"}'),
    )
    transport(observer, monkeypatch, error)
    record = observer.send_request("https://service.example/predict", "POST", {})
    assert record["http_status"] == 422
    assert record["request_id"] == "invalid-id"
    assert record["response"] == {"detail": "bad input"}
    assert record["response_body"] == '{"detail":"bad input"}'


@pytest.mark.parametrize(
    "body", [b"not json", b"[]", b'{"prediction":NaN}', b'{"prediction":1e309}']
)
def test_malformed_responses_are_recorded_without_invalid_jsonl(
    observer, monkeypatch, body
):
    transport(observer, monkeypatch, Response(body))
    record = observer.send_request("https://service.example/predict")
    assert record["response"] is None
    assert record["response_body"] == body.decode()
    json.dumps(record, allow_nan=False)


def test_timeout_is_a_recorded_failed_attempt(observer, monkeypatch):
    transport(observer, monkeypatch, TimeoutError("synthetic timeout"))
    record = observer.send_request("https://service.example/predict")
    assert record["http_status"] is None
    assert record["request_id"] is None
    assert record["error"] == "synthetic timeout"


def phase(observer, monkeypatch, tmp_path, mode="healthy", expected_sha=None):
    calls = []
    valid_count = 0

    def request(url, method="GET", payload=None, timeout=15):
        nonlocal valid_count
        calls.append((url, method, payload, timeout))
        if url.endswith("/health"):
            code = "unexpected-code" if mode == "wrong_code" else CODE
            status = 200
            body = {"status": "ok", "model_version": MODEL, "code_revision": code}
            if mode == "not_ready":
                body["status"] = "unavailable"
            if mode == "wrong_model":
                body["model_version"] = "unexpected-model"
            if mode == "hash_present":
                body["model_sha256"] = "a" * 64
        elif (
            "hr" not in payload or "unexpected_field" in payload or payload["hr"] == 24
        ):
            status, body = 422, {"detail": "synthetic validation rejection"}
        else:
            valid_count += 1
            status, body = 200, {"prediction": 1.0, "model_version": MODEL}
            if mode == "three_failures" and valid_count <= 3:
                status, body = 503, {"detail": "synthetic unavailable model"}
            if mode == "wrong_prediction_model":
                body["model_version"] = "unexpected-model"
        if mode == "forbidden":
            status, body = 403, {"detail": "synthetic forbidden"}
        return {
            "timestamp_utc": "2026-11-09T00:00:00+00:00",
            "completed_at_utc": "2026-11-09T00:00:01+00:00",
            "http_status": status,
            "duration_ms": float(len(calls)),
            "request_id": f"synthetic-{len(calls)}",
            "response": body,
            "response_body": json.dumps(body),
            "error": None if status < 400 else json.dumps(body),
        }

    monkeypatch.setattr(observer, "send_request", request)
    args = SimpleNamespace(
        url="https://service.example",
        phase="recovery",
        expected_model_version=MODEL,
        expected_code_revision=CODE,
        expected_model_sha256=expected_sha,
        timeout=15,
        payloads=ROOT / "reports/lab-08/payloads.json",
        output_dir=tmp_path,
    )
    exit_code = observer.run_observation(args)
    path = next(tmp_path.glob("observations_recovery_*.jsonl"))
    records = [json.loads(line) for line in path.read_text().splitlines()]
    return exit_code, records, calls, args


def test_complete_phase_records_exact_counts_ids_and_frozen_payload_hash(
    observer, monkeypatch, tmp_path
):
    code, records, calls, args = phase(observer, monkeypatch, tmp_path)
    assert code == 0
    summary = records[-1]
    assert summary["phase_verified"] is True
    assert summary["valid_attempts"] == summary["successful_predictions"] == 30
    assert summary["invalid_rejections_422"] == 3
    assert summary["health_usable"] == 2
    assert summary["first_signal"] is None
    assert summary["successful_prediction_latency"]["n"] == 30
    assert len(calls) == 35 and all(v[3] == 15 for v in calls)
    responses = [
        v
        for v in records
        if v["type"] in {"health", "valid_prediction", "invalid_prediction"}
    ]
    assert len({v["request_id"] for v in responses}) == 35
    import hashlib

    assert (
        records[0]["payloads_sha256"]
        == hashlib.sha256(args.payloads.read_bytes()).hexdigest()
    )


@pytest.mark.parametrize("mode", ["wrong_code", "wrong_model", "not_ready"])
def test_health_failure_cannot_be_hidden_by_30_successful_predictions(
    observer, monkeypatch, tmp_path, mode
):
    code, records, _, _ = phase(observer, monkeypatch, tmp_path, mode)
    assert code == 2
    assert records[-1]["successful_predictions"] == 30
    assert records[-1]["phase_verified"] is False
    signals = [v for v in records if v["type"] == "signal"]
    assert len(signals) == 1 and signals[0]["source_type"] == "health"


@pytest.mark.parametrize("mode,expected", [("healthy", 2), ("hash_present", 0)])
def test_optional_hash_is_checked_without_inventing_a_legacy_field(
    observer, monkeypatch, tmp_path, mode, expected
):
    code, records, _, _ = phase(
        observer, monkeypatch, tmp_path, mode, expected_sha="a" * 64
    )
    assert code == expected
    assert records[-1]["phase_verified"] == (expected == 0)


def test_three_failed_predictions_emit_one_signal_with_the_third_request_id(
    observer, monkeypatch, tmp_path
):
    code, records, _, _ = phase(observer, monkeypatch, tmp_path, "three_failures")
    signals = [v for v in records if v["type"] == "signal"]
    valid = [v for v in records if v["type"] == "valid_prediction"]
    assert code == 2 and records[-1]["successful_predictions"] == 27
    assert len(signals) == 1
    assert signals[0]["reason"] == "three_consecutive_valid_failures"
    assert signals[0]["request_id"] == valid[2]["request_id"]
    assert signals[0]["timestamp_utc"] == valid[2]["completed_at_utc"]


def test_wrong_prediction_identity_is_signalled_on_the_first_response(
    observer, monkeypatch, tmp_path
):
    code, records, _, _ = phase(
        observer, monkeypatch, tmp_path, "wrong_prediction_model"
    )
    assert code == 2
    signal = next(v for v in records if v["type"] == "signal")
    assert signal["reason"] == "unexpected_model_identity"
    assert signal["request_id"] == "synthetic-2"


def test_403_is_not_counted_as_a_successful_phase(observer, monkeypatch, tmp_path):
    code, records, _, _ = phase(observer, monkeypatch, tmp_path, "forbidden")
    assert code == 2
    assert records[-1]["successful_predictions"] == 0
    assert records[-1]["successful_prediction_latency"] is None


def test_main_returns_nonzero_for_incomplete_collection(
    observer, monkeypatch, tmp_path
):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "lab8_observe.py",
            "--url",
            "https://service.example",
            "--phase",
            "normal",
            "--expected-model-version",
            MODEL,
            "--expected-code-revision",
            CODE,
            "--payloads",
            str(tmp_path / "missing.json"),
        ],
    )
    assert observer.main() == 3


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf"])
def test_timeout_must_be_finite_and_positive(observer, monkeypatch, value):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "lab8_observe.py",
            "--url",
            "https://service.example",
            "--phase",
            "normal",
            "--expected-model-version",
            MODEL,
            "--expected-code-revision",
            CODE,
            "--timeout",
            value,
        ],
    )
    with pytest.raises(SystemExit) as error:
        observer.main()
    assert error.value.code == 2


@pytest.mark.parametrize(
    "url",
    [
        "https://user:synthetic-password@service.example",
        "https://service.example?token=synthetic-query-secret",
    ],
)
def test_phase_rejects_unsafe_url_before_printing_or_writing(
    observer, tmp_path, capsys, url
):
    with pytest.raises(ValueError):
        observer.run_observation(SimpleNamespace(url=url))
    captured = capsys.readouterr()
    assert not captured.out and not captured.err
    assert not list(tmp_path.iterdir())
