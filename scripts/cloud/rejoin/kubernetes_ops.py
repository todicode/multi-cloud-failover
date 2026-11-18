from scripts.cloud.rejoin.host_ops import (
    require_postgres_stopped,
    restore_agent,
    run_host_command,
)
import subprocess
import time
import json


def run_kubectl(namespace, *arguments, timeout=60):
    return run_host_command(
        "k3s", "kubectl", "-n", namespace,
        *arguments,
        timeout=timeout,
    )


def scale_workloads_to_zero(namespace):
    return run_kubectl(
        namespace,
        "scale", "statefulset/postgres", "deployment/issues-app",
        "--replicas=0",
    )


def apply_manifest(namespace, manifest_path):
    return run_kubectl(
        namespace,
        "apply", "-f", str(manifest_path),
    )

def wait_for_api(namespace, timeout=120):
    deadline = time.monotonic() + timeout
    last_error = None

    while time.monotonic() < deadline:
        try:
            run_kubectl(
                namespace,
                "get", "--raw=/readyz", "--request-timeout=5s",
                timeout=10,
            )
            return
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            last_error = error
            time.sleep(2)

    raise RuntimeError("Kubernetes API did not become ready.") from last_error

def read_manifest(namespace, manifest_path):
    output = run_kubectl(
        namespace,
        "create", "--dry-run=client", "--validate=false",
        "-f", str(manifest_path), "-o", "json",
    )
    return json.loads(output)


def restore_node_for_clone(namespace, node_name):
    resources = json.loads(run_kubectl(
        namespace,
        "get", "statefulset/postgres", "deployment/issues-app", "-o", "json",
    ))
    for resource in resources["items"]:
        if resource["spec"].get("replicas", 1) != 0:
            raise RuntimeError("Workload replicas must be 0 before agent restore.")

    require_postgres_stopped()
    run_kubectl(
        namespace,
        "delete", "pod", "-l", "app in (postgres,issues-app)",
        "--force", "--grace-period=0", "--ignore-not-found=true",
    )
    restore_agent()
    wait_for_api(namespace)
    return run_kubectl(
        namespace,
        "wait", "--for=condition=Ready", f"node/{node_name}",
        "--timeout=180s",
        timeout=210,
    )