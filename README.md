# Cluster setup

minikube start --nodes 3 -p multinode-demo --driver=docker



# Scheduler setup

`docker build -t mvinchoo-scheduler:0.0.1 .`

`minikube image load -p multinode-demo mvinchoo-scheduler:0.0.41`

# Permissions Setup
Apply all the YAML files in `cluster_setup` folder

Apply `mvinchoo-scheduler-deployment.yaml` last after all permissions are setup

# Test folder

There are 4 test which try to cover all scenarios.
Test format test{number}_scenario_part{NUMBER}

Please run `part1` before `part2`, grouped by `test{number}` (please ignore values after decimal point)

High level Example:


Please apply : test3.2_basic_pg_allocation_test_part1.yaml

Wait for pods to be running

Please apply : test3.1_basic_pg_allocation_test_part2.yaml

Use get pods after each apply to monitor

I did not get time to write good automated tests but these validate most logic 



 # DETAILS
Pods are grouped by their pod_group annotation. If a pod has a group, it is always scheduled or preempted together with its group. Solo pods are treated as single-pod gangs.

When preemption happens:
- If a new workload can fit on the cluster with the existing free nodes, it’s scheduled normally.

- If not, the scheduler looks at the currently running gangs and checks if evicting lower-priority groups would free enough nodes.

`All or nothing guarantee`: The scheduler only preempts if the new workload can be placed in full. If it cannot fit, no preemption happens. *This avoids early preemption problems*.

`Whole gang eviction`: When preemption is triggered, the scheduler always preempts the entire gang, never individual pods inside it. *This preserves gang semantics (a group runs together or not at all)*.



> Extra point: implement appropriate scheduling retry mechanism. (If not enough time, just think and mention on README)


Current scheduler operates in sessions (inspired from OSS Volcano which we also use at LinkedIn)

After a scheduling cycle finishes, it will sleep for 5 seconds and start a new cycle. (sort of busy loop logic)

This handles retires however I would have loved to make improvements:

- There should be a background watcher which constantly watches pods and updates a central in memory DB.
- Then at each session start, we use a snapshot of this central DB.
- This will prevent expensive list operation and use K8s informer watcher setup

> Extra point: try improving the performance for a large scale cluster. (If not enough time, just think and mention on README)

We can go with multiple approaches for this but each have their own pros and cons:

Example 1: Multischeduler setup:

- We create 3 instances of schedulers via statefulSets.
- Each node is consistent-hashed to go to a specific scheduler.
- Every (podName/Namespaces) is consistent-hashed to go to a specific scheduler.
- This will 3x our speed in theory. (Will definitely be faster than current single instance)
- However in the real world, it will lead to node resource fragmentations.
- - There is room on scheduler-1's nodes but the pod is assigned to scheduler-3 and stuck in pending.
Happy to discuss, learn and share more of such examples / cases. 
