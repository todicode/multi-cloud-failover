from datetime import datetime

import httpx

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
