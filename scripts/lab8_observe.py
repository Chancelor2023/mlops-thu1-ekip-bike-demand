"""Lab 8 — Sequential API observation and incident evidence collection."""

import argparse
import hashlib
import json
import math
import os
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

FEATURES = (
    "season",
    "yr",
    "mnth",
    "hr",
    "holiday",
    "weekday",
    "workingday",
    "weathersit",
    "temp",
    "atemp",
    "hum",
    "windspeed",
)

PAYLOADS_PATH = Path("reports/lab-08/payloads.json")
OUTPUT_DIR = Path("reports/lab-08")


def utc_now():
    """Return the current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Keep a bearer token on the selected endpoint; record redirects as failures."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate_url(url):
    """Reject URL credentials before any URL can be printed or used."""
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Use an HTTP(S) URL without credentials, query or fragment")
    return parsed


def send_request(url, method="GET", payload=None, timeout=15):
    """Capture response bodies and request IDs; never record request headers."""
    parsed = validate_url(url)
    token = os.environ.get("ID_TOKEN", "").strip()
    if token and parsed.scheme != "https":
        raise ValueError("ID_TOKEN requires HTTPS; unset it for a local HTTP check")
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if payload is not None:
        data = json.dumps(payload, allow_nan=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    started = time.monotonic()
    timestamp = utc_now()
    request_id = None
    try:
        opener = urllib.request.build_opener(NoRedirect())
        try:
            response = opener.open(request, timeout=timeout)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            status = response.code
            request_id = response.headers.get("X-Request-ID")
            body = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return {
            "timestamp_utc": timestamp,
            "completed_at_utc": utc_now(),
            "http_status": None,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
            "request_id": request_id,
            "response": None,
            "response_body": None,
            "error": str(error),
        }
    try:
        response_json = json.loads(body)
        # Unexpected shapes and non-finite JSON must fail as observations, not
        # crash the collector or be written as invalid JSONL.
        if not isinstance(response_json, dict):
            raise ValueError("JSON response is not an object")
        json.dumps(response_json, allow_nan=False)
    except (ValueError, TypeError):
        response_json = None
    return {
        "timestamp_utc": timestamp,
        "completed_at_utc": utc_now(),
        "http_status": status,
        "duration_ms": round((time.monotonic() - started) * 1000, 2),
        "request_id": request_id,
        "response": response_json,
        "response_body": body,
        "error": body
        if status >= 400
        else (
            "response is not a finite JSON object" if response_json is None else None
        ),
    }


def save_record(file, record):
    """Append one JSON record to the evidence file."""
    file.write(json.dumps(record, allow_nan=False) + "\n")
    file.flush()


def check_health(
    base_url,
    phase,
    label,
    expected_version,
    output,
    *,
    expected_code,
    expected_sha=None,
    timeout=15,
):
    """Compare health to independently retained model AND code expectations."""
    result = send_request(f"{base_url}/health", timeout=timeout)
    response = result["response"] or {}
    version = response.get("model_version")
    code = response.get("code_revision")
    sha = response.get("model_sha256")
    identity_matches = (
        version == expected_version
        and code == expected_code
        and (expected_sha is None or sha == expected_sha)
    )
    record = {
        "phase": phase,
        "type": "health",
        "label": label,
        **result,
        "health_status": response.get("status"),
        "model_version": version,
        "code_revision": code,
        "model_sha256": sha,
        "expected_model_version": expected_version,
        "expected_code_revision": expected_code,
        "expected_model_sha256": expected_sha,
        "identity_matches": identity_matches,
        "usable": result["http_status"] == 200
        and response.get("status") == "ok"
        and identity_matches,
    }
    save_record(output, record)
    print(
        f"[HEALTH {label}] HTTP {result['http_status']} | model={version} "
        f"| identity_matches={identity_matches} | usable={record['usable']}",
        flush=True,
    )
    return record


def make_invalid_payloads(valid_payload):
    """Build three deliberately invalid requests."""
    missing_field = dict(valid_payload)
    missing_field.pop("hr")

    extra_field = dict(valid_payload)
    extra_field["unexpected_field"] = 123

    out_of_range = dict(valid_payload)
    out_of_range["hr"] = 24

    return [
        ("missing_field", missing_field),
        ("extra_field", extra_field),
        ("out_of_range", out_of_range),
    ]


def run_observation(args):
    """Execute one complete observation phase."""
    validate_url(args.url)
    with args.payloads.open("r", encoding="utf-8") as file:
        payloads = json.load(file)

    if not isinstance(payloads, list) or len(payloads) != 10:
        raise ValueError("payloads.json must contain exactly 10 payloads.")

    for index, payload in enumerate(payloads, start=1):
        if not isinstance(payload, dict) or set(payload) != set(FEATURES):
            raise ValueError(
                f"Payload {index} must contain exactly the 12 API predictors."
            )

    args.output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_path = args.output_dir / f"observations_{args.phase}_{timestamp}.jsonl"

    base_url = args.url.rstrip("/")
    started = time.monotonic()
    first_signal = None
    consecutive_failures = 0
    successful_latencies = []
    health_records = []
    valid_attempts = 0
    successful_predictions = 0
    failed_predictions = 0
    invalid_attempts = 0
    invalid_rejections = 0

    print(f"Phase: {args.phase}")
    print(f"API: {base_url}")
    print(f"Expected model version: {args.expected_model_version}")
    print(f"Evidence file: {output_path}")
    print()

    with output_path.open("x", encoding="utf-8") as output:

        def signal(reason, observation):
            nonlocal first_signal
            if first_signal is not None:
                return
            first_signal = {
                "type": "signal",
                "phase": args.phase,
                "reason": reason,
                "timestamp_utc": observation.get(
                    "completed_at_utc", observation["timestamp_utc"]
                ),
                "source_type": observation["type"],
                "request_id": observation.get("request_id"),
                "http_status": observation.get("http_status"),
                "model_version": observation.get("model_version"),
                "code_revision": observation.get("code_revision"),
            }
            save_record(output, first_signal)
            print(f"[SIGNAL] {reason} at {first_signal['timestamp_utc']}", flush=True)

        save_record(
            output,
            {
                "phase": args.phase,
                "type": "phase_start",
                "timestamp_utc": utc_now(),
                "expected_model_version": args.expected_model_version,
                "expected_code_revision": args.expected_code_revision,
                "expected_model_sha256": args.expected_model_sha256,
                "payloads_sha256": hashlib.sha256(
                    args.payloads.read_bytes()
                ).hexdigest(),
                "timeout_seconds": args.timeout,
                "expected_valid_attempts": 30,
                "expected_invalid_attempts": 3,
            },
        )

        health = check_health(
            base_url,
            args.phase,
            "start",
            args.expected_model_version,
            output,
            expected_code=args.expected_code_revision,
            expected_sha=args.expected_model_sha256,
            timeout=args.timeout,
        )
        health_records.append(health)
        if not health["usable"]:
            signal("health_unusable_or_identity_mismatch", health)
        time.sleep(1)

        # 10 payloads, each submitted 3 times, sequentially.
        for payload_index, payload in enumerate(payloads, start=1):
            for attempt in range(1, 4):
                valid_attempts += 1

                result = send_request(
                    f"{base_url}/predict",
                    method="POST",
                    payload=payload,
                    timeout=args.timeout,
                )

                response = result["response"] or {}
                prediction = response.get("prediction")
                model_version = response.get("model_version")

                prediction_is_valid = (
                    isinstance(prediction, (int, float))
                    and not isinstance(prediction, bool)
                    and math.isfinite(prediction)
                    and prediction >= 0
                )

                identity_matches = model_version == args.expected_model_version

                success = (
                    result["http_status"] == 200
                    and prediction_is_valid
                    and identity_matches
                )

                if success:
                    successful_predictions += 1
                    successful_latencies.append(result["duration_ms"])
                    consecutive_failures = 0
                else:
                    failed_predictions += 1
                    consecutive_failures += 1

                record = {
                    "phase": args.phase,
                    "type": "valid_prediction",
                    "payload_id": payload_index,
                    "attempt": attempt,
                    **result,
                    "prediction": prediction,
                    "model_version": model_version,
                    "prediction_is_valid": prediction_is_valid,
                    "identity_matches": identity_matches,
                    "success": success,
                    "consecutive_valid_failures": consecutive_failures,
                }

                save_record(output, record)
                if model_version is not None and not identity_matches:
                    signal("unexpected_model_identity", record)
                elif consecutive_failures >= 3:
                    signal("three_consecutive_valid_failures", record)

                print(
                    f"[VALID {valid_attempts}/30] "
                    f"payload={payload_index} attempt={attempt} "
                    f"| HTTP {result['http_status']} "
                    f"| {result['duration_ms']} ms "
                    f"| success={success}",
                    flush=True,
                )

                if valid_attempts < 30:
                    time.sleep(1)

        # Invalid requests are measured separately.
        for invalid_id, (invalid_type, payload) in enumerate(
            make_invalid_payloads(payloads[0]),
            start=1,
        ):
            invalid_attempts += 1

            result = send_request(
                f"{base_url}/predict",
                method="POST",
                payload=payload,
                timeout=args.timeout,
            )

            rejected = result["http_status"] == 422
            if rejected:
                invalid_rejections += 1

            record = {
                "phase": args.phase,
                "type": "invalid_prediction",
                "invalid_id": invalid_id,
                "invalid_type": invalid_type,
                **result,
                "rejected_as_expected": rejected,
            }

            save_record(output, record)

            print(
                f"[INVALID {invalid_id}/3] {invalid_type} "
                f"| HTTP {result['http_status']} "
                f"| rejected_as_expected={rejected}",
                flush=True,
            )

            if invalid_id < 3:
                time.sleep(1)

        time.sleep(1)

        health = check_health(
            base_url,
            args.phase,
            "end",
            args.expected_model_version,
            output,
            expected_code=args.expected_code_revision,
            expected_sha=args.expected_model_sha256,
            timeout=args.timeout,
        )
        health_records.append(health)
        if not health["usable"]:
            signal("health_unusable_or_identity_mismatch", health)

        success_rate = (
            successful_predictions / valid_attempts * 100 if valid_attempts else 0
        )

        phase_verified = (
            valid_attempts == successful_predictions == 30
            and invalid_attempts == invalid_rejections == 3
            and len(health_records) == 2
            and all(record["usable"] for record in health_records)
        )
        latency = None
        if successful_latencies:
            ordered = sorted(successful_latencies)
            # Linear-interpolated percentile; same definition in every phase.
            position = (len(ordered) - 1) * 0.95
            lower = math.floor(position)
            upper = math.ceil(position)
            latency = {
                "n": len(ordered),
                "population": "successful_valid_predictions",
                "median_ms": statistics.median(ordered),
                "p95_ms": ordered[lower]
                + (ordered[upper] - ordered[lower]) * (position - lower),
                "max_ms": ordered[-1],
            }
        summary = {
            "phase": args.phase,
            "type": "summary",
            "timestamp_utc": utc_now(),
            "valid_attempts": valid_attempts,
            "successful_predictions": successful_predictions,
            "failed_predictions": failed_predictions,
            "valid_success_rate_percent": round(success_rate, 2),
            "invalid_attempts": invalid_attempts,
            "invalid_rejections_422": invalid_rejections,
            "expected_model_version": args.expected_model_version,
            "expected_code_revision": args.expected_code_revision,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "health_usable": sum(record["usable"] for record in health_records),
            "first_signal": first_signal,
            "successful_prediction_latency": latency,
            "phase_verified": phase_verified,
            "scope": "HTTP observations only; cloud revision/log correlation is separate",
        }

        save_record(output, summary)

    print("\n--- SUMMARY ---")
    print(f"Valid attempts: {valid_attempts}/30")
    print(f"Successful predictions: {successful_predictions}")
    print(f"Failed predictions: {failed_predictions}")
    print(f"Success rate: {success_rate:.2f}%")
    print(f"Invalid requests rejected: {invalid_rejections}/3")
    print(f"Phase contract satisfied: {phase_verified}")
    print(f"Evidence saved to: {output_path}")
    return 0 if phase_verified else 2


def main():
    parser = argparse.ArgumentParser(description="Lab 8 sequential API observation.")
    parser.add_argument(
        "--url",
        required=True,
        help="Base URL of the dedicated Cloud Run rehearsal service.",
    )
    parser.add_argument(
        "--phase",
        required=True,
        choices=("normal", "incident", "recovery"),
    )
    parser.add_argument(
        "--expected-model-version",
        required=True,
        help="Verified accepted model version expected for this phase.",
    )
    parser.add_argument(
        "--expected-code-revision",
        required=True,
        help="Independently retained code revision expected from /health.",
    )
    parser.add_argument(
        "--expected-model-sha256",
        help="Optional loaded-model hash expectation; omit for the legacy target API.",
    )
    parser.add_argument("--payloads", type=Path, default=PAYLOADS_PATH)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument(
        "--timeout",
        type=float,
        default=15,
        help="HTTP timeout in seconds (default: 15).",
    )

    args = parser.parse_args()

    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be greater than zero.")

    try:
        return run_observation(args)
    except (OSError, ValueError, KeyboardInterrupt) as error:
        print(
            f"Observation incomplete: {type(error).__name__}: {error}", file=sys.stderr
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
