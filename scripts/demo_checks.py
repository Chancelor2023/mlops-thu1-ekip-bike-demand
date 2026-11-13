"""Read-only checks used by demo.sh; never train, score held test or deploy."""

import argparse
import hashlib
import json
import math
import os
import socket
import sys
import time
from pathlib import Path

from lab8_observe import send_request


def verify_bundle(root):
    selection = json.loads((root / "reports/final-model-selection.json").read_bytes())
    folder = root / selection["bundle_path"]
    for name in ("model.joblib", "model-metadata.json"):
        actual = hashlib.sha256((folder / name).read_bytes()).hexdigest()
        if actual != selection["checksums"][name]:
            raise ValueError(f"Bundle checksum mismatch: {name}")
    metadata = json.loads((folder / "model-metadata.json").read_bytes())
    if (
        metadata["model_version"] != selection["model_version"]
        or metadata["features"] != selection["features"]
        or metadata["model_sha256"] != selection["checksums"]["model.joblib"]
    ):
        raise ValueError("Bundle metadata differs from the frozen selection")
    print(
        "PASS accepted model and metadata checksums; model="
        + selection["model_version"]
    )
    print("Model SHA-256: " + selection["checksums"]["model.joblib"])
    return selection


def verify_image(path, revision):
    images = json.loads(path.read_bytes())
    if len(images) != 1:
        raise ValueError("Expected exactly one inspected image")
    image = images[0]
    env = dict(item.split("=", 1) for item in image["Config"].get("Env", []))
    if env.get("CODE_REVISION") != revision:
        raise ValueError("Image CODE_REVISION does not match the presented Git commit")
    if env.get("MODEL_DIR") != "/app/artifacts":
        raise ValueError("Unexpected image MODEL_DIR")
    print(f"PASS image {image['Id']}; code={revision}")


def check_health(record, model, code, model_sha=None):
    body = record.get("response")
    if (
        record.get("http_status") != 200
        or not isinstance(body, dict)
        or body.get("status") != "ok"
        or body.get("model_version") != model
        or body.get("code_revision") != code
        or (model_sha is not None and body.get("model_sha256") != model_sha)
    ):
        raise ValueError("Health status or retained model/code/hash identity differs")


def check_prediction(record, model):
    body = record.get("response")
    value = body.get("prediction") if isinstance(body, dict) else None
    if (
        record.get("http_status") != 200
        or not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        or value < 0
        or body.get("model_version") != model
    ):
        raise ValueError(
            "Prediction must be HTTP 200, finite, nonnegative and correctly versioned"
        )


def observe(args, path, body=None):
    record = send_request(
        args.url.rstrip("/") + path,
        method="GET" if body is None else "POST",
        payload=body,
        timeout=5 if args.action == "wait" else 15,
    )
    with args.output.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(record, allow_nan=False) + "\n")
    return record


def display(record):
    print(f"HTTP {record['http_status']}; request_id={record.get('request_id')}")
    if record.get("response") is not None:
        print(json.dumps(record["response"], indent=2, allow_nan=False))
    if record.get("error") and record.get("http_status") is None:
        print("Transport error: " + record["error"])


def run_http(args, selection):
    if args.cloud:
        if not args.url.startswith("https://") or not os.environ.get("ID_TOKEN"):
            raise ValueError("Cloud checks require HTTPS and ID_TOKEN in memory")
    elif os.environ.get("ID_TOKEN"):
        raise ValueError("Unset ID_TOKEN for local requests")
    if args.action == "wait":
        deadline = time.monotonic() + 120
        print(
            f"Waiting for /health HTTP {args.status} (maximum about 125 s)...",
            flush=True,
        )
        while True:
            record = observe(args, "/health")
            if record["http_status"] == args.status:
                if args.status == 200:
                    check_health(
                        record,
                        selection["model_version"],
                        args.code,
                        None if args.cloud else selection["checksums"]["model.joblib"],
                    )
                display(record)
                return
            if time.monotonic() >= deadline:
                display(record)
                raise ValueError(
                    "Readiness deadline exceeded; inspect retained requests/container logs"
                )
            time.sleep(1)
    valid = json.loads((args.root / "reports/lab-08/payloads.json").read_bytes())[0]
    invalid = {**valid, "hr": 24}
    if args.action == "health":
        record = observe(args, "/health")
        display(record)
        check_health(
            record,
            selection["model_version"],
            args.code,
            None if args.cloud else selection["checksums"]["model.joblib"],
        )
    else:
        record = observe(args, "/predict", valid if args.action == "valid" else invalid)
        display(record)
        if args.action == "valid":
            check_prediction(record, selection["model_version"])
        elif record["http_status"] != 422:
            raise ValueError("Invalid hr=24 must return HTTP 422")
    print("PASS " + args.action)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=["bundle", "image", "port", "wait", "health", "valid", "invalid"],
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--image-inspect", type=Path)
    parser.add_argument("--code")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--status", type=int, choices=[200, 503], default=200)
    parser.add_argument("--cloud", action="store_true")
    args = parser.parse_args()
    try:
        if args.action == "image":
            verify_image(args.image_inspect, args.code)
        elif args.action == "port":
            with socket.socket() as server:
                server.bind(("127.0.0.1", 8000))
            print("PASS local port 8000 is available")
        else:
            selection = verify_bundle(args.root)
            if args.action != "bundle":
                if args.output is None or (args.status == 200 and not args.code):
                    raise ValueError(
                        "HTTP checks need an output path and expected code"
                    )
                run_http(args, selection)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"FAIL demo check: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
