from collections import OrderedDict
from typing import List
from kubernetes import client, config
from models import PodSpec, NodeSpec
import logging

from utils import get_pending_pods, get_all_nodes

log = logging.getLogger(__name__)

# Try in-cluster config first; fall back to local for dev
try:
    config.load_incluster_config()
except Exception:
    config.load_kube_config()

v1 = client.CoreV1Api()


def bind_pod_to_node(pod_name: str, namespace: str, node_name: str) -> bool:
    target = client.V1ObjectReference(api_version="v1", kind="Node", name=node_name)
    meta = client.V1ObjectMeta(name=pod_name)
    body = client.V1Binding(metadata=meta, target=target)

    log.info(f"Bind pod {namespace}/{pod_name} -> {node_name}")
    try:
        if hasattr(v1, "create_namespaced_pod_binding"):
            v1.create_namespaced_pod_binding(
                name=pod_name,
                namespace=namespace,
                body=body,
                _preload_content=False,
            )
        else:
            v1.create_namespaced_binding(
                namespace=namespace,
                body=body,
                _preload_content=False,
            )
        return True
    except Exception as e:
        log.exception(e)
        return False


def preempt_pod(victim: PodSpec) -> bool:
    try:
        v1.delete_namespaced_pod(
            name=victim.name,
            namespace=victim.namespace,
            body=client.V1DeleteOptions(),
        )
        return True
    except Exception as e:
        log.exception(e)
        return False


class SchedulerActions:

    def __init__(self):
        self.pending_pods: List[PodSpec] = []
        self.available_nodes: List[NodeSpec] = []
        self.ACTIONS = OrderedDict()
        self.ACTIONS["ALLOCATE"] = self._allocate
        self.ACTIONS["PREEMPT"] = self._preempt

    def start_session(self):
        log.info("Starting Session")
        self.pending_pods: List[PodSpec] = get_pending_pods()
        self.available_nodes: List[NodeSpec] = get_all_nodes()
        log.info(f"Found {len(self.pending_pods)} pending pods and {len(self.available_nodes)} available nodes")
        # Always sort for simplicity
        self.pending_pods.sort()

        for action, func in self.ACTIONS.items():
            log.info(f"Starting action: {action}")
            func()
            log.info(f"Finished action: {action}")
        log.info("Ending Session")

    def _update_pod_and_nodes(self, allocated_nodes, allocated_pods):
        log.info(f"Updating pending pod and available nodes.")
        self.pending_pods = [p for p in self.pending_pods if p not in allocated_pods]
        if "PREEMPT" not in self.ACTIONS:
            self.available_nodes = [n for n in self.available_nodes if n not in allocated_nodes]

    def _allocate(self):
        allocated_pods = set()
        allocated_nodes = set()
        self.available_nodes = [x for x in self.available_nodes if len(x.pods) == 0]
        for p in self.pending_pods:
            log.info(f"Processing pod: {p}")
            for n in self.available_nodes:
                # TODO: should delete later, sanity condition
                if len(n.pods):
                    allocated_nodes.add(n)
                    continue
                if bind_pod_to_node(p.name, p.namespace, n.name):
                    allocated_pods.add(p)
                    allocated_nodes.add(n)
                    break
                else:
                    log.info("Try next node!")

        self._update_pod_and_nodes(allocated_nodes, allocated_pods)

    def _preempt(self):
        if not len(self.pending_pods):
            log.info("No pending pods, skip preempt action!")
        self.available_nodes.sort(key=lambda x: x.pods[0].priority if x.pods else -1)
        allocated_pods = set()
        allocated_nodes = set()
        for p in self.pending_pods:
            for n in self.available_nodes:
                if n.pods and n.pods[0].priority < p.priority:
                    if preempt_pod(n.pods[0]):
                        log.info(f"Preempted pod {n.pods[0].name}/{n.pods[0].namespace} for {p.name}/{p.namespace}")
                        n.reset_pods()
                        if bind_pod_to_node(p.name, p.namespace, n.name):
                            n.add_pod(p)
                            allocated_pods.add(p)
                            allocated_nodes.add(n)
                            break
                        else:
                            log.info("Preempted but not allocated!")
                    else:
                        log.info(f"Failed to Preempt pod {n.pods[0].name}/{n.pods[0].namespace} for {p.name}/{p.namespace}")

        self._update_pod_and_nodes(allocated_nodes, allocated_pods)




