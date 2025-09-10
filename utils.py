from typing import List

from models import NodeSpec, PodSpec
import logging
from kubernetes import client, config

log = logging.getLogger(__name__)

# Try in-cluster config first; fall back to local for dev
try:
    config.load_incluster_config()
except Exception:
    config.load_kube_config()

v1 = client.CoreV1Api()


SCHEDULER_NAME = "mvinchoo-scheduler"


def get_all_nodes() -> List[NodeSpec]:
    node_list = v1.list_node().items
    node_specs: List[NodeSpec] = []

    for node in node_list:
        node_name = node.metadata.name
        nspec = NodeSpec(name=node_name)

        pods = v1.list_pod_for_all_namespaces(field_selector=f"spec.nodeName={node_name}")
        for p in pods.items:
            if p.spec.scheduler_name != SCHEDULER_NAME:
                continue

            pod_spec = PodSpec(
                namespace=p.metadata.namespace,
                name=p.metadata.name,
                priority=p.spec.priority or 0,
                creation_timestamp=p.metadata.creation_timestamp,
            )
            nspec.add_pod(pod_spec)

        node_specs.append(nspec)

    return node_specs


def get_pending_pods() -> List[PodSpec]:
    pods = v1.list_pod_for_all_namespaces(field_selector="status.phase=Pending")
    result: List[PodSpec] = []
    for p in pods.items:
        if p.spec.scheduler_name != SCHEDULER_NAME:
            continue

        result.append(
            PodSpec(
                namespace=p.metadata.namespace,
                name=p.metadata.name,
                priority=p.spec.priority if p.spec.priority is not None else 0,
                creation_timestamp=p.metadata.creation_timestamp,
            )
        )
    return result