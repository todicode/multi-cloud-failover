import json
import time
from pathlib import Path

from scripts.cloud.rejoin.kubernetes_ops import apply_manifest, run_kubectl


class CloneJobFailed(RuntimeError):
    """Kubernetes reported a terminal failure for the clone Job."""


def run_clone(namespace, job_path, pvc_name, timeout=630):
    job = json.loads(Path(job_path).read_text(encoding="utf-8"))
    job_name = job["metadata"]["name"]
    volumes = job["spec"]["template"]["spec"]["volumes"]
    data_volume = next(volume for volume in volumes if volume["name"] == "data")
    if data_volume["persistentVolumeClaim"]["claimName"] != pvc_name:
        raise ValueError("Clone Job must reference the rejoin PVC.")

    apply_manifest(namespace, job_path)
    deadline = time.monotonic() + timeout
    while True:
        current = json.loads(run_kubectl(
            namespace,
            "get", f"job/{job_name}", "-o", "json", "--request-timeout=10s",
            timeout=15,
        ))
        for condition in current.get("status", {}).get("conditions", []):
            if condition.get("status") != "True":
                continue
            if condition.get("type") == "Complete":
                return job_name
            if condition.get("type") == "Failed":
                reason = condition.get("reason") or "unknown reason"
                raise CloneJobFailed(f"Clone Job {job_name} failed: {reason}")

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"Timed out waiting for clone Job {job_name}.")
        time.sleep(min(2, remaining))
