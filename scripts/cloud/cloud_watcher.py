import json
from pathlib import Path
import httpx
import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "deploy" / "watcher" / "config.json"


def load_config():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    if not isinstance(config, dict):
        raise ValueError("Watcher config must be a JSON object.")
    if type(config.get("enable_auto_failover")) is not bool:
        raise ValueError("enable_auto_failover must be true or false.")
    return config

def probe_writer(url, timeout):
    try:
        response = httpx.get(
            url,
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
        )
    except httpx.RequestError as error:
        return {"http_status": None, "error": type(error).__name__}

    try:
        body = response.json()
    except ValueError:
        return {"http_status": response.status_code, "error": "invalid_json"}

    return {"http_status": response.status_code, "body": body}

def classify_probe(result):
    if result.get("error") in ("ConnectTimeout", "ReadTimeout"):
        return "unavailable"

    status = result.get("http_status")
    body = result.get("body")
    if (
        status == 503
        and isinstance(body, dict)
        and body.get("connected") is False
    ):
        return "unavailable"
    if not isinstance(body, dict) or body.get("connected") is not True:
        return "unknown"

    role = body.get("role")
    writable = body.get("writable")
    paused = body.get("writes_paused")

    if status == 200 and role == "primary" and writable is True and paused is False:
        return "writer"
    if status == 503 and role == "primary" and writable is False and paused is True:
        return "paused"
    if status == 503 and role == "standby" and writable is False:
        return "standby"
    return "unknown"

def classify_route53_report(report, now, max_age_seconds=120):
    if not isinstance(report, dict):
        return "unknown"
    status = report.get("Status")
    checked_at = report.get("CheckedTime")
    if not isinstance(status, str) or not isinstance(checked_at, datetime):
        return "unknown"
    if checked_at.tzinfo is None:
        return "unknown"

    age_seconds = (now - checked_at).total_seconds()
    if not 0 <= age_seconds <= max_age_seconds:
        return "unknown"
    if status.startswith("Success:"):
        return "healthy"
    if status.startswith("Failure:"):
        return "unhealthy"
    return "unknown"

def classify_route53(observations, now):
    if not observations:
        return "unknown"
    states = [
        classify_route53_report(observation.get("StatusReport"), now)
        for observation in observations
    ]
    if all(state == "healthy" for state in states):
        return "healthy"
    if all(state == "unhealthy" for state in states):
        return "unhealthy"
    return "unknown"

def main():
    config = load_config()

    aws_client_config = Config(
        connect_timeout=5,
        read_timeout=5,
        retries={"mode": "standard", "total_max_attempts": 2},
    )

    session = boto3.Session(
        profile_name=config["aws_profile"],
        region_name=config["aws_region"],
    )
    sts = session.client("sts", config=aws_client_config)
    identity = sts.get_caller_identity()
    print(f"aws_identity={identity['Arn']}")

    ec2 = session.client("ec2", config=aws_client_config)
    try:
        ec2_response = ec2.describe_instances(
            InstanceIds=[config["aws_instance_id"]],
        )
        instance = ec2_response["Reservations"][0]["Instances"][0]
        instance_state = instance["State"]["Name"]
    except (BotoCoreError, ClientError) as error:
        instance_state = "unknown"
        print(f"aws_ec2_error={type(error).__name__}: {error}")
    print(f"aws_ec2_state={instance_state}")


    route53 = session.client("route53", config=aws_client_config)
    try:
        health_response = route53.get_health_check_status(
            HealthCheckId=config["aws_health_check_id"],
        )
        observations = health_response["HealthCheckObservations"]
    except (BotoCoreError, ClientError) as error:
        observations = None
        print(f"route53_error={type(error).__name__}: {error}")

    now = datetime.now(timezone.utc)
    route53_state = classify_route53(observations, now)
    print(f"route53_state={route53_state}")
    if observations:
        for observation in observations:
            region = observation["Region"]
            report = observation.get("StatusReport")
            checker_state = classify_route53_report(report, now)
            print(f"route53 region={region} state={checker_state}")

    mode = "automatic" if config["enable_auto_failover"] else "observe"
    print(f"mode={mode}")
    print(f"aws_region={config['aws_region']}")
    print(f"aws_instance_id={config['aws_instance_id']}")
    print(f"aws_writer_url={config['aws_writer_url']}")
    for cloud in ("aws", "azure"):
        url = config[f"{cloud}_writer_url"]
        result = probe_writer(url, config["http_timeout_seconds"])
        state = classify_probe(result)
        print(f"{cloud} state={state}, result={json.dumps(result, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
