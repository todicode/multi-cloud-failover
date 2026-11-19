import argparse
import os
from pathlib import Path
import subprocess
import sys
import time

import httpx
from botocore.exceptions import BotoCoreError, ClientError

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.cloud.config import CONFIG_PATH, load_config
from scripts.cloud.failback.postgres_ops import require_primary
from scripts.cloud.failover.aws_ops import create_aws_clients, read_instance_state
from scripts.cloud.failover.observation import failover_candidate
from scripts.cloud.recovery import advance
from scripts.cloud.recovery_state import new_cycle, read_cycle
from scripts.cloud.rejoin.clone_ops import CloneJobFailed
from scripts.cloud.rejoin.lock_ops import RejoinBusy, operation_lock
from scripts.cloud.rejoin.preflight import require_source_writer


def adopt_azure_primary(config, ec2):
    if not config["enable_auto_recovery"]:
        raise ValueError("Adoption requires enable_auto_recovery=true.")
    state = read_cycle()
    if state is not None and state["phase"] != "complete":
        raise ValueError("An unfinished cycle already exists. Start the service to resume it.")
    if read_instance_state(ec2, config["aws_instance_id"]) != "stopped":
        raise RuntimeError("Adoption requires EC2 to be stopped.")
    if require_primary(config)["writes_enabled"] is not True:
        raise RuntimeError("Adoption requires Azure to accept application writes.")
    require_source_writer(config["azure_writer_url"], config["http_timeout_seconds"])
    new_cycle("azure_ready")


def run_controller(config, ec2, route53):
    failures = 0
    print(f"auto_failover={config['enable_auto_failover']} auto_recovery={config['enable_auto_recovery']}")
    while True:
        state = read_cycle()
        phase = state["phase"] if state else None
        if phase in (None, "complete"):
            if failover_candidate(config, ec2, route53):
                failures += 1
            else:
                failures = 0
            print(f"consecutive_failures={failures}")
            if config["enable_auto_failover"] and failures >= config["failure_threshold"]:
                new_cycle("failover_pending")
                failures = 0
                continue
        elif config["enable_auto_failover"] and (
            phase == "failover_pending" or config["enable_auto_recovery"]
        ):
            try:
                next_state = advance(config, ec2, state)
            except CloneJobFailed:
                raise
            except (BotoCoreError, ClientError, httpx.HTTPError, OSError,
                    RuntimeError, subprocess.SubprocessError, ValueError) as error:
                detail = error.stderr if isinstance(error, subprocess.CalledProcessError) else None
                print(f"recovery_retry phase={phase} error={str(detail or error).strip()}", file=sys.stderr)
            else:
                if next_state["phase"] != phase:
                    continue
        else:
            print(f"recovery_paused phase={phase}")
        time.sleep(config["interval_seconds"])


def main():
    parser = argparse.ArgumentParser(description="Azure-hosted multi-cloud recovery controller.")
    parser.add_argument("--config", type=Path, default=os.environ.get("MCF_WATCHER_CONFIG", CONFIG_PATH))
    parser.add_argument("--adopt-azure-primary", action="store_true")
    args = parser.parse_args()

    try:
        config = load_config(args.config)
        with operation_lock("mcf-controller", "controller.lock"):
            sts, ec2, route53 = create_aws_clients(config)
            print(f"aws_identity={sts.get_caller_identity()['Arn']}")
            if args.adopt_azure_primary:
                adopt_azure_primary(config, ec2)
            else:
                run_controller(config, ec2, route53)
    except (CloneJobFailed, RejoinBusy, ValueError) as error:
        print(f"controller_blocked={error}", file=sys.stderr)
        return 78
    except (BotoCoreError, ClientError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        detail = error.stderr if isinstance(error, subprocess.CalledProcessError) else None
        print(f"controller_error={str(detail or error).strip()}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
