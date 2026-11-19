from pathlib import Path
from uuid import UUID

from scripts.cloud.rejoin.app_ops import restore_application
from scripts.cloud.rejoin.clone_ops import run_clone
from scripts.cloud.rejoin.host_ops import (
    require_postgres_stopped,
    run_host_command,
    start_agentless_control_plane,
)
from scripts.cloud.rejoin.kubernetes_ops import (
    apply_manifest,
    restore_node_for_clone,
    scale_workloads_to_zero,
    wait_for_api,
)
from scripts.cloud.rejoin.lock_ops import rejoin_lock
from scripts.cloud.rejoin.manifest_ops import render_manifests
from scripts.cloud.rejoin.postgres_ops import (
    confirm_postgres_fenced,
    start_standby,
    wait_for_streaming,
)
from scripts.cloud.rejoin.preflight import require_source_writer
from scripts.cloud.rejoin.state_ops import load_state, rejoin_directory, save_state

PROJECT_ROOT = Path(__file__).resolve().parents[3]
K3S_START_MARKER = Path("/run/issues-k3s-start-approved")
WAL_HOSTS = {"aws": "10.200.29.1", "azure": "10.200.29.2"}
AWS_NODE = "mcf-aws-primary"


def prepare_target(config, cloud, operation_id, directory):
    namespace = config["kubernetes_namespace"]
    run_host_command("systemctl", "start", "wg-quick@wg0")
    addresses = run_host_command("ip", "-4", "-o", "addr", "show", "dev", "wg0")
    if f"{WAL_HOSTS[cloud]}/32" not in addresses.split():
        raise RuntimeError(f"Expected the {cloud} WireGuard address on this host.")

    if cloud == "aws":
        require_postgres_stopped()
        start_agentless_control_plane(PROJECT_ROOT)
    else:
        confirm_postgres_fenced(config)

    wait_for_api(namespace)
    scale_workloads_to_zero(namespace)
    paths, pvc_name = render_manifests(namespace, PROJECT_ROOT, directory, operation_id, cloud)
    apply_manifest(namespace, paths["pvc"])
    apply_manifest(namespace, paths["postgres"])
    if cloud == "aws":
        restore_node_for_clone(namespace, AWS_NODE)
    return pvc_name


def run_rejoin(config, cloud, operation_id):
    operation_id = UUID(operation_id).hex
    directory = rejoin_directory(operation_id)
    state_path = directory / "state.json"
    namespace = config["kubernetes_namespace"]
    source = "azure" if cloud == "aws" else "aws"

    with rejoin_lock():
        state = load_state(state_path, operation_id)
        if state["phase"] == "complete":
            return state
        if state["phase"] not in ("pending", "prepared", "clone_complete", "standby_streaming"):
            raise ValueError(f"Unknown rejoin phase: {state['phase']}")

        require_source_writer(config[f"{source}_writer_url"], config["http_timeout_seconds"])
        if state["phase"] == "pending" or (cloud == "aws" and not K3S_START_MARKER.is_file()):
            save_state(state_path, state)
            pvc_name = prepare_target(config, cloud, operation_id, directory)
            if state.get("pvc_name", pvc_name) != pvc_name:
                raise RuntimeError("Rejoin PVC changed while resuming.")
            if state["phase"] == "pending":
                state.update(phase="prepared", pvc_name=pvc_name)
                save_state(state_path, state)

        pvc_name = state["pvc_name"]
        if state["phase"] == "prepared":
            job_name = run_clone(namespace, directory / "clone.json", pvc_name)
            state.update(phase="clone_complete", job_name=job_name)
            save_state(state_path, state)

        start_standby(config, pvc_name)
        replication = wait_for_streaming(config, WAL_HOSTS[source])
        state.update(phase="standby_streaming", replication=replication)
        save_state(state_path, state)

        application = restore_application(namespace, config[f"{cloud}_writer_url"])
        state.update(phase="complete", application=application)
        save_state(state_path, state)
        return state
