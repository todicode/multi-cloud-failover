from scripts.cloud.failback.postgres_ops import require_primary, set_app_writes
from scripts.cloud.failover.aws_ops import fence_instance, read_instance_state
from scripts.cloud.failover.postgres_ops import preflight_standby, promote_standby, read_postgres_status
from scripts.cloud.failover.checks import wait_for_writer

def prepare_failover(config, ec2):
    print("failover_step=preflight_standby")
    preflight_standby(config)

    print("failover_step=fence_aws")
    state = fence_instance(ec2, config["aws_instance_id"])

    print(f"failover_step=fence_confirmed aws_ec2_state={state}")
    return state

def run_failover(config, ec2):
    status = read_postgres_status(config)
    if status["in_recovery"] is True:
        prepare_failover(config, ec2)
        print("failover_step=promote_azure")
        promote_standby(config)
    elif read_instance_state(ec2, config["aws_instance_id"]) != "stopped":
        raise RuntimeError("Cannot resume Azure promotion without a stopped AWS instance.")

    status = require_primary(config)
    if status["writes_enabled"] is not True:
        set_app_writes(config, True)
        status = require_primary(config)
    print("failover_step=promotion_confirmed")
    print("failover_step=verify_azure_writer")
    wait_for_writer(
        config["azure_writer_url"],
        config["http_timeout_seconds"],
        config["interval_seconds"],
    )
    print("failover_step=writer_confirmed")
    return status
