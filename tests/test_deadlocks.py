# finds - Copyright (c) 2026 Kirizaki

import os
import pytest


@pytest.mark.deadlocks
@pytest.mark.negative
def test_deadlocks_wrong_order_test_lock(deadlock_runner, mocker):
    mocker.patch.dict(os.environ, {"LOCK_TIMEOUT": "1.0"})
    tasks_num = 50
    stats = deadlock_runner(tasks_num=tasks_num, buggy=True)

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
@pytest.mark.negative
@pytest.mark.long
def test_deadlocks_wrong_order_default_timeout_test_lock(deadlock_runner):
    tasks_num = 50
    stats = deadlock_runner(tasks_num=tasks_num, buggy=True)

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
@pytest.mark.parametrize("tasks_num", [10, 50, 100])
def test_deadlocks_fixed_completes_without_deadlock_test_lock(deadlock_runner, tasks_num):
    stats = deadlock_runner(tasks_num=tasks_num)

    assert stats["upload_completed"] == tasks_num
    assert stats["cleanup_completed"] == tasks_num
    assert stats["timeouts"] == 0
    assert stats["errors"] == 0


@pytest.mark.deadlocks
def test_deadlocks_fixed_completes_without_deadlock_prod_lock(deadlock_runner):
    tasks_num = 50
    stats = deadlock_runner(tasks_num=tasks_num, prod_lock_factory=True)

    assert stats["upload_completed"] == tasks_num
    assert stats["cleanup_completed"] == tasks_num
    assert stats["timeouts"] == 0
    assert stats["errors"] == 0


@pytest.mark.deadlocks
@pytest.mark.stress
@pytest.mark.long
def test_deadlocks_fixed_completes_without_deadlock_stress_test_lock(deadlock_runner):
    tasks_num = 500
    stats = deadlock_runner(tasks_num=tasks_num)

    assert stats["upload_completed"] == tasks_num
    assert stats["cleanup_completed"] == tasks_num
    assert stats["timeouts"] == 0
    assert stats["errors"] == 0

