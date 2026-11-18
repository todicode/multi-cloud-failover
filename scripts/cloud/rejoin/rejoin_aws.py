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
    run_kubectl,
    scale_workloads_to_zero,
    wait_for_api,
)
from scripts.cloud.rejoin.lock_ops import rejoin_lock
from scripts.cloud.rejoin.manifest_ops import render_manifests
from scripts.cloud.rejoin.postgres_ops import start_standby, wait_for_streaming
from scripts.cloud.rejoin.preflight import require_source_writer
from scripts.cloud.rejoin.state_ops import load_state, save_state

PROJECT_ROOT = Path(__file__).resolve().parents[3]
NAMESPACE = "issues"
AWS_NODE = "mcf-aws-primary"
AZURE_WRITER_URL = "https://azure.mcf.todicode.tech/health/database"
AWS_WRITER_URL = "https://aws.mcf.todicode.tech/health/database"
AZURE_WAL_HOST = "10.200.29.2"
K3S_START_MARKER = Path("/run/issues-k3s-start-approved")
POSTGRES_CONFIG = {"kubernetes_namespace": NAMESPACE, "postgres_pod": "postgres-0"}


def prepare_aws(operation_id, operation_directory):
    run_host_command("systemctl", "start", "wg-quick@wg0")
    addresses = run_host_command("ip", "-4", "-o", "addr", "show", "dev", "wg0")
    if "10.200.29.1/32" not in addresses.split():
        raise RuntimeError("Expected the AWS WireGuard address on this host.")

    require_postgres_stopped()
    start_agentless_control_plane(PROJECT_ROOT)
    wait_for_api(NAMESPACE)
    scale_workloads_to_zero(NAMESPACE)
    paths, pvc_name = render_manifests(NAMESPACE, PROJECT_ROOT, operation_directory, operation_id)
    apply_manifest(NAMESPACE, paths["pvc"])
    apply_manifest(NAMESPACE, paths["postgres"])
    restore_node_for_clone(NAMESPACE, AWS_NODE)
    return pvc_name


def run_aws_rejoin(operation_id):
    operation_id = UUID(operation_id).hex
    operation_directory = Path.home() / ".local" / "state" / "mcf-rejoin" / operation_id
    state_path = operation_directory / "state.json"

    with rejoin_lock():
        state = load_state(state_path, operation_id)
        phase = state["phase"]
        if phase == "complete":
            return state
        if phase not in ("pending", "prepared", "clone_complete", "standby_streaming"):
            raise ValueError(f"Unknown rejoin phase: {phase}")

        require_source_writer(AZURE_WRITER_URL)
        if phase == "pending":
            save_state(state_path, state)
            pvc_name = prepare_aws(operation_id, operation_directory)
            state.update(phase="prepared", pvc_name=pvc_name)
            save_state(state_path, state)
        elif not K3S_START_MARKER.is_file():
            pvc_name = prepare_aws(operation_id, operation_directory)
            if pvc_name != state["pvc_name"]:
                raise RuntimeError("Rejoin PVC changed while resuming the operation.")
        else:
            wait_for_api(NAMESPACE)
            run_kubectl(
                NAMESPACE, "wait", "--for=condition=Ready", f"node/{AWS_NODE}",
                "--timeout=180s", timeout=210,
            )

        pvc_name = state["pvc_name"]
        if state["phase"] == "prepared":
            run_kubectl(NAMESPACE, "get", f"pvc/{pvc_name}", "-o", "name")
            job_name = run_clone(NAMESPACE, operation_directory / "clone.json", pvc_name)
            state.update(phase="clone_complete", job_name=job_name)
            save_state(state_path, state)

        start_standby(POSTGRES_CONFIG, pvc_name)
        replication = wait_for_streaming(POSTGRES_CONFIG, AZURE_WAL_HOST)
        state.update(phase="standby_streaming", replication=replication)
        save_state(state_path, state)

        application = restore_application(NAMESPACE, AWS_WRITER_URL)
        state.update(phase="complete", application=application)
        save_state(state_path, state)
        return state
