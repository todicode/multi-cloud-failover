# Implementation roadmap

The project progresses from local recovery validation to deployment and measurement across independent cloud environments. Completion requires working behavior and reproducible evidence, not only configuration files.

The [project requirements and acceptance criteria](PROJECT_REQUIREMENTS.md) track Topic 29 suggested tasks, General Deliverables, and the assessment rubric. Use them when accepting each milestone; baseline comparison and repeatable measurements remain required project deliverables.

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

## Validated: cloud infrastructure

The [Stage 4 guide](instruction/giaidoan4_ha_tang_aws_azure_terraform.md) covers operator tooling, Azure fundamentals and account checks, AWS authentication, and incremental Terraform implementation. AWS networking, host access rules, EC2, SSH Key Pair, and Elastic IP were deployed and validated in Singapore. Status checks and SSH acceptance passed, and the post-apply plan reported no changes. The subnet AZ and Ubuntu AMI are pinned; the host configuration includes encrypted root EBS, Standard CPU credits, and IMDSv2. Lab resources were subsequently removed, including retained EBS and Elastic IP, to control costs while implementing Azure.

The Azure root module deployed eleven resources: Resource Group, VNet, subnet, NSG and SSH/HTTP/HTTPS rules, Static Public IP, NIC, NIC–NSG association, and Ubuntu VM. The VM uses Standard_B2als_v2 in Zone 1 with a pinned Ubuntu 24.04 image and a 32 GiB Standard SSD OS disk. Formatting, validation, deployment, VM/agent state checks, and a clean post-apply plan passed. The operator confirmed SSH access and the expected username/Ubuntu version. The Azure lab was subsequently removed with a reviewed Terraform destroy plan, including the managed OS disk and Static Public IP. Infrastructure has been validated independently on both clouds; cloud clusters and workloads remain pending.

The implementation sequence completes the required Azure background, then builds and validates AWS infrastructure with Terraform before Azure. Infrastructure code stays in this repository under `deploy/terraform/`. AWS and Azure use separate root modules under `deploy/terraform/aws/` and `deploy/terraform/azure/`, with separate local state for the single-operator lab. State and saved plans are excluded from version control; provider lock files are committed. Both lab environments are currently removed. Recreate them from fresh reviewed plans for the cluster, WireGuard, and replication exercises.

## Milestones

| Phase | Deliverable | Acceptance evidence |
|---|---|---|
| Infrastructure | Independent AWS and Azure compute, networking, IPs, and storage | Validated independently: deployment, post-apply plan, and SSH; lab resources subsequently removed on both clouds |
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
