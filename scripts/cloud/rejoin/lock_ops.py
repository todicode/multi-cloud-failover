from contextlib import contextmanager
from pathlib import Path


class RejoinBusy(RuntimeError):
    """Another worker is already running on this host."""


@contextmanager
def rejoin_lock():
    import fcntl

    state_directory = Path.home() / ".local" / "state" / "mcf-rejoin"
    state_directory.mkdir(mode=0o700, parents=True, exist_ok=True)

    with (state_directory / "worker.lock").open("a") as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RejoinBusy("A rejoin worker is already running.") from error
        yield