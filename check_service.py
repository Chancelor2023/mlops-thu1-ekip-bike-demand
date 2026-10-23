#!/usr/bin/env python3
"""Check a running Lab 5 service over HTTP."""

import argparse
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def request_json(url: str, method: str, body: dict | None = None):
    data = None if body is None else json.dumps(body).encode()
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"

    token = os.environ.get("ID_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=15) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {}
        return exc.code, payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="Service base URL")
    parser.add_argument("--expected-model", required=True)
    parser.add_argument("--expected-revision", required=True)
    parser.add_argument("--valid-payload", required=True, help="Valid /predict JSON")
    parser.add_argument(
        "--invalid-payload", required=True, help="Invalid /predict JSON"
    )
    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    checks: list[tuple[str, bool, str]] = []

    try:
        status, health = request_json(f"{base_url}/health", "GET")
        checks.extend(
            [
                ("health HTTP 200", status == 200, f"observed HTTP {status}"),
                (
                    "ready",
                    status == 200 and health.get("status") == "ok",
                    f"observed status={health.get('status')!r}",
                ),
                (
                    "model",
                    health.get("model_version") == args.expected_model,
                    f"expected {args.expected_model!r}, observed {health.get('model_version')!r}",
                ),
                (
                    "revision",
                    health.get("code_revision") == args.expected_revision,
                    f"expected {args.expected_revision!r}, observed {health.get('code_revision')!r}",
                ),
            ]
        )

        valid_payload = json.loads(args.valid_payload)
        status, prediction = request_json(f"{base_url}/predict", "POST", valid_payload)
        valid_ok = (
            status == 200
            and isinstance(prediction.get("prediction"), (int, float))
            and prediction.get("model_version") == args.expected_model
        )
        checks.append(("valid prediction", valid_ok, f"observed HTTP {status}"))

        invalid_payload = json.loads(args.invalid_payload)
        status, _ = request_json(f"{base_url}/predict", "POST", invalid_payload)
        checks.append(
            ("invalid request rejected", status == 422, f"observed HTTP {status}")
        )

    except (URLError, TimeoutError, json.JSONDecodeError, TypeError, ValueError) as exc:
        # Do not print request headers or environment values; ID_TOKEN stays secret.
        print(f"FAIL service check: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    failed = False
    for name, passed, detail in checks:
        print(f"{'PASS' if passed else 'FAIL'} {name}: {detail}")
        failed |= not passed

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
