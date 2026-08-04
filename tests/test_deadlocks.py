# finds - Copyright (c) 2026 Kirizaki

import os

import pytest


@pytest.mark.deadlocks
def test_deadlocks_wrong_order(deadlock_runner, mocker):
    mocker.patch.dict(os.environ, {"LOCK_TIMEOUT": "1.0"})
    tasks_num = 50
    stats = deadlock_runner(tasks_num=tasks_num, prod_mode=False, buggy=True)

    assert stats["upload_completed"] + stats["cleanup_completed"] < tasks_num * 2
    assert stats["timeouts"] > 0
    assert stats["errors"] == 0
    # check conservation of all tasks
    completed = (
        stats["upload_completed"]
        + stats["cleanup_completed"]
        + stats["timeouts"]
        + stats["errors"]
    )
    assert completed == tasks_num * 2

@pytest.mark.deadlocks
@pytest.mark.long
def test_deadlocks_wrong_order_default_timeout(deadlock_runner):
    tasks_num = 50
    stats = deadlock_runner(tasks_num=tasks_num, prod_mode=False, buggy=True)

    assert stats["upload_completed"] + stats["cleanup_completed"] < tasks_num * 2
    assert stats["timeouts"] > 0
    assert stats["errors"] == 0
    # check conservation of all tasks
    completed = (
        stats["upload_completed"]
        + stats["cleanup_completed"]
        + stats["timeouts"]
        + stats["errors"]
    )
    assert completed == tasks_num * 2

@pytest.mark.deadlocks
def test_deadlocks_wrong_order_debug_output(deadlock_runner, mocker):
    """
    Same as test_deadlocks_wrong_order but with verbose lock tracing
    and a diagnostic summary printed for debugging deadlock patterns.
    """
    mocker.patch.dict(os.environ, {"LOCK_TIMEOUT": "1.0"})
    tasks_num = 50
    stats = deadlock_runner(tasks_num=tasks_num, prod_mode=False, buggy=True)

    print("\n  Deadlock debug output:")
    print(f"    uploads completed:  {stats['upload_completed']}/{tasks_num}")
    print(f"    cleanups completed: {stats['cleanup_completed']}/{tasks_num}")
    print(f"    timeouts (deadlocks detected): {stats['timeouts']}")
    print(f"    errors: {stats['errors']}")
    print(f"    total tasks: {tasks_num * 2}")

    assert stats["upload_completed"] + stats["cleanup_completed"] < tasks_num * 2
    assert stats["timeouts"] > 0
    assert stats["errors"] == 0
    # check conservation of all tasks
    completed = (
        stats["upload_completed"]
        + stats["cleanup_completed"]
        + stats["timeouts"]
        + stats["errors"]
    )
    assert completed == tasks_num * 2

@pytest.mark.deadlocks
def test_deadlocks_circular_wait(deadlock_runner, mocker):
    """
    Prove that the buggy path produces a real circular-wait deadlock
    by detecting a cycle in the wait-for graph.
    
    Each timeoud-out process reports which lock it held and which lock
    it was waiting on. A circular wait exists when:
        - process A: held quota,        waited on metadata
        - process B: held metadata,     waited on quota

    Uses small batches (4 tasks) so both upload and cleanup worksers
    reach the nested-lock phase before contention overwhelms them.
    Multiple rounds accumulate edges until the cycle is found.
    """
    mocker.patch.dict(os.environ, {"LOCK_TIMEOUT": "1.0"})
    all_edges = set()

    for _ in range(10):
        stats = deadlock_runner(tasks_num=4, prod_mode=False, buggy=True)
        all_edges.update(stats["wait_for_edges"])

        has_cycle = any((b, a) in all_edges for a, b in all_edges)
        if has_cycle:
            break

    assert has_cycle, (
        f"No circular wait detected in wait-for graph after 10 rounds.\n"
        f"  edges: {all_edges}\n"
        f"  Expected both (quota, metadata) and (metadata, quota)."
    )
    assert stats["errors"] == 0

    # proof: print the cycle that proves deadlock:
    cycle_edges = sorted((a, b) for a, b in all_edges if (b, a) in all_edges)
    print("\n  Circular-wait deadlock proven via wait-for graph:")
    for a, b in sorted(all_edges):
        if (b, a) in all_edges:
            print(f"    process X: held {a:<10s} waited on {b}")
    print(f"    cycle: {cycle_edges[0][0]} -> {cycle_edges[0][1]} -> {cycle_edges[0][0]}")

