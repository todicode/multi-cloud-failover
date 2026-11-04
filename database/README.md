# Database

PostgreSQL stores the application workload, request receipts, and recovery control state. The local topology uses two PostgreSQL 17 containers with independent persistent volumes and asynchronous physical streaming replication.

## Schema

| Table | Responsibility |
|---|---|
| `issues` | Issue identity, number, title, description, author, status, version, and timestamps |
| `comments` | Comments associated with an issue |
| `issue_history` | Recorded business operations and before/after data |
| `save_requests` | Request payloads and results used for retry handling |
| `app_control` | Application write gate coordinated with advisory locks |
| `probe_pings` | Sequenced writes used to measure availability and data loss |

Issue changes, history entries, and request receipts are committed together. Stale issue versions return a conflict. The same request ID cannot be reused for different operation content.

## Components

| Path | Purpose |
|---|---|
| `connection.py` | PostgreSQL connection configuration |
| `issues.py` | Business queries, transactions, version checks, and retry receipts |
| `control.py` | Shared/exclusive write coordination |
| `role.py` | Database role, WAL status, and writer health endpoints |
| `local_state.py` | Durable local controller/proxy state |
| `schema/` | Idempotent schema bootstrap SQL |
| `compose.replication.yml` | Primary/standby containers and volume configuration |
| `replication/` | Primary replication setup and standby bootstrap scripts |

## Local configuration

Run from the repository root:

```powershell
. .\scripts\Use-LocalLab.ps1
.\.venv\Scripts\python.exe scripts/local_replication.py setup
```

The helper selects Docker project `mcf-todicode`, PostgreSQL host ports 56432/56433, and the development `DATABASE_URL`. The local database/user name is `taskflow`. Application processes use host ports; replication uses the internal Docker network and PostgreSQL port 5432.

`setup` bootstraps schema only on the primary before cloning the standby. It preserves existing primary data and rejects unsafe role changes. Schema creation is a development bootstrap mechanism, not a versioned production migration system.

## Storage and recovery

Database files live in Docker volumes, not in the repository or application source. Rejoin creates a new volume and retains the old one for inspection. Repeated recovery exercises therefore require additional disk space.

Asynchronous replication can lose recent acknowledged transactions when the primary fails. Replication also propagates logical deletions and does not replace an independent backup.

See [local development](../docs/LOCAL_DEVELOPMENT.md) for runtime operations and the [recovery runbook](../docs/DISASTER_RECOVERY.md) for switchover, failover, rejoin, and failback.
