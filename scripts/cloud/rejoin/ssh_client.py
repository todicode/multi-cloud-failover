import json
import subprocess
from uuid import UUID

from scripts.cloud.failback.postgres_ops import lsn_value


class RejoinTransportError(RuntimeError):
    """SSH did not provide a confirmed worker result."""


def call_aws_rejoin(operation_id, timeout=2400):
    operation_id = UUID(operation_id).hex
    result = call_worker(operation_id, operation_id, timeout)
    if result["status"] == "ok" and result["state"].get("phase") != "complete":
        raise RuntimeError("AWS worker did not complete the requested rejoin operation.")
    return result


def read_aws_status(operation_id, timeout=75):
    operation_id = UUID(operation_id).hex
    return require_ok(call_worker(f"status {operation_id}", operation_id, timeout))


def request_aws_promotion(operation_id, target_lsn, timeout=150):
    operation_id = UUID(operation_id).hex
    lsn_value(target_lsn)
    return require_ok(call_worker(f"promote {operation_id} {target_lsn}", operation_id, timeout))


def require_ok(result):
    if result["status"] != "ok":
        raise RuntimeError(f"AWS worker {result['status']}: {result.get('error')}")
    return result["state"]


def call_worker(request, operation_id, timeout):
    command = [
        "ssh", "-T",
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=yes",
        "-o", "ConnectTimeout=10",
        "-o", "ServerAliveInterval=15",
        "-o", "ServerAliveCountMax=3",
        "mcf-aws-rejoin", request,
    ]
    try:
        process = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise RejoinTransportError("SSH timed out while waiting for the AWS worker.") from error

    if process.returncode == 255:
        raise RejoinTransportError(f"SSH failed: {process.stderr.strip()}")

    try:
        result = json.loads(process.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("AWS worker did not return valid JSON.") from error

    expected_status = {0: "ok", 75: "busy", 3: "clone_failed", 1: "error"}.get(process.returncode)
    if expected_status is None or not isinstance(result, dict) or result.get("status") != expected_status:
        raise RuntimeError(f"Unexpected AWS worker response for exit code {process.returncode}.")
    if expected_status == "ok":
        state = result.get("state")
        if not isinstance(state, dict) or state.get("operation_id") != operation_id:
            raise RuntimeError("AWS worker response did not match the requested operation.")
    return result
