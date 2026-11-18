import json
import time

from scripts.cloud.failover.postgres_ops import preflight_standby, run_postgres_sql
from scripts.cloud.rejoin.kubernetes_ops import run_kubectl


def start_standby(config, pvc_name):
    namespace = config["kubernetes_namespace"]
    postgres = json.loads(run_kubectl(
        namespace,
        "get", "statefulset/postgres", "-o", "json",
    ))
    volumes = postgres["spec"]["template"]["spec"]["volumes"]
    data_volume = next(volume for volume in volumes if volume["name"] == "data")
    if data_volume["persistentVolumeClaim"]["claimName"] != pvc_name:
        raise RuntimeError("PostgreSQL must use the completed clone PVC.")

    run_kubectl(namespace, "scale", "statefulset/postgres", "--replicas=1")
    run_kubectl(
        namespace,
        "rollout", "status", "statefulset/postgres", "--timeout=300s",
        timeout=330,
    )


def wait_for_streaming(config, source_host, timeout=120):
    sql = """SELECT COALESCE(
        (SELECT json_build_object(
            'status', status,
            'sender_host', sender_host,
            'sender_port', sender_port
        ) FROM pg_stat_wal_receiver),
        '{}'::json
    );"""
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        status = preflight_standby(config)
        receiver = json.loads(run_postgres_sql(config, sql))
        if (
            receiver.get("status") == "streaming"
            and receiver.get("sender_host") == source_host
            and receiver.get("sender_port") == 5432
        ):
            return {**status, "receiver": receiver}
        time.sleep(2)

    raise RuntimeError(f"Standby did not start streaming from {source_host}.")
