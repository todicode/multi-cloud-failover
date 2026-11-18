import json
from pathlib import Path

from scripts.cloud.rejoin.kubernetes_ops import read_manifest


def render_manifests(namespace, project_root, output_directory, operation_id):
    templates = Path(project_root) / "deploy/kubernetes/database"
    pvc = read_manifest(namespace, templates / "postgres-pvc-rejoin-aws.yaml")
    postgres = read_manifest(namespace, templates / "postgres-aws.yaml")
    clone = read_manifest(namespace, templates / "postgres-clone-rejoin-aws.yaml")

    pvc_name = f"postgres-data-rejoin-aws-{operation_id}"
    pvc["metadata"]["name"] = pvc_name
    postgres["spec"]["replicas"] = 0
    clone["metadata"]["name"] = f"postgres-clone-rejoin-aws-{operation_id}"

    for workload in (postgres, clone):
        volumes = workload["spec"]["template"]["spec"]["volumes"]
        data_volume = next(volume for volume in volumes if volume["name"] == "data")
        data_volume["persistentVolumeClaim"]["claimName"] = pvc_name

    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, manifest in (("pvc", pvc), ("postgres", postgres), ("clone", clone)):
        path = output_directory / f"{name}.json"
        path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        paths[name] = path
    return paths, pvc_name
