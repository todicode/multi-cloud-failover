import subprocess
import time

from scripts.cloud.failback.postgres_ops import replayed_write_barrier, require_primary, set_app_writes
from scripts.cloud.rejoin.ssh_client import read_aws_status
from scripts.cloud.rejoin.workflow import WAL_HOSTS


def require_aws_streaming(operation_id, timeout=40):
    status = read_aws_status(operation_id, timeout)
    if (
        status["in_recovery"] is not True
        or status["read_only"] != "on"
        or status["sender_host"] != WAL_HOSTS["azure"]
        or status["sender_port"] != 5432
    ):
        raise RuntimeError("AWS standby is not streaming from Azure.")
    return status


def pause_azure_and_wait(config, operation_id, timeout=60):
    # Only this phase can roll back. The controller persists fencing intent
    # before scaling Azure down or asking the remote worker to promote AWS.
    try:
        require_aws_streaming(operation_id)
        target_lsn = set_app_writes(config, False)
        print(f"failback_step=azure_writes_paused target_lsn={target_lsn}")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = require_aws_streaming(operation_id, timeout=25)
            if replayed_write_barrier(status, target_lsn):
                print(f"failback_step=aws_replay_confirmed replay_lsn={status['replay_lsn']} target_lsn={target_lsn}")
                return target_lsn
            time.sleep(2)
        raise TimeoutError("AWS did not replay the checkpoint before the write-pause deadline.")
    except (RuntimeError, ValueError, OSError, subprocess.SubprocessError):
        if require_primary(config)["writes_enabled"] is False:
            set_app_writes(config, True)
            print("failback_step=azure_writes_reopened")
        raise
