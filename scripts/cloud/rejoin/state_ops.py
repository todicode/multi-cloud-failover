import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile


def load_state(state_path, operation_id):
    state_path = Path(state_path)
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"operation_id": operation_id, "phase": "pending"}

    if not isinstance(state, dict) or state.get("operation_id") != operation_id:
        raise ValueError("Rejoin state does not match the operation ID.")
    if not isinstance(state.get("phase"), str):
        raise ValueError("Rejoin state must include a phase.")
    return state


def save_state(state_path, state):
    state_path = Path(state_path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = NamedTemporaryFile(
        mode="w", encoding="utf-8",
        dir=state_path.parent, prefix=".state-", delete=False,
    )
    temporary_path = Path(temporary.name)
    try:
        with temporary:
            json.dump(state, temporary, indent=2)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, state_path)
    finally:
        temporary_path.unlink(missing_ok=True)