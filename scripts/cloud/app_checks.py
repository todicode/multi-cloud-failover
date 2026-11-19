from urllib.parse import urlsplit

import httpx


def get_json(url, timeout):
    response = httpx.get(url, timeout=timeout, trust_env=False)
    response.raise_for_status()
    return response.json()


def origin_url(writer_url):
    parts = urlsplit(writer_url)
    return f"{parts.scheme}://{parts.netloc}"


def write_shared_probe(config, cloud, run_id, seq):
    base = config["shared_app_url"].rstrip("/")
    timeout = config["http_timeout_seconds"]
    version = get_json(f"{base}/version", timeout)
    if version["environment"] != cloud:
        raise RuntimeError(f"Shared hostname currently selects {version['environment']}; waiting for {cloud}.")
    data = {"run_id": run_id, "seq": seq}
    response = httpx.post(f"{base}/api/ping", json=data, timeout=timeout, trust_env=False)
    response.raise_for_status()
    if response.json() != {**data, "environment": cloud}:
        raise RuntimeError(f"Shared write receipt did not confirm {cloud} as writer.")
    require_probe_records(base, timeout, run_id, {seq: cloud})


def require_probe_records(base, timeout, run_id, expected):
    result = get_json(f"{base}/api/ping/{run_id}", timeout)
    records = {row["seq"]: row["environment"] for row in result["pings"]}
    if result["run_id"] != run_id or any(records.get(seq) != cloud for seq, cloud in expected.items()):
        raise RuntimeError(f"Probe {run_id} does not yet contain expected records at {base}.")
