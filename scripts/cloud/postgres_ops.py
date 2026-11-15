import json
import subprocess

def read_postgres_status(config):
    sql = """SELECT json_build_object(
        'in_recovery', pg_is_in_recovery(),
        'read_only', current_setting('transaction_read_only'),
        'receive_lsn', pg_last_wal_receive_lsn()::text,
        'replay_lsn', pg_last_wal_replay_lsn()::text
    );"""
    command = [
        "sudo", "-n", "k3s", "kubectl",
        "-n", config["kubernetes_namespace"],
        "exec", config["postgres_pod"], "--",
        "psql", "-X", "-v", "ON_ERROR_STOP=1",
        "-U", "taskflow", "-d", "taskflow",
        "-At", "-c", sql,
    ]
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    status = json.loads(result.stdout)
    if not isinstance(status, dict):
        raise ValueError("PostgreSQL status must be a JSON object.")
    return status

def preflight_standby(config):
    status = read_postgres_status(config)
    if status.get("in_recovery") is not True:
        raise RuntimeError("Target PostgreSQL must be a standby.")
    if status.get("read_only") != "on":
        raise RuntimeError("Standby PostgreSQL must be read-only.")
    return status