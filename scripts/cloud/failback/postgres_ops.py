import re

from scripts.cloud.failover.postgres_ops import read_postgres_status, run_postgres_sql


def lsn_value(lsn):
    if not isinstance(lsn, str) or not re.fullmatch(r"[0-9A-Fa-f]{1,8}/[0-9A-Fa-f]{1,8}", lsn):
        raise ValueError(f"Invalid PostgreSQL LSN: {lsn!r}")
    high, low = lsn.split("/")
    return (int(high, 16) << 32) | int(low, 16)


def replayed_write_barrier(status, target_lsn):
    replay = status["replay_lsn"]
    return (
        status["in_recovery"] is True
        and status["read_only"] == "on"
        and status["writes_enabled"] is False
        and replay is not None
        and lsn_value(replay) >= lsn_value(target_lsn)
    )


def require_primary(config):
    status = read_postgres_status(config)
    if status["in_recovery"] is not False or status["read_only"] != "off":
        raise RuntimeError("Expected a writable PostgreSQL primary role.")
    return status


def set_app_writes(config, enabled):
    current = require_primary(config)
    if type(current["writes_enabled"]) is not bool:
        raise RuntimeError("Application write-control row is missing.")
    desired = "TRUE" if enabled else "FALSE"
    lsn = run_postgres_sql(config, f"""
        BEGIN;
        SET LOCAL lock_timeout = '15s';
        SET LOCAL synchronous_commit = on;
        SELECT pg_advisory_xact_lock(2900, 1);
        UPDATE app_control SET writes_enabled = {desired} WHERE singleton;
        COMMIT;
        SELECT pg_current_wal_flush_lsn()::text;
    """, timeout=30).splitlines()[-1]
    lsn_value(lsn)
    if require_primary(config)["writes_enabled"] is not enabled:
        raise RuntimeError("Application write barrier did not reach the requested state.")
    return lsn