@pytest.mark.deadlocks
@pytest.mark.parametrize("prod_mode", [True, False])
def test_deadlocks_fixed_completes_without_deadlock(deadlock_runner, prod_mode):
    tasks_num = 50
    stats = deadlock_runner(tasks_num=tasks_num, prod_mode=prod_mode)

    assert stats["upload_completed"] == tasks_num
    assert stats["cleanup_completed"] == tasks_num
    assert stats["timeouts"] == 0
    assert stats["errors"] == 0

@pytest.mark.deadlocks
@pytest.mark.scalability
@pytest.mark.stress
@pytest.mark.long
@pytest.mark.parametrize("tasks_num", [10, 50, 200, 500])
def test_deadlocks_fixed_scales_without_deadlock(deadlock_runner, tasks_num):
    """
    Scalability: fixed lock ordering stays deadlock-free as task count grows.

    Increasing concurrent upload + cleanup pairs raises the probability
    of lock acquisition overlap. The fixed path must complete all tasks
    with zero timeouts at every scale - well... wide scale, but not every. :)"""
    stats = deadlock_runner(tasks_num=tasks_num, prod_mode=True)

    assert stats["upload_completed"] == tasks_num
    assert stats["cleanup_completed"] == tasks_num
    assert stats["timeouts"] == 0
    assert stats["errors"] == 0

@pytest.mark.deadlocks
def test_deadlocks_fixed_completes_without_deadlock_prod_lock(deadlock_runner):
    tasks_num = 50
    stats = deadlock_runner(tasks_num=tasks_num, prod_mode=True)

    assert stats["upload_completed"] == tasks_num
    assert stats["cleanup_completed"] == tasks_num
    assert stats["timeouts"] == 0
    assert stats["errors"] == 0


@pytest.mark.deadlocks
@pytest.mark.stress
@pytest.mark.long
def test_deadlocks_fixed_completes_without_deadlock_stress(deadlock_runner):
    tasks_num = 500
    stats = deadlock_runner(tasks_num=tasks_num, prod_mode=True)

    assert stats["upload_completed"] == tasks_num
    assert stats["cleanup_completed"] == tasks_num
    assert stats["timeouts"] == 0
    assert stats["errors"] == 0

@pytest.mark.deadlocks
@pytest.mark.regression
def test_deadlocks_fixed_lock_order_not_reverted(deadlock_runner):
    """
    Regression: consistent lock ordering must not be accidentally
    reverted to the buggy order. Previously, swapping the lock
    acquisition order in cleanup_worker reintroduced circular wait.

    This test runs the fixed path with enough concurrency to trigger
    the deadlock if lock ordering regresses, verifying zero timeouts
    across multiple rounds.
    """
    for _ in range(5):
        stats = deadlock_runner(tasks_num=100, prod_mode=True, buggy=False)

        assert stats["upload_completed"] == 100
        assert stats["cleanup_completed"] == 100
        assert stats["timeouts"] == 0
        assert stats["errors"] == 0

@pytest.mark.deadlocks
@pytest.mark.regression
def test_deadlocks_buggy_always_detected(deadlock_runner, mocker):
    """
    Regression: the buggy path must always produce at least one
    timeout. If this test starts passing with zero timeouts, the
    fault injection or detection mechanism is broken.
    """
    mocker.patch.dict(os.environ, {"LOCK_TIMEOUT": "1.0"})
    for _ in range(3):
        stats = deadlock_runner(tasks_num=50, prod_mode=False, buggy=True)

        assert stats["timeouts"] > 0, "Deadlock was not detected - fault injection may be broken"
        assert stats["errors"] == 0

