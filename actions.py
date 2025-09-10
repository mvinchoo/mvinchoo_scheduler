from collections import OrderedDict
from typing import List
from kubernetes import client, config
from models import PodSpec, NodeSpec
import logging
from collections import defaultdict
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

        free_nodes = [x for x in self.available_nodes if len(x.pods) == 0]

        groups = defaultdict(list)
        for p in self.pending_pods:
            groups[p.pod_group or f"__solo__:{p.name}"].append(p)

        sorted_groups = sorted(
            groups.items(),
            key=lambda kv: -max(p.priority for p in kv[1])
        )

        for group_name, pods in sorted_groups:
            log.info(f"Processing group: {group_name} with {len(pods)} pods")

            if len(pods) > len(free_nodes):
                log.info(f"Not enough nodes for group {group_name}, skipping")
                continue

            for p, n in zip(pods, free_nodes[:len(pods)]):
                if bind_pod_to_node(p.name, p.namespace, n.name):
                    allocated_pods.add(p)
                    allocated_nodes.add(n)
                    free_nodes.remove(n)
                    log.info(f"Bound pod {p.name} to node {n.name}")

        self._update_pod_and_nodes(allocated_nodes, allocated_pods)

    def _preempt(self):
        if not self.pending_pods:
            log.info("No pending pods, skip preempt action!")
            return

        allocated_pods = set()
        allocated_nodes = set()

        # --- Group pending pods (gang-aware) ---
        pending_groups = defaultdict(list)
        for p in self.pending_pods:
            pending_groups[p.pod_group or f"__solo__:{p.name}"].append(p)

        # Sort pending groups by descending priority
        sorted_pending_groups = sorted(
            pending_groups.items(),
            key=lambda kv: -max(p.priority for p in kv[1])
        )

        for group_name, pods in sorted_pending_groups:
            group_priority = max(p.priority for p in pods)
            needed = len(pods)
            log.info(f"Checking preemption for group {group_name} (prio={group_priority}, size={needed})")

            # --- Regroup currently running pods into their gangs ---
            running_groups = defaultdict(list)
            for n in self.available_nodes:
                if n.pods:
                    pod = n.pods[0]
                    running_groups[pod.pod_group or f"__solo__:{pod.name}"].append(n)

            # --- Candidate victim groups (lower priority only) ---
            victim_candidates = []
            for vg, nodes in running_groups.items():
                victim_priority = max(n.pods[0].priority for n in nodes)
                if victim_priority < group_priority:
                    victim_candidates.append((vg, victim_priority, nodes))

            # Sort victims by ascending priority (evict lowest first)
            victim_candidates.sort(key=lambda x: x[1])

            # --- Dry run: see if enough nodes could be freed ---
            candidate_nodes = []
            victim_groups_to_preempt = []
            for vg, vprio, nodes in victim_candidates:
                candidate_nodes.extend(nodes)
                victim_groups_to_preempt.append((vg, nodes))
                if len(candidate_nodes) >= needed:
                    break

            if len(candidate_nodes) < needed:
                log.info(f"Not enough nodes even with preemption for group {group_name}")
                continue

            # --- Actually preempt chosen victim groups ---
            freed_nodes = []
            preempt_success = True
            for vg, nodes in victim_groups_to_preempt:
                log.info(f"Preempting group {vg} (size={len(nodes)})")
                success = all(preempt_pod(n.pods[0]) for n in nodes)
                if not success:
                    preempt_success = False
                    log.info(f"Failed to preempt group {vg}, aborting scheduling for {group_name}")
                    break
                for n in nodes:
                    n.reset_pods()
                freed_nodes.extend(nodes)

            # --- If preemption succeeded, schedule this group ---
            if preempt_success and len(freed_nodes) >= needed:
                for p, n in zip(pods, freed_nodes[:needed]):
                    if bind_pod_to_node(p.name, p.namespace, n.name):
                        n.add_pod(p)
                        allocated_pods.add(p)
                        allocated_nodes.add(n)
                log.info(f"Scheduled group {group_name} after preemption")

        self._update_pod_and_nodes(allocated_nodes, allocated_pods)
