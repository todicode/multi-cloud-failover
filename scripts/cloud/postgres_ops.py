import json
import subprocess

def run_postgres_sql(config, sql, timeout=20):
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
        timeout=timeout,
    )
    return result.stdout.strip()

def read_postgres_status(config):
    sql = """SELECT json_build_object(
        'in_recovery', pg_is_in_recovery(),
        'read_only', current_setting('transaction_read_only'),
        'receive_lsn', pg_last_wal_receive_lsn()::text,
        'replay_lsn', pg_last_wal_replay_lsn()::text
    );"""
    status = json.loads(run_postgres_sql(config, sql))
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

def promote_standby(config):
    sql = "SELECT json_build_object('promoted', pg_promote(true, 60));"
    result = json.loads(run_postgres_sql(config, sql, timeout=75))
    if not isinstance(result, dict) or result.get("promoted") is not True:
        raise RuntimeError("PostgreSQL promotion was not confirmed.")

    status = read_postgres_status(config)
    if status.get("in_recovery") is not False or status.get("read_only") != "off":
        raise RuntimeError("PostgreSQL primary role was not confirmed.")
    return status