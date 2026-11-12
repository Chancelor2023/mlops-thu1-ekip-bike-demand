
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

def request(path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    started = datetime.now(timezone.utc).isoformat()
    try:
        try:
            response = urlopen(Request("http://127.0.0.1:8000" + path,
                                      data=data, headers=headers), timeout=3)
        except HTTPError as error:
            response = error
        with response:
            body = response.read().decode("utf-8", errors="replace")
            return {"started_at_utc": started, "http_status": response.code,
                    "request_id": response.headers.get("X-Request-ID"),
                    "response_body": body}
    except (URLError, TimeoutError, OSError) as error:
        return {"started_at_utc": started, "http_status": None,
                "error": str(error)}

attempts = []
deadline = time.monotonic() + 120
while True:
    health = request("/health")
    attempts.append(health)
    if health["http_status"] is not None or time.monotonic() >= deadline:
        break
    time.sleep(2)

payloads = json.loads(Path("/lab8-inputs/payloads.json").read_text())
valid = request("/predict", payloads[0])
invalid = request("/predict", {**payloads[0], "hr": 24})
checks = {"health_503": health["http_status"] == 503,
          "valid_prediction_503": valid["http_status"] == 503,
          "invalid_input_422": invalid["http_status"] == 422}
print(json.dumps({"scope": "Local private fault rehearsal, not Cloud Run incident",
                  "readiness_attempts": attempts, "health": health,
                  "valid": valid, "invalid": invalid, "checks": checks,
                  "result": "passed" if all(checks.values()) else "failed"}, indent=2))
raise SystemExit(0 if all(checks.values()) else 2)
