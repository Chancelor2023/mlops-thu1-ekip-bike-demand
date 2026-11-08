"""Lab 8 — Sequential API observation and incident evidence collection."""

import argparse
import json
import math
import time
import urllib.error
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


def send_request(url, method="GET", payload=None, timeout=10):
    """Send one HTTP request and capture its result."""
    headers = {"Accept": "application/json"}

    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method=method,
    )

    started = time.monotonic()
    timestamp = utc_now()

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.status
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        status = error.code
        body = error.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return {
            "timestamp_utc": timestamp,
            "http_status": None,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
            "response": None,
            "error": str(error),
        }

    try:
        response_json = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        response_json = None

    return {
        "timestamp_utc": timestamp,
        "http_status": status,
        "duration_ms": round((time.monotonic() - started) * 1000, 2),
        "response": response_json,
        "error": None if status < 400 else body,
    }


def save_record(file, record):
    """Append one JSON record to the evidence file."""
    file.write(json.dumps(record, allow_nan=False) + "\n")
    file.flush()


def check_health(base_url, phase, label, expected_version, output):
    """Observe the health endpoint and record model identity."""
    result = send_request(f"{base_url}/health")

    response = result["response"] or {}
    version = response.get("model_version")

    record = {
        "phase": phase,
        "type": "health",
        "label": label,
        **result,
        "health_status": response.get("status"),
        "model_version": version,
        "code_revision": response.get("code_revision"),
        "model_sha256": response.get("model_sha256"),
        "expected_model_version": expected_version,
        "identity_matches": version == expected_version,
    }

    save_record(output, record)
    print(
        f"[HEALTH {label}] HTTP {result['http_status']} "
        f"| model={version} "
        f"| identity_matches={record['identity_matches']}"
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
    with PAYLOADS_PATH.open("r", encoding="utf-8") as file:
        payloads = json.load(file)

    if not isinstance(payloads, list) or len(payloads) != 10:
        raise ValueError("payloads.json must contain exactly 10 payloads.")

    for index, payload in enumerate(payloads, start=1):
        if not isinstance(payload, dict) or set(payload) != set(FEATURES):
            raise ValueError(
                f"Payload {index} must contain exactly the 12 API predictors."
            )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = OUTPUT_DIR / f"observations_{args.phase}_{timestamp}.jsonl"

    base_url = args.url.rstrip("/")
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

    with output_path.open("w", encoding="utf-8") as output:
        save_record(
            output,
            {
                "phase": args.phase,
                "type": "phase_start",
                "timestamp_utc": utc_now(),
                "expected_model_version": args.expected_model_version,
                "expected_valid_attempts": 30,
                "expected_invalid_attempts": 3,
            },
        )

        check_health(
            base_url,
            args.phase,
            "start",
            args.expected_model_version,
            output,
        )
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
                else:
                    failed_predictions += 1

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
                }

                save_record(output, record)

                print(
                    f"[VALID {valid_attempts}/30] "
                    f"payload={payload_index} attempt={attempt} "
                    f"| HTTP {result['http_status']} "
                    f"| {result['duration_ms']} ms "
                    f"| success={success}"
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
                f"| rejected_as_expected={rejected}"
            )

            if invalid_id < 3:
                time.sleep(1)

        time.sleep(1)

        check_health(
            base_url,
            args.phase,
            "end",
            args.expected_model_version,
            output,
        )

        success_rate = (
            successful_predictions / valid_attempts * 100 if valid_attempts else 0
        )

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
        }

        save_record(output, summary)

    print("\n--- SUMMARY ---")
    print(f"Valid attempts: {valid_attempts}/30")
    print(f"Successful predictions: {successful_predictions}")
    print(f"Failed predictions: {failed_predictions}")
    print(f"Success rate: {success_rate:.2f}%")
    print(f"Invalid requests rejected: {invalid_rejections}/3")
    print(f"Evidence saved to: {output_path}")


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
        "--timeout",
        type=float,
        default=10,
        help="HTTP timeout in seconds (default: 10).",
    )

    args = parser.parse_args()

    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero.")

    run_observation(args)


if __name__ == "__main__":
    main()
