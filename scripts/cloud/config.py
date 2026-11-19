import json
from pathlib import Path
from urllib.parse import urlsplit

CONFIG_PATH = Path(__file__).resolve().parents[2] / "deploy/watcher/config.json"


def load_config(path=CONFIG_PATH):
    config = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(config, dict):
        raise ValueError("Watcher config must be a JSON object.")
    config.setdefault("enable_auto_recovery", False)
    for flag in ("enable_auto_failover", "enable_auto_recovery"):
        if type(config.get(flag)) is not bool:
            raise ValueError(f"{flag} must be true or false.")
    if config["enable_auto_recovery"] and not config["enable_auto_failover"]:
        raise ValueError("Automatic recovery requires automatic failover.")

    for key in ("interval_seconds", "http_timeout_seconds", "failure_threshold"):
        if type(config.get(key)) is not int or config[key] < 1:
            raise ValueError(f"{key} must be a positive integer.")
    if config["enable_auto_recovery"]:
        if type(config.get("azure_writer_min_seconds")) is not int or config["azure_writer_min_seconds"] < 300:
            raise ValueError("azure_writer_min_seconds must be at least 300.")
        shared = urlsplit(config.get("shared_app_url", ""))
        if shared.scheme != "https" or not shared.hostname or shared.path not in ("", "/") or shared.query or shared.fragment:
            raise ValueError("shared_app_url must be an HTTPS origin.")
    return config
