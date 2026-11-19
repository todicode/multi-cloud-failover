import argparse
import json
import subprocess
from uuid import UUID

from scripts.cloud.config import load_config
from scripts.cloud.failback.aws_promotion import inspect_aws, promote_aws
from scripts.cloud.rejoin.clone_ops import CloneJobFailed
from scripts.cloud.rejoin.lock_ops import RejoinBusy
from scripts.cloud.rejoin.rejoin_aws import run_aws_rejoin


def dispatch(request):
    parts = request.split()
    if len(parts) == 1:
        return run_aws_rejoin(UUID(parts[0]).hex)
    if len(parts) == 2 and parts[0] == "status":
        return inspect_aws(load_config(), UUID(parts[1]).hex)
    if len(parts) == 3 and parts[0] == "promote":
        return promote_aws(load_config(), UUID(parts[1]).hex, parts[2])
    raise ValueError("Expected an operation UUID, status UUID, or promote UUID LSN.")


def main():
    parser = argparse.ArgumentParser(description="Run a scoped AWS recovery operation.")
    parser.add_argument("request")
    args = parser.parse_args()

    try:
        state = dispatch(args.request)
    except RejoinBusy as error:
        print(json.dumps({"status": "busy", "error": str(error)}))
        return 75
    except CloneJobFailed as error:
        print(json.dumps({"status": "clone_failed", "error": str(error)}))
        return 3
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        detail = error.stderr if isinstance(error, subprocess.CalledProcessError) else None
        print(json.dumps({"status": "error", "error": (detail or str(error)).strip()}))
        return 1

    print(json.dumps({"status": "ok", "state": state}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
