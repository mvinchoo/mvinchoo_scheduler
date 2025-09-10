from dataclasses import dataclass, field
import datetime
from typing import List


@dataclass(order=True)
class PodSpec:
    namespace: str
    name: str
    priority: int
    creation_timestamp: datetime
    pod_group: str = ""

    def __post_init__(self):
        self.sort_index = (-self.priority, self.creation_timestamp)

    def __hash__(self):
        return hash((self.namespace, self.name))

    def __eq__(self, other):
        if not isinstance(other, PodSpec):
            return NotImplemented
        return (self.namespace, self.name) == (other.namespace, other.name)


@dataclass
class NodeSpec:
    name: str
    pods: List[PodSpec] = field(default_factory=list)

    def add_pod(self, pod: PodSpec):
        self.pods.append(pod)

    def reset_pods(self):
        self.pods = []

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        if not isinstance(other, NodeSpec):
            return NotImplemented
        return self.name == other.name