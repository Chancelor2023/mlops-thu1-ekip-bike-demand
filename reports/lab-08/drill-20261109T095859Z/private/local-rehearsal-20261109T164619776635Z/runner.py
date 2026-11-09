"""Private, local-only Lab 8 rehearsal. Does not invoke gcloud or modify Cloud Run."""

import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

PLAN_SHA = "d16e9a43d2ac64d77b0e07fa49c545f25f8d59e04ece15fe5e92575bb0850066"
PROBE = r"""
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
"""


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if len(sys.argv) != 2 or not sys.argv[1].strip():
        raise SystemExit("STOP: provide the absolute LAB8_DRILL directory")
    root = Path(sys.argv[1])
    if (
        not root.is_absolute()
        or not (root / "preparation/reference-preflight.json").is_file()
    ):
        raise SystemExit("STOP: expected drill preparation directory is missing")
    root = root.resolve()
    repo = Path.cwd().resolve()
    if root.is_relative_to(repo):
        raise SystemExit(
            "STOP: private rehearsal evidence must remain outside the repository"
        )
    plan_path = root / "private/fault-plan.json"
    if sha(plan_path) != PLAN_SHA:
        raise SystemExit(
            "STOP: plan hash differs; do not replace or regenerate the note"
        )
    plan = json.loads(plan_path.read_text())
    expected = json.loads((repo / "reports/lab-08/rollback-target.json").read_text())
    if plan["image"] != expected["image"] or plan["injection_performed"]:
        raise SystemExit("STOP: unexpected plan image or injection state")
    if plan["fault"]["variable"] != "MODEL_DIR":
        raise SystemExit("STOP: unexpected fault type")
    bundle = root / "preparation/reference-bundle"
    for name, digest in expected["bundle_checksums"].items():
        if sha(bundle / name) != digest:
            raise SystemExit("STOP: reference bundle checksum mismatch")
    inputs = root / "preparation/frozen-inputs"
    provenance = json.loads((inputs / "provenance.json").read_text())
    if sha(inputs / "payloads.json") != provenance["payloads_sha256"]:
        raise SystemExit("STOP: frozen payload checksum mismatch")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    stage = root / "private" / ("local-rehearsal-" + stamp)
    stage.mkdir(mode=0o700)
    (stage / "probe.py").write_text(PROBE)
    (stage / "runner.py").write_bytes(Path(__file__).read_bytes())
    name = "lab8-local-fault-" + uuid4().hex[:10]
    command = [
        "docker",
        "run",
        "--detach",
        "--name",
        name,
        "--cpus=1",
        "--memory=512m",
        "--network=none",
        "--env",
        "MODEL_DIR=" + plan["fault"]["planned_value"],
        "--env",
        "PYTHONPATH=/app/src",
        "--entrypoint",
        "/app/.venv/bin/python",
        "--mount",
        f"type=bind,src={bundle},dst=/app/artifacts,readonly",
        "--mount",
        f"type=bind,src={inputs},dst=/lab8-inputs,readonly",
        plan["image"],
        "-m",
        "uvicorn",
        "bike_demand.api:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
    ]
    (stage / "docker-run-command.json").write_text(json.dumps(command, indent=2) + "\n")
    outcome = {
        "scope": "Private local rehearsal only",
        "runner_version": 2,
        "launch_mode": "Installed Python/uvicorn directly; no uv bootstrap",
        "default_image_command_tested": False,
        "plan_sha256": PLAN_SHA,
        "cloud_run_modified": False,
        "retraining_performed": False,
        "container": name,
        "result": "failed",
    }
    created = False
    try:
        run = subprocess.run(command, capture_output=True, text=True)
        (stage / "docker-run.stdout.log").write_text(run.stdout)
        (stage / "docker-run.stderr.log").write_text(run.stderr)
        if run.returncode:
            raise RuntimeError("Docker start failed; inspect the private stderr log")
        created = True
        deadline = time.monotonic() + 120
        with (stage / "server-startup.jsonl").open("x") as startup:
            while True:
                inspected = subprocess.run(
                    ["docker", "inspect", name],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                state = json.loads(inspected.stdout)[0]["State"]
                logs = subprocess.run(
                    ["docker", "logs", name],
                    capture_output=True,
                    text=True,
                )
                complete = "Application startup complete" in logs.stdout + logs.stderr
                startup.write(
                    json.dumps(
                        {
                            "observed_at_utc": datetime.now(timezone.utc).isoformat(),
                            "running": state["Running"],
                            "exit_code": state.get("ExitCode"),
                            "application_startup_complete": complete,
                        }
                    )
                    + "\n"
                )
                startup.flush()
                if not state["Running"]:
                    raise RuntimeError(
                        f"API exited before probing (exit {state.get('ExitCode')}); "
                        "inspect the private container logs"
                    )
                if complete:
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError("API startup not observed within 120 seconds")
                time.sleep(2)
        probe = subprocess.run(
            ["docker", "exec", "-i", name, "/app/.venv/bin/python", "-"],
            input=PROBE,
            capture_output=True,
            text=True,
            timeout=150,
        )
        (stage / "probe.stdout.json").write_text(probe.stdout)
        (stage / "probe.stderr.log").write_text(probe.stderr)
        (stage / "probe-exit.txt").write_text(str(probe.returncode) + "\n")
        outcome["probe_exit"] = probe.returncode
        if not probe.stdout.strip():
            raise RuntimeError(
                f"HTTP probe produced no JSON (exit {probe.returncode}); "
                "inspect probe stderr and container logs"
            )
        result = json.loads(probe.stdout)
        outcome["checks"] = result["checks"]
        inspected = subprocess.run(
            ["docker", "inspect", name], capture_output=True, text=True, check=True
        )
        config = json.loads(inspected.stdout)[0]
        (stage / "container-running.json").write_text(inspected.stdout)
        env = dict(v.split("=", 1) for v in config["Config"]["Env"])
        outcome["configuration_matches"] = (
            env.get("MODEL_DIR") == plan["fault"]["planned_value"]
            and env.get("CODE_REVISION") == expected["code_revision"]
            and env.get("PYTHONPATH") == "/app/src"
            and config["Config"].get("Entrypoint") == ["/app/.venv/bin/python"]
            and config["Config"].get("Cmd")
            == [
                "-m",
                "uvicorn",
                "bike_demand.api:app",
                "--host",
                "0.0.0.0",
                "--port",
                "8000",
            ]
            and config["HostConfig"]["NetworkMode"] == "none"
            and config["HostConfig"]["Memory"] == 536870912
            and config["HostConfig"]["NanoCpus"] == 1000000000
            and all(not v["RW"] for v in config["Mounts"])
        )
        for filename, digest in expected["bundle_checksums"].items():
            if sha(bundle / filename) != digest:
                raise RuntimeError(
                    "STOP: reference file changed during local rehearsal"
                )
        if (
            probe.returncode == 0
            and result["result"] == "passed"
            and all(result["checks"].values())
            and outcome["configuration_matches"]
        ):
            outcome["result"] = "passed"
    except (
        OSError,
        ValueError,
        KeyError,
        RuntimeError,
        subprocess.SubprocessError,
        KeyboardInterrupt,
    ) as error:
        outcome["error"] = f"{type(error).__name__}: {error}"
    finally:
        if not created:
            existence = subprocess.run(
                ["docker", "inspect", name], capture_output=True, text=True
            )
            created = existence.returncode == 0
        if created:
            stop = subprocess.run(
                ["docker", "stop", name], capture_output=True, text=True
            )
            (stage / "docker-stop.log").write_text(stop.stdout + stop.stderr)
            logs = subprocess.run(
                ["docker", "logs", name], capture_output=True, text=True
            )
            (stage / "container.stdout.log").write_text(logs.stdout)
            (stage / "container.stderr.log").write_text(logs.stderr)
            (stage / "container.log").write_text(logs.stdout + logs.stderr)
            inspected = subprocess.run(
                ["docker", "inspect", name], capture_output=True, text=True
            )
            (stage / "container-stopped.json").write_text(inspected.stdout)
            if stop.returncode or inspected.returncode:
                outcome["result"] = "failed"
                outcome["cleanup_error"] = "Could not verify the local container stop"
            else:
                state = json.loads(inspected.stdout)[0]["State"]
                outcome["container_running_after_cleanup"] = state["Running"]
                outcome["oom_killed"] = state["OOMKilled"]
                if state["Running"] or state["OOMKilled"]:
                    outcome["result"] = "failed"
        (stage / "result.json").write_text(json.dumps(outcome, indent=2) + "\n")
    print("Private evidence directory:", stage)
    print(json.dumps(outcome, indent=2))
    return 0 if outcome["result"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
