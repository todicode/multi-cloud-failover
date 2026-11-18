from scripts.cloud.failover.checks import classify_probe, probe_writer


def require_source_writer(source_url, timeout=5):
    result = probe_writer(source_url, timeout)
    state = classify_probe(result)
    if state != "writer":
        raise RuntimeError(
            f"Rejoin source writer was not confirmed: {result}"
        )
    return result["body"]