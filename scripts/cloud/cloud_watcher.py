import json
from pathlib import Path
import httpx
import boto3
from botocore.config import Config

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
    ec2_response = ec2.describe_instances(
        InstanceIds=[config["aws_instance_id"]],
    )
    instance = ec2_response["Reservations"][0]["Instances"][0]
    instance_state = instance["State"]["Name"]
    print(f"aws_ec2_state={instance_state}")

    route53 = session.client("route53", config=aws_client_config)
    health_response = route53.get_health_check_status(
        HealthCheckId=config["aws_health_check_id"],
    )
    observations = health_response["HealthCheckObservations"]
    for observation in observations:
        region = observation["Region"]
        status = observation["StatusReport"]["Status"]
        print(f"route53 region={region} status={status}")

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