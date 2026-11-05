# Implementation roadmap

The project progresses from local recovery validation to deployment and measurement across independent cloud environments. Completion requires working behavior and reproducible evidence, not only configuration files.

## Completed: local system

- [x] FastAPI Issues UI and API with PostgreSQL persistence.
- [x] Separate primary and standby PostgreSQL 17 databases.
- [x] Asynchronous WAL replication and standby write rejection.
- [x] Shared URL with routing gated on completed writer transitions.
- [x] Planned switchover and unplanned failover with fencing.
- [x] Rejoin on new volumes and controlled failback.
- [x] Local failure watcher and read/write measurement tools.
- [x] Local API/database test suite: 19 tests passed.
- [x] End-to-end lifecycle validation, including interrupted recovery.
- [x] Stop/restart validation with persistent data.
- [x] Reproducible [Stage 1 installation and validation instructions](instruction/giaidoan1_ungdung_database_local.md).

## Completed: application container packaging

- [x] Linux AMD64 application image with an unprivileged runtime user.
- [x] Two application containers using the same image ID and separate runtime configuration.
- [x] HTTP checks and direct connectivity to the primary and standby over the lab Docker network.
- [x] Manual issue/comment replication checks through the containerized web instances.
- [x] Reproducible [Stage 2 container packaging instructions](instruction/giaidoan2_docker_hoa_ungdung.md).

## Planned milestones

| Phase | Deliverable | Acceptance evidence |
|---|---|---|
| CI and registry | Test/build/publish workflow and immutable image digest | Successful workflow run and clean pull of the selected digest |
| Infrastructure | Independent AWS and Azure compute, networking, IPs, and storage | Reviewed Terraform plan and inventory for the selected accounts |
| Cluster and workload | Two K3s environments, PostgreSQL, application, and WireGuard | Node/pod readiness, tunnel connectivity, role checks, and replayed business data |
| HTTPS | Origin/shared hostnames and certificate renewal | Valid TLS on both origins and the shared hostname |
| DNS failover | Writer health checks and Route 53 routing | Traffic reaches the promoted writer after the old writer is fenced |
| Observability | Monitoring outside the application environments | Origin/writer availability, latency, and replication signals |
| Cloud recovery | Manual failover, rejoin, and controlled failback | A single writer throughout; verified data after both transitions |
| Automatic failover | Optional Azure-hosted watcher | Confirmed fencing before promotion and observable failure handling |
| Evaluation | Repeated failure exercises and operational analysis | Raw measurements for downtime, latency, errors, data loss, and cost |

The [Stage 3 guide](instruction/giaidoan3_ci_va_container_registry.md) is being developed incrementally. CI and publication are not validated until a complete workflow has run successfully on GitHub.

## Evaluation goals

Compare a single-environment baseline with standby-assisted recovery. Separate detection time, controller execution time, and client-visible recovery. Measure replication loss under unplanned failure rather than assuming zero data loss. Record the operational work required for rejoin, failback, backups, credential management, and cleanup.

Cloud recovery times, cost, capacity, and availability remain unmeasured until these milestones have been deployed and exercised.
