import json
from datetime import datetime, timezone

from botocore.exceptions import BotoCoreError, ClientError

from scripts.cloud.failover.aws_ops import read_instance_state
from scripts.cloud.failover.checks import classify_probe, classify_route53, probe_writer


def failover_candidate(config, ec2, route53):
    try:
        instance = read_instance_state(ec2, config["aws_instance_id"])
    except (BotoCoreError, ClientError, RuntimeError) as error:
        instance = "unknown"
        print(f"aws_ec2_error={type(error).__name__}: {error}")

    try:
        response = route53.get_health_check_status(HealthCheckId=config["aws_health_check_id"])
        dns_health = classify_route53(response["HealthCheckObservations"], datetime.now(timezone.utc))
    except (BotoCoreError, ClientError) as error:
        dns_health = "unknown"
        print(f"route53_error={type(error).__name__}: {error}")

    results = {}
    for cloud in ("aws", "azure"):
        results[cloud] = probe_writer(config[f"{cloud}_writer_url"], config["http_timeout_seconds"])

    aws = classify_probe(results["aws"])
    azure = classify_probe(results["azure"])
    aws_down = aws == "unavailable" or (
        instance == "stopped" and results["aws"].get("http_status") is None
    )
    candidate = aws_down and dns_health == "unhealthy" and azure == "standby"
    print(f"aws_ec2_state={instance} route53_state={dns_health} aws={aws} azure={azure} failover_candidate={candidate}")
    print(f"writer_probes={json.dumps(results)}")
    return candidate
