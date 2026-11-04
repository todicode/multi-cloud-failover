# Disaster recovery runbook

This runbook applies to the local PostgreSQL replication environment. It validates recovery behavior on one development machine; it does not establish cloud recovery objectives.

## Preconditions

Configure the terminal and inspect the topology:

```powershell
. .\scripts\Use-LocalLab.ps1
.\.venv\Scripts\python.exe scripts/local_replication.py status
```

Identify the current writer and phase before changing roles. The normal starting topology is AWS primary, Azure streaming standby, and the shared proxy serving AWS. Keep the shared URL `http://127.0.0.1:8190` throughout a recovery exercise.

## Planned switchover to Azure

Use this operation while AWS remains available:

```powershell
.\.venv\Scripts\python.exe scripts/local_replication.py switchover
```

The controller pauses application writes, drains in-flight transactions, records the final WAL position, waits for Azure replay, fences AWS, promotes Azure, verifies the writer, and updates routing. A planned switchover avoids losing application transactions when all relevant writers are covered by the barrier and the required WAL has replayed.

Verify Azure is primary/writable through the shared URL and add a comment to an existing issue. That new comment becomes part of the recovery data checks.

## Unplanned failover

Start from a verified AWS-primary topology. To simulate an abrupt database failure:

```powershell
docker compose -p mcf-todicode -f database/compose.replication.yml kill database
.\.venv\Scripts\python.exe scripts/local_replication.py failover
```

Unlike planned switchover, this operation cannot obtain a final WAL cutoff from an unavailable primary. It fences the AWS container, promotes Azure using the available data, verifies write eligibility, and switches the proxy. Recent acknowledged transactions may be missing because replication is asynchronous.

Verify:

```powershell
Invoke-RestMethod http://127.0.0.1:8190/version
Invoke-RestMethod http://127.0.0.1:8190/api/database/status
```

The shared URL should identify Azure with `role=primary` and `writable=true`. Compare issue contents, comments, history, and retry results.

## Automatic local watcher

Run the watcher in a separate configured terminal before injecting the failure:

```powershell
. .\scripts\Use-LocalLab.ps1
.\.venv\Scripts\python.exe scripts/watcher.py --interval 5 --threshold 3
```

It checks the AWS writer HTTP endpoint and a direct PostgreSQL connection. Agreeing failures increment a counter; both checks healthy reset it. When checks disagree, the current count is retained. A busy topology transition pauses decisions and resets the count. At the threshold, the watcher invokes the same local failover operation.

The watcher exits after failover and never performs automatic failback. Do not run a manual promotion concurrently with an active watcher.

## Rejoin AWS

While Azure serves writes:

```powershell
.\.venv\Scripts\python.exe scripts/local_replication.py rejoin-aws
.\.venv\Scripts\python.exe scripts/local_replication.py status
```

AWS is rebuilt from Azure on a new volume and joins as a standby. Its previous volume is retained. Verify replay and compare data written on Azure before returning traffic to AWS.

## Controlled failback

```powershell
.\.venv\Scripts\python.exe scripts/local_replication.py failback
```

The controller performs rejoin if needed, pauses Azure writes, waits for AWS replay, fences Azure, promotes and verifies AWS, then rebuilds Azure as its standby.

Completion criteria:

- AWS is primary and writable; Azure is standby and streaming.
- The shared URL serves AWS.
- Data written while Azure was primary remains present after failback.
- Issue versions, comments, history, and retry receipts are consistent after replay.

If a transition fails, inspect state and logs, resolve the cause, and retry the same operation. Do not edit the writer field to bypass a failed step or restart an old primary independently.

## Measure an exercise

Run a read/write probe from a separate terminal:

```powershell
. .\scripts\Use-LocalLab.ps1
$RunDirectory = 'experiments/runs/local-failover-01'
New-Item -ItemType Directory -Force -Path $RunDirectory | Out-Null
.\.venv\Scripts\python.exe scripts/probe_failover.py --url http://127.0.0.1:8190 --duration 180 --out "$RunDirectory/probe.csv"
```

Choose a new run directory for each exercise. Inject the failure from the control terminal while the probe is running. The probe calls `GET /version` and `POST /api/ping`, writes CSV samples and a JSON summary, and checks which acknowledged writes are missing on the current writer.

Report read and write downtime separately, include the sampling interval and failure timestamp, and distinguish missing acknowledged writes from requests with an unknown outcome. Keep local measurements separate from future cloud measurements.
