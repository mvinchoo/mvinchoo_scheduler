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

Please run part1 before part2, grouped by test{number}

High level Example:


Please apply : test3.2_basic_pg_allocation_test_part1.yaml

Wait for pods to be running

Please apply : test3.1_basic_pg_allocation_test_part2.yaml

Use get pods after each apply to monitor

I did not get time to write good automated tests but these validate most logic 
