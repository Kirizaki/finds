Fault Injection & Detection

Goal: inject realistic faults and reliably detect them with Pytest.

Faults:

1. Contentions:
- Thread contention -> hot locks / oversubscribed threads -> contention + latency
- I/O contention -> competing disk/network I/O -> throughput + latency
- CPU contention -> CPU starvation -> profiling + throughput
2. Hazards / Race Condition:
- Race / TOCTOU -> unsynchronized shared state -> stress + repeated runs
3. Deadlocks:
- Deadlock -> circular lock ordering -> timeout & circular-wait graph*

Requirements:

1. Toggleable: fixed - buggy
2. Reproducible, low-flakiness
3. Realistic + documented root cause/symptom
4. CI-friendly pass/fail
5. Regression detection with baselines/thresholds

Deliverables:

1. Fault implementations
2. Detection suite
4. README
3. CI integration
