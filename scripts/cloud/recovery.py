import time

from scripts.cloud.app_checks import origin_url, require_probe_records, write_shared_probe
from scripts.cloud.failback.postgres_ops import replayed_write_barrier
from scripts.cloud.failback.switchover import pause_azure_and_wait, require_aws_streaming
from scripts.cloud.failover.aws_ops import start_instance
from scripts.cloud.failover.checks import classify_probe, probe_writer, wait_for_writer
from scripts.cloud.failover.failover_ops import run_failover
from scripts.cloud.recovery_state import save_phase
from scripts.cloud.rejoin.clone_ops import CloneJobFailed
from scripts.cloud.rejoin.postgres_ops import confirm_postgres_fenced, fence_postgres, mounted_claim, wait_for_streaming
from scripts.cloud.rejoin.preflight import require_source_writer
from scripts.cloud.rejoin.ssh_client import call_aws_rejoin, read_aws_status, request_aws_promotion, require_ok
from scripts.cloud.rejoin.workflow import WAL_HOSTS, run_rejoin


def advance(config, ec2, state):
    phase = state["phase"]
    operation_id = state["operation_id"]
    run_id = f"stage7-{operation_id}"
    timeout = config["http_timeout_seconds"]
    if phase == "failover_pending":
        run_failover(config, ec2)
        return save_phase(state, "azure_ready")

    if phase == "azure_ready":
        require_source_writer(config["azure_writer_url"], timeout)
        write_shared_probe(config, "azure", run_id, seq=1)
        print(f"shared_writer=azure run_id={run_id}")
        return save_phase(state, "rejoin_aws", azure_writer_verified_at=time.time())

    if phase == "rejoin_aws":
        require_source_writer(config["azure_writer_url"], timeout)
        start_instance(ec2, config["aws_instance_id"])
        result = call_aws_rejoin(operation_id)
        if result["status"] == "clone_failed":
            raise CloneJobFailed(result["error"])
        worker = require_ok(result)
        print(f"aws_rejoin_complete pvc={worker['pvc_name']}")
        return save_phase(state, "wait_failback", aws_pvc=worker["pvc_name"])

    if phase == "wait_failback":
        remaining = state["azure_writer_verified_at"] + config["azure_writer_min_seconds"] - time.time()
        if remaining > 0:
            print(f"failback_wait_seconds={round(remaining)} operation_id={operation_id}")
            return state
        require_source_writer(config["azure_writer_url"], timeout)
        require_aws_streaming(operation_id)
        require_probe_records(origin_url(config["aws_writer_url"]), timeout, run_id, {1: "azure"})
        return save_phase(state, "drain_azure")

    if phase == "drain_azure":
        target_lsn = pause_azure_and_wait(config, operation_id)
        return save_phase(state, "fence_azure", target_lsn=target_lsn)

    if phase == "fence_azure":
        status = read_aws_status(operation_id)
        if not replayed_write_barrier(status, state["target_lsn"]):
            raise RuntimeError("AWS no longer confirms replay of the Azure write barrier.")
        fence_postgres(config)
        print("failback_step=azure_postgres_fenced")
        return save_phase(state, "promote_aws")

    if phase == "promote_aws":
        confirm_postgres_fenced(config)
        status = request_aws_promotion(operation_id, state["target_lsn"])
        if (
            status["in_recovery"] is not False
            or status["read_only"] != "off"
            or status["writes_enabled"] is not True
        ):
            raise RuntimeError("AWS worker did not confirm an open primary.")
        wait_for_writer(config["aws_writer_url"], timeout, config["interval_seconds"])
        return save_phase(state, "aws_ready")

    if phase == "aws_ready":
        write_shared_probe(config, "aws", run_id, seq=2)
        print(f"shared_writer=aws run_id={run_id}")
        return save_phase(state, "rejoin_azure")

    if phase == "rejoin_azure":
        standby = run_rejoin(config, "azure", operation_id)
        wait_for_writer(config["aws_writer_url"], timeout, config["interval_seconds"])
        verify_restored(config, run_id, standby)
        print(f"azure_rejoin_complete pvc={standby['pvc_name']}")
        return save_phase(state, "complete", azure_pvc=standby["pvc_name"], completed_at=time.time())

    raise ValueError(f"Unexpected active recovery phase: {phase}")


def verify_restored(config, run_id, standby):
    if mounted_claim(config) != standby["pvc_name"]:
        raise RuntimeError("Azure does not mount this operation's standby PVC.")
    wait_for_streaming(config, WAL_HOSTS["aws"])
    timeout = config["http_timeout_seconds"]
    azure = probe_writer(config["azure_writer_url"], timeout)
    if classify_probe(azure) != "standby" or azure["body"]["replication_connected"] is not True:
        raise RuntimeError("Azure HTTPS did not confirm the restored standby.")
    expected = {1: "azure", 2: "aws"}
    require_probe_records(origin_url(config["azure_writer_url"]), timeout, run_id, expected)
    require_source_writer(config["aws_writer_url"], timeout)
    require_probe_records(config["shared_app_url"].rstrip("/"), timeout, run_id, expected)
