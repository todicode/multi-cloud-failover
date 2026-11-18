import subprocess
from pathlib import Path


def run_host_command(*arguments, timeout=60):
    result = subprocess.run(
        ["sudo", "-n", *arguments],
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.stdout.strip()


def start_agentless_control_plane(project_root):
    config_source = Path(project_root) / "deploy/k3s/rejoin-control-plane.yaml"
    if not config_source.is_file():
        raise FileNotFoundError(config_source)

    config_directory = "/etc/rancher/k3s/config.yaml.d"
    run_host_command("systemctl", "stop", "k3s", timeout=120)
    run_host_command("install", "-d", "-m", "700", config_directory)
    run_host_command(
        "install", "-m", "600", str(config_source),
        f"{config_directory}/99-rejoin.yaml",
    )
    run_host_command("touch", "/run/issues-k3s-start-approved")
    run_host_command("systemctl", "reset-failed", "k3s")
    run_host_command("systemctl", "start", "k3s", timeout=120)

def require_postgres_stopped():
    result = subprocess.run(
        ["pgrep", "-a", "-x", "postgres"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode == 1:
        return
    result.check_returncode()
    raise RuntimeError(f"PostgreSQL is still running: {result.stdout.strip()}")


def restore_agent():
    run_host_command("systemctl", "stop", "k3s", timeout=120)
    run_host_command("rm", "-f", "--", "/etc/rancher/k3s/config.yaml.d/99-rejoin.yaml")
    run_host_command("systemctl", "start", "k3s", timeout=120)