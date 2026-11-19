import json
import time

from scripts.cloud.failover.postgres_ops import preflight_standby, run_postgres_sql
from scripts.cloud.rejoin.kubernetes_ops import run_kubectl
from scripts.cloud.rejoin.host_ops import require_postgres_stopped, run_host_command


def mounted_claim(config):
    namespace = config["kubernetes_namespace"]
    pod = json.loads(run_kubectl(
        namespace,
        "get", f"pod/{config['postgres_pod']}", "-o", "json",
    ))
    volumes = pod["spec"]["volumes"]
    data_volume = next(volume for volume in volumes if volume["name"] == "data")
    if pod["metadata"].get("deletionTimestamp"):
        raise RuntimeError("PostgreSQL Pod is terminating.")
    return data_volume["persistentVolumeClaim"]["claimName"]


def start_standby(config, pvc_name):
    namespace = config["kubernetes_namespace"]
    postgres = json.loads(run_kubectl(namespace, "get", "statefulset/postgres", "-o", "json"))
    volumes = postgres["spec"]["template"]["spec"]["volumes"]
    data_volume = next(volume for volume in volumes if volume["name"] == "data")
    if data_volume["persistentVolumeClaim"]["claimName"] != pvc_name:
        raise RuntimeError("PostgreSQL StatefulSet must use the completed clone PVC.")
    run_kubectl(namespace, "scale", "statefulset/postgres", "--replicas=1")
    run_kubectl(
        namespace,
        "rollout", "status", "statefulset/postgres", "--timeout=300s",
        timeout=330,
    )
    if mounted_claim(config) != pvc_name:
        raise RuntimeError("PostgreSQL Pod did not mount the completed clone PVC.")


def wait_for_streaming(config, source_host, timeout=120):
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        status = preflight_standby(config)
        if status["sender_host"] == source_host and status["sender_port"] == 5432:
            return status
        time.sleep(2)

    raise RuntimeError(f"Standby did not start streaming from {source_host}.")


def confirm_postgres_fenced(config):
    namespace = config["kubernetes_namespace"]
    replicas = run_kubectl(
        namespace, "get", "statefulset/postgres", "-o", "jsonpath={.spec.replicas}",
    )
    if replicas != "0" or run_kubectl(
        namespace, "get", "pod", config["postgres_pod"], "--ignore-not-found", "-o", "name",
    ):
        raise RuntimeError("PostgreSQL must have zero replicas and no Pod.")
    require_postgres_stopped()
    if run_host_command("ss", "-H", "-ltn", "sport = :5432", timeout=10):
        raise RuntimeError("A local TCP listener still owns port 5432.")


def fence_postgres(config, timeout=120):
    namespace = config["kubernetes_namespace"]
    run_kubectl(namespace, "scale", "statefulset/postgres", "--replicas=0")
    deadline = time.monotonic() + timeout
    while run_kubectl(
        namespace, "get", "pod", config["postgres_pod"], "--ignore-not-found", "-o", "name",
    ):
        if time.monotonic() >= deadline:
            raise TimeoutError("PostgreSQL Pod did not stop.")
        time.sleep(2)
    confirm_postgres_fenced(config)
