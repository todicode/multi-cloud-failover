from contextlib import contextmanager
from pathlib import Path


class RejoinBusy(RuntimeError):
    """Another worker is already running on this host."""


def rejoin_lock():
    return operation_lock("mcf-rejoin", "worker.lock")


@contextmanager
def operation_lock(directory, filename):
    import fcntl

    state_directory = Path.home() / ".local" / "state" / directory
    state_directory.mkdir(mode=0o700, parents=True, exist_ok=True)

    with (state_directory / filename).open("a") as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RejoinBusy(f"Another process holds {state_directory / filename}.") from error
        yield
