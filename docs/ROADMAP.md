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

## Completed: CI and container registry

- [x] API/PostgreSQL tests on GitHub Actions.
- [x] Dependent Linux AMD64 image build and GHCR publication.
- [x] Published image pull by digest and runtime/database checks locally.
- [x] Separate CI runner: pull by digest, revision/default-user checks, application startup, and HTTP smoke checks.
- [x] Successful [three-job workflow run](https://github.com/todicode/multi-cloud-failover/actions/runs/42080473436) and recorded artifact identity in the [Stage 3 guide](instruction/giaidoan3_ci_va_container_registry.md).

## In progress: cloud infrastructure

The [Stage 4 guide](instruction/giaidoan4_ha_tang_aws_azure_terraform.md) covers operator tooling, Azure fundamentals and account checks, AWS authentication, and incremental Terraform implementation. The initial AWS network has been deployed in Singapore: VPC, subnet, Internet Gateway, public route table, and subnet association. Acceptance confirmed five managed resources and a subsequent plan with no changes. Compute and Azure infrastructure remain to be implemented.

The implementation sequence completes the required Azure background, then builds and validates AWS infrastructure with Terraform before Azure. Infrastructure code stays in this repository under `deploy/terraform/`. AWS uses the `deploy/terraform/aws/` root module with a local backend for the single-operator lab; Azure will use a separate root module and state. State and saved plans are excluded from version control; the provider lock file is committed.

## Planned milestones

| Phase | Deliverable | Acceptance evidence |
|---|---|---|
| Infrastructure | Independent AWS and Azure compute, networking, IPs, and storage | Reviewed Terraform plan and inventory for the selected accounts |
| Cluster and workload | Two K3s environments, PostgreSQL, application, and WireGuard | Node/pod readiness, tunnel connectivity, role checks, and replayed business data |
| HTTPS | Origin/shared hostnames and certificate renewal | Valid TLS on both origins and the shared hostname |
| DNS failover | Writer health checks and Route 53 routing | Traffic reaches the promoted writer after the old writer is fenced |
| Observability | Monitoring outside the application environments | Origin/writer availability, latency, and replication signals |
| Cloud recovery | Manual failover, rejoin, and controlled failback | A single writer throughout; verified data after both transitions |
| Automatic failover | Optional Azure-hosted watcher | Confirmed fencing before promotion and observable failure handling |
| Evaluation | Repeated failure exercises and operational analysis | Raw measurements for downtime, latency, errors, data loss, and cost |

## Evaluation goals

Compare a single-environment baseline with standby-assisted recovery. Separate detection time, controller execution time, and client-visible recovery. Measure replication loss under unplanned failure rather than assuming zero data loss. Record the operational work required for rejoin, failback, backups, credential management, and cleanup.

Cloud recovery times, cost, capacity, and availability remain unmeasured until these milestones have been deployed and exercised.
