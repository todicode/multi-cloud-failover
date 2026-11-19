from uuid import UUID

from scripts.cloud.failback.postgres_ops import lsn_value, replayed_write_barrier, set_app_writes
from scripts.cloud.failover.postgres_ops import promote_standby, read_postgres_status
from scripts.cloud.rejoin.lock_ops import rejoin_lock
from scripts.cloud.rejoin.postgres_ops import mounted_claim
from scripts.cloud.rejoin.state_ops import load_state, rejoin_directory, save_state


def completed_standby(config, operation_id):
    state_path = rejoin_directory(operation_id) / "state.json"
    state = load_state(state_path, UUID(operation_id).hex)
    if state["phase"] != "complete" or mounted_claim(config) != state["pvc_name"]:
        raise RuntimeError("AWS is not using the completed rejoin PVC for this operation.")
    return state_path, state


def inspect_aws(config, operation_id):
    with rejoin_lock():
        _, state = completed_standby(config, operation_id)
        return {"operation_id": state["operation_id"], **read_postgres_status(config)}


def promote_aws(config, operation_id, target_lsn):
    target = lsn_value(target_lsn)
    with rejoin_lock():
        state_path, state = completed_standby(config, operation_id)
        status = read_postgres_status(config)
        requested = state.get("promotion_target_lsn")
        if requested is not None and lsn_value(requested) != target:
            raise RuntimeError("An AWS promotion was already requested at another LSN.")

        if status["in_recovery"] is True:
            if not replayed_write_barrier(status, target_lsn):
                raise RuntimeError("AWS did not replay the paused Azure writer checkpoint.")
            state["promotion_target_lsn"] = target_lsn
            save_state(state_path, state)
            status = promote_standby(config)
        elif requested is None:
            raise RuntimeError("AWS is already primary without this operation's promotion intent.")

        if status["in_recovery"] is not False or status["read_only"] != "off":
            raise RuntimeError("AWS PostgreSQL promotion did not reach primary.")
        if status["writes_enabled"] is not True:
            set_app_writes(config, True)

        return {"operation_id": state["operation_id"], **read_postgres_status(config)}
