from scripts.cloud.config import load_config
from scripts.cloud.rejoin.workflow import run_rejoin


def run_aws_rejoin(operation_id):
    return run_rejoin(load_config(), "aws", operation_id)
