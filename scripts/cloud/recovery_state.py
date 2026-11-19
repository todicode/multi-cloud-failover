import json
from pathlib import Path
from uuid import UUID, uuid4

from scripts.cloud.rejoin.state_ops import save_state

CONTROLLER_STATE = Path.home() / ".local/state/mcf-controller/state.json"
PHASES = (
    "failover_pending", "azure_ready", "rejoin_aws", "wait_failback", "drain_azure",
    "fence_azure", "promote_aws", "aws_ready", "rejoin_azure", "complete",
)


def read_cycle(path=CONTROLLER_STATE):
    try:
        details = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    if not isinstance(details, dict) or details.get("phase") not in PHASES:
        raise ValueError("Controller state has an unknown phase.")
    if UUID(details["operation_id"]).hex != details["operation_id"]:
        raise ValueError("Controller state has an invalid operation ID.")
    return details


def save_phase(state, phase, **details):
    next_state = {**state, **details, "phase": phase}
    save_state(CONTROLLER_STATE, next_state)
    print(f"recovery_phase={phase} operation_id={next_state['operation_id']}")
    return next_state


def new_cycle(phase):
    return save_phase({"operation_id": uuid4().hex}, phase)
