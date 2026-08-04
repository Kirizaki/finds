# finds

`finds` (**F**ault **IN**jection & **D**etection **S**uite) is a pytest-based framework for injecting common concurrency and performance faults and reliably detecting them.

## Prerequisities

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Quick Start

```bash
# install deps (creates .venv automatically)
uv sync

# run all fast tests
uv run pytest

# run with verbose output (includes print diagnostics)
uv run pytest -s -v

# run specific fault class
uv run pytest -m contentions
uv run pytest -m deadlocks
uv run pytest -m hazards

# include long-running tests
uv run pytest -m "not stress"

# stress tests only
uv run pytest -m stress
```

## Toggling Faults

Every fault scenario exposes a `buggy` flag (constructor parameter or fixture argument). When `buggy=True` the fault is active; when `buggy=False` the fixed implementation runs.

Tests exercise both paths: the buggy path must exhibit the fault (detected by the test), and the fixed path must be correct and free of the fault.

```python
# example: toggle thread contention
stats = thread_contention_runner(buggy=True)   # hot-lock path
stats = thread_contention_runner(buggy=False)  # sharded-counter path

# example: toggle deadlock
stats = deadlock_runner(tasks_num=50, buggy=True)   # inconsistent lock order
stats = deadlock_runner(tasks_num=50, buggy=False)  # consistent lock order

# example: toggle TOCTOU race
stats = hazard_runner(buggy=True)   # check-then-act without lock
stats = hazard_runner(buggy=False)  # atomic check-and-reserve
```

Additionally, each runner accepts `prod_mode=True/False` to switch between production locks/threads and instrumented (debug) locks/threads.

## Structure

```
lab/                            # fault scenario stubs (Part 1)
  contentions.py                # thread, I/O, CPU contention
  deadlocks.py                  # circular-wait deadlock
  hazards.py                    # TOCTOU race condition
  io_stats.py                   # thread-safe I/O metrics collector
  utils/
    locks.py                    # production lock factory
    threads.py                  # production thread factory

tests/                          # detection suite (Part 2)
  conftest.py                   # runner fixtures (thread/IO/CPU/deadlock/hazard)
  test_contentions.py           # contention detection tests
  test_deadlocks.py             # deadlock detection tests
  test_hazards.py               # TOCTOU detection tests
  contention_helpers.py         # worker wrappers and stats gatherers
  deadlock_helpers.py           # deadlock worker wrappers and stats
  hazard_helpers.py             # hazard worker wrappers and stats
  instrumentation/
    instrumented_locks.py       # lock wrappers with timeout + metrics
    instrumented_thread.py      # thread wrapper with timing metrics
    thread_metrics.py           # per-thread metrics dataclass
    utils.py                    # shared helpers (start_and_join, percentile)

conftest.py                     # root: pytest summary report hook
pyproject.toml                  # project config (deps, pytest, ruff)
uv.lock                         # planned dependency lockfile

.github/workflows/              # CI pipelines
  pr_tests.yml                  # PR gate (fast tests only)
  nightly_tests.yml             # nightly (all except stress)
  stress_tests.yml              # weekend stress runs
  full_scope_tests.yml          # manual full-scope trigger
```

## Fault Scenarios and Detection Methods

| Fault Class | Scenario | Root Cause | Expected Symptom | Detection Method |
|---|---|---|---|---|
| **Thread contention** | `SharedCounter` hot-lock | Single global lock serialises all threads | High lock-wait ratio, degraded throughput | Lock-wait/active ratio > 80%, lock-acquire counting, p99 tail-latency analysis, median elapsed comparison |
| **I/O contention** | `StorageWriterPool` unbounded writers | No concurrency limit on storage writers | Queue depth explosion, p99 write latency spikes | Queue-depth bounds check, p99 write latency comparison, throughput ratio validation |
| **CPU contention** | `ComputeWorkerPool` oversubscription | More runnable threads than CPU cores | Scheduler pressure, cache thrashing, p99 latency spikes | Queue-depth validation, p99 task latency comparison (> 10x), context-switch counting |
| **Deadlock** | `UploadBackend` circular-wait | Inconsistent lock ordering (quota->metadata vs metadata->quota) | Processes hang, timeout after deadline | Timeout-based deadlock detection via instrumented locks, task-completion conservation law |
| **TOCTOU race** | `UploadQuota` check-then-act | Non-atomic check and update of shared quota | Quota oversubscription, extra uploads accepted | Quota-violation counting, formula verification, stress reproducibility (50 rounds x 1000 uploads) |

## Result Interpretation

After each test run, a **Fault Detection Summary** is printed showing per-fault-class pass/fail counts and timings:

```
====== Fault Detection Summary ======
  [PASS] Resource Contention (thread / I/O / CPU): 10/10 passed  (12.34s)
  [PASS] Deadlocks (circular-wait): 5/5 passed  (3.21s)
  [PASS] Hazards / Race Conditions (TOCTOU): 4/4 passed  (1.56s)

  Total: 19 passed, 0 failed  (17.11s)
  All fault scenarios detected reliably.
```

- **PASS** means detection is reliable: both the buggy path exhibits the fault and the fixed path is clean.
- **FAIL** indicates flaky or broken detection - review the specific test for environmental sensitivity.

### HTML Dashboard

An interactive HTML report is generated automatically at `results/report.html` after every test run (via `pytest-html`). It includes:

- **Fault Detection Summary** table at the top (pass/fail per fault class with timings)
- **Fault Class** and **Duration** columns for each test row (sortable)
- Full test output, captured logs, and environment metadata

To view it locally after a test run:
```bash
uv run pytest                          # generates results/report.html
open results/report.html               # macOS
xdg-open results/report.html           # Linux
start results\report.html              # Windows
```

CI workflows upload both JUnit XML and the HTML report as downloadable artifacts.

## CI Integration

| Workflow | Trigger | Scope | Marker filter |
|---|---|---|---|
| `pr_tests.yml` | Pull request | Fast tests only | `not stress and not long` |
| `nightly_tests.yml` | Daily 18:00 UTC | All except stress | `not stress` |
| `stress_tests.yml` | Friday 22:00 UTC | Stress tests | `stress` |
| `full_scope_tests.yml` | Manual dispatch | Everything | (none) |
