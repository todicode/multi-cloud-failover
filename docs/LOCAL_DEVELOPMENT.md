# Local development

For a complete setup and validation walkthrough, see [Stage 1 instructions](instruction/giaidoan1_ungdung_database_local.md).

## Requirements

- Windows PowerShell and Python 3.12.
- Docker Desktop with the Linux container engine running.
- Available application ports 8180, 8181, and 8190; database ports 56432 and 56433.

The local workflow runs the web processes on the host and PostgreSQL in Docker. Commands below run from the repository root.

## Install dependencies

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

An existing virtual environment can be reused. There is no need to recreate it each time the application starts.

## Configure the terminal

```powershell
. .\scripts\Use-LocalLab.ps1
```

This selects Docker project `mcf-todicode`, sets the five local ports and `DATABASE_URL`, and enables UTF-8 for Python output. Repeat it in each new terminal used for the lab. PostgreSQL credentials are development-only and database ports bind to localhost.

## Start the initial topology

```powershell
.\.venv\Scripts\python.exe scripts/local_replication.py setup
.\.venv\Scripts\python.exe scripts/local_replication.py start-web
.\.venv\Scripts\python.exe scripts/local_replication.py start-proxy
```

`setup` configures the primary, creates the application schema, and initializes the standby. It preserves existing primary data. It rejects a topology that has already changed roles; use the [recovery runbook](DISASTER_RECOVERY.md) after a failover.

The web commands start background processes and record their PIDs and logs. They refuse to start on occupied ports. If the application is already running, inspect it instead of starting another copy.

Open `http://127.0.0.1:8190/issues.html`. Direct application URLs are `http://127.0.0.1:8180/issues.html` and `http://127.0.0.1:8181/issues.html`.

## Optional sample data

```powershell
.\.venv\Scripts\python.exe scripts/seed_demo.py --url http://127.0.0.1:8190
```

This creates five example issues through the API. Stable request IDs make repeated runs reuse the same operations.

## Inspect runtime state

```powershell
.\.venv\Scripts\python.exe scripts/local_replication.py status
Invoke-RestMethod http://127.0.0.1:8190/api/proxy/status
Invoke-RestMethod http://127.0.0.1:8180/api/database/status
Invoke-RestMethod http://127.0.0.1:8181/api/database/status
```

The initial state should show AWS as primary/writable and Azure as standby/read-only with a streaming receiver. Create an issue or comment through the shared URL and compare the complete issue details on Azure after replay. The standby interface polls periodically, so UI refresh delay is separate from replication delay.

## Run tests

With AWS acting as the writable local primary:

```powershell
$env:TASKFLOW_DB_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest -q
```

The database tests create isolated schemas and remove those schemas afterward. Without `TASKFLOW_DB_TESTS=1`, integration tests are skipped.

The end-to-end lifecycle check creates its own Docker project and runs a separate set of databases and web processes:

```powershell
.\.venv\Scripts\python.exe scripts/check_local_lifecycle.py
```

Ports 55632/55633, 18080/18081, and 18090 must be available. The check verifies repeated role transitions, unsafe setup rejection, retry handling, interrupted failback, preserved data/history, and watcher-triggered failover. Cleanup is restricted to its generated test project.

## Stop and restart

```powershell
.\scripts\Stop-LocalLab.ps1
```

The stop helper validates recorded processes against the repository's Python executable, module, and port before terminating their process trees. It stops the database project while preserving volumes and topology state.

For a normal AWS-primary restart, repeat the terminal configuration and startup commands. If Azure is the current primary or a transition was interrupted, recover using the existing phase and role information rather than running initial setup.

## Storage and logs

| Location | Content |
|---|---|
| Docker volumes belonging to `mcf-todicode` | PostgreSQL data |
| `.local-replication/mcf-todicode/state.json` | Current writer, phase, and transition timeline |
| `.local-replication/mcf-todicode/events.jsonl` | State transition history |
| `.local-replication/mcf-todicode/*.log` | Web and proxy output |
| `.local-replication/mcf-todicode/web.json`, `proxy.json` | Background process records |

Runtime data is excluded from Git. Removing volumes deletes database data; stopping containers does not. Bash scripts use LF line endings, enforced by `.gitattributes`, so they can run inside Linux containers.
