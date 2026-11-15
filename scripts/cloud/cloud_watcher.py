import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from botocore.exceptions import BotoCoreError, ClientError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from scripts.cloud.aws_ops import create_aws_clients, read_instance_state

from scripts.cloud.checks import (
    classify_probe,
    classify_route53,
    classify_route53_report,
    probe_writer,
)
from scripts.cloud.postgres_ops import read_postgres_status

CONFIG_PATH = PROJECT_ROOT / "deploy" / "watcher" / "config.json"


def load_config():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    if not isinstance(config, dict):
        raise ValueError("Watcher config must be a JSON object.")
    if type(config.get("enable_auto_failover")) is not bool:
        raise ValueError("enable_auto_failover must be true or false.")
    return config



def main():
    config = load_config()
    sts, ec2, route53 = create_aws_clients(config)
    identity = sts.get_caller_identity()
    print(f"aws_identity={identity['Arn']}")

    failure_count = 0
    while True:
        try:
            instance_state = read_instance_state(ec2, config["aws_instance_id"])
        except (BotoCoreError, ClientError, RuntimeError) as error:
            instance_state = "unknown"
            print(f"aws_ec2_error={type(error).__name__}: {error}")
        print(f"aws_ec2_state={instance_state}")

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

        writer_states = {}
        for cloud in ("aws", "azure"):
            url = config[f"{cloud}_writer_url"]
            result = probe_writer(url, config["http_timeout_seconds"])
            state = classify_probe(result)
            writer_states[cloud] = state
            print(f"{cloud} state={state}, result={json.dumps(result, ensure_ascii=False)}")

        failover_candidate = (
            writer_states["aws"] == "unavailable"
            and route53_state == "unhealthy"
            and writer_states["azure"] == "standby"
        )
        print(f"failover_candidate={failover_candidate}")

        if failover_candidate:
            failure_count += 1
        else:
            failure_count = 0
        threshold_reached = failure_count >= config["failure_threshold"]
        print(f"consecutive_failures={failure_count}")
        print(f"failover_threshold_reached={threshold_reached}")
        time.sleep(config["interval_seconds"])


if __name__ == "__main__":
    main()
