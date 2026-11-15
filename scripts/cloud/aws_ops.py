import boto3
from botocore.config import Config


def create_aws_clients(config):
    client_config = Config(
        connect_timeout=5,
        read_timeout=5,
        retries={"mode": "standard", "total_max_attempts": 2},
    )

    session = boto3.Session(
        profile_name=config["aws_profile"],
        region_name=config["aws_region"],
    )

    sts = session.client("sts", config=client_config)
    ec2 = session.client("ec2", config=client_config)
    route53 = session.client("route53", config=client_config)

    return sts, ec2, route53


def read_instance_state(ec2, instance_id):
    response = ec2.describe_instances(InstanceIds=[instance_id])
    reservations = response["Reservations"]

    if not reservations or not reservations[0]["Instances"]:
        raise RuntimeError(f"EC2 instance {instance_id} was not returned.")

    instance = reservations[0]["Instances"][0]
    return instance["State"]["Name"]

def fence_instance(ec2, instance_id):
    state = read_instance_state(ec2, instance_id)
    if state == "stopped":
        return state

    if state == "running":
        ec2.stop_instances(InstanceIds=[instance_id])
    elif state != "stopping":
        raise RuntimeError(f"Cannot fence EC2 instance in state {state}.")

    waiter = ec2.get_waiter("instance_stopped")
    waiter.wait(
        InstanceIds=[instance_id],
        WaiterConfig={"Delay": 5, "MaxAttempts": 60},
    )
    return "stopped"