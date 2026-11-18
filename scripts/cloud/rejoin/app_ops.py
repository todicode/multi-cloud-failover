import time

from scripts.cloud.failover.checks import classify_probe, probe_writer
from scripts.cloud.rejoin.kubernetes_ops import run_kubectl


def restore_application(namespace, writer_url, timeout=120):
    run_kubectl(namespace, "scale", "deployment/issues-app", "--replicas=1")
    run_kubectl(
        namespace,
        "rollout", "status", "deployment/issues-app", "--timeout=180s",
        timeout=210,
    )
    deadline = time.monotonic() + timeout
    result = None

    while time.monotonic() < deadline:
        result = probe_writer(writer_url, timeout=5)
        if (
            classify_probe(result) == "standby"
            and result["body"].get("replication_connected") is True
        ):
            return result["body"]
        time.sleep(2)

    raise RuntimeError(f"Application standby health was not confirmed: {result}")