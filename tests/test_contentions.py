# finds - Copyright (c) 2026 Kirizaki

import os
import statistics

import pytest


@pytest.mark.contentions
def test_thread_contention_fixed_is_correct(thread_contention_runner):
    """
    Fixed path produces correct totals.
    """
    stats = thread_contention_runner(num_threads=8, increments_per_thread=50000, buggy=False, prod_mode=True)
    assert stats["errors"] == 0
    assert sum(stats["totals"].values()) == 8 * 50000

@pytest.mark.contentions
def test_thread_contention_buggy_is_correct(thread_contention_runner):
    """
    Buggy path should also produce correct totals.

    NOTE: The contention affects SPEED, not CORRECTNESS.
    """
    stats = thread_contention_runner(num_threads=8, increments_per_thread=50000, buggy=True, prod_mode=True)
    assert stats["errors"] == 0
    assert sum(stats["totals"].values()) == 8 * 50000

@pytest.mark.contentions
@pytest.mark.long
def test_thread_contention_buggy_is_slower(thread_contention_runner):
    """
    Buggy path should be slower then fixed due to contention.

    Repeat each measurement 10 times and compare medians to reduce noise.
    """
    fixed = thread_contention_runner(num_threads=8, increments_per_thread=50000, buggy=False, iterations=10, prod_mode=True)
    buggy = thread_contention_runner(num_threads=8, increments_per_thread=50000, buggy=True, iterations=10, prod_mode=True)

    fixed_median = fixed["median_elapsed"]
    buggy_median = buggy["median_elapsed"]
    ratio = buggy_median / fixed_median if fixed_median > 0 else float("inf")
    print(f"\n  Thread contention - fixed={fixed_median:.4f}s  "
          f"buggy={buggy_median:.4f}s  median ratio={ratio:.2f}x")
    assert ratio > 1.15, (f"Expected buggy path to be >1.15x slower, but got {ratio:.2f}")

@pytest.mark.contentions
def test_thread_contention_buggy_wait_dominates_active(thread_contention_runner):
    """
    Hot-lock proof: most of the threads' active time is spent
    waiting for the lock, not doing useful work.

    active_time includes lock acquisition (measured by measure_active),
    so wait_time is a subset of active_time. A high wait/active ratio
    proves serialisation: threads are blocked, not computing.
    Fixed path has zero wait (no shared lock).
    """
    num_threads = 8
    increments = 50000

    buggy = thread_contention_runner(num_threads=num_threads, increments_per_thread=increments, buggy=True)
    fixed = thread_contention_runner(num_threads=num_threads, increments_per_thread=increments, buggy=False)

    b_metrics = buggy["metrics"]
    f_metrics = fixed["metrics"]

    b_wait = sum(m.wait_time for m in b_metrics)
    b_active = sum(m.active_time for m in b_metrics)
    f_wait = sum(m.wait_time for m in f_metrics)
    wait_ratio = b_wait / b_active

    print(f"\n  buggy: wait={b_wait:.4f}s  active={b_active:.4f}s  wait/active={wait_ratio:.0%}")
    print(f"  fixed: wait={f_wait:.6f}s")

    # buggy: >80% of active time is lock wait, not computation
    assert wait_ratio > 0.80, (
        f"Expected >80% of active time to be lock wait, got {wait_ratio:.0%}")
    # fixed: no lock contention
    assert f_wait == 0

@pytest.mark.contentions
def test_thread_contention_lock_acquires_conservation(thread_contention_runner):
    """
    Every increment in the buggy path acquires the global lock exactly once.
    Fixed path uses no locks at all.
    NOTE: Can update in future if still use lock(s), but will expect lower lock acquires.
    """
    num_threads = 8
    increments = 5000

    buggy = thread_contention_runner(num_threads=num_threads, increments_per_thread=increments, buggy=True)
    fixed = thread_contention_runner(num_threads=num_threads, increments_per_thread=increments, buggy=False)

    b_acquires = sum(m.lock_acquires for m in buggy["metrics"])
    f_acquires = sum(m.lock_acquires for m in fixed["metrics"])

    expected = num_threads * increments
    assert b_acquires == expected, f"Expected {expected} lock acquires, got {b_acquires}"
    assert f_acquires == 0, f"Expected 0 lock acquires in fixed path, got {f_acquires}"

@pytest.mark.contentions
def test_thread_contention_buggy_p99_lock_wait(thread_contention_runner):
    """
    Hot-lock causes tail latency spikes visible at p99 (1% of users will experience this).
    Fixed path has no lock wait samples at all.

    p99 matters because in production systems a single slow lock
    acquire can cascade into retries, timeouts, and queue buildup (see: test_deadlocks.py for examples)
    """
    buggy = thread_contention_runner(num_threads=8, increments_per_thread=5000, buggy=True)
    fixed = thread_contention_runner(num_threads=8, increments_per_thread=5000, buggy=False)

    b_samples = [s for m in buggy["metrics"] for s in m.lock_wait_samples]
    f_samples = [s for m in fixed["metrics"] for s in m.lock_wait_samples]

    b_p99 = statistics.quantiles(b_samples, n=100)[98]
    print(f"\n  buggy p99 lock wait: {b_p99*1000:.3f}ms  ({len(b_samples)} samples)")

    assert b_p99 > 0, "Expected measurable p99 lock wait in buggy path"
    assert len(f_samples) == 0, f"Expected no lock wait samples in fixed path, got {len(f_samples)}"

@pytest.mark.contentions
def test_io_contention_fixed_is_correct(io_contention_runner):
    """
    Fixed path writes all expected bytes and bounds concurrency.
    """
    num_threads = 16
    file_size_mb = 2
    block_size = 1024 * 1024
    max_writers = 4

    stats = io_contention_runner(num_threads=num_threads, file_size_mb=file_size_mb,
                                 block_size=block_size, max_writers=max_writers,
                                 buggy=False, prod_mode=True)

    assert stats["errors"] == 0
    assert stats["bytes_written"] == num_threads * file_size_mb * block_size
    assert stats["queue_depth"] <= max_writers

@pytest.mark.contentions
def test_io_contention_buggy_is_correct(io_contention_runner):
    """
    Buggy path writes all expected bytes but cannot control concurrency.
    TODO: Could add test with threads barrier (start_event), to prove queue_depth > num_threads.
    NOTE: Like thread contention, the bug affects CONCURRENCY CONTROL, not CORRECTNESS of the data.
    """
    num_threads = 16
    file_size_mb = 2
    block_size = 1024 * 1024
    max_writers = 4

    stats = io_contention_runner(num_threads=num_threads, file_size_mb=file_size_mb,
                                 block_size=block_size, max_writers=max_writers,
                                 buggy=True, prod_mode=True)

    assert stats["errors"] == 0
    assert stats["bytes_written"] == num_threads * file_size_mb * block_size
    assert stats["queue_depth"] > max_writers

@pytest.mark.contentions
@pytest.mark.regression
def test_io_fixed_queue_depth_stays_bounded(io_contention_runner):
    """
    Regression: fixed path must never exceed max_writers concurrency.

    Previously, queue depth could match num_threads when the semaphore
    was accidentally bypassed. This guards against re-introducing
    unbounded writer concurrency in the fixed case.
    """
    num_threads = 16
    max_writers = 4

    stats = io_contention_runner(num_threads=num_threads, file_size_mb=2,
                                 block_size=1024 * 1024, max_writers=max_writers,
                                 buggy=False, prod_mode=True)

    assert stats["errors"] == 0
    assert stats["queue_depth"] <= max_writers
    assert stats["queue_depth"] > 0

@pytest.mark.contentions
@pytest.mark.long
def test_io_contention_buggy_p99_latency_tail_with_similar_throughput(io_contention_runner):
    fixed = io_contention_runner(num_threads=32, file_size_mb=8, max_writers=16, buggy=False, prod_mode=True)
    buggy = io_contention_runner(num_threads=32, file_size_mb=8, max_writers=16, buggy=True, prod_mode=True)

    print("\n  Fixed (bounded concurrency):\n"f"{fixed}")
    print("\n  Buggy (unbounded concurrency):\n"f"{buggy}")

    # verify bounded concurrency in fixed case
    assert fixed["queue_depth"] < buggy["queue_depth"]

    # fixed case should maintain reasonable throughput
    # NOTE: threshold is lower with small test sizes on fast storage
    #       where the semaphore overhead dominates over actual I/O contention.
    assert fixed["throughput_mb_s"] >= buggy["throughput_mb_s"] * 0.4

    # write p99 (tail latency):
    # - retries
    # - timeouts
    # - queues build
    # - systems cascade
    assert buggy["write_p99_ms"] > fixed["write_p99_ms"]

    # NOTE: as fsync depends heavily on fs, virtualization,
    #       storage backend, or runner environment,
    #       we should omit that, or apply based on specific infra.
    # assert buggy["fsync_p99_ms"] > fixed["fsync_p99_ms"]

@pytest.mark.contentions
def test_cpu_contention_fixed_is_correct(cpu_contention_runner):
    """
    Fixed path completes all operations and bounds concurrency.
    """
    num_threads = 16
    iterations = 100
    max_workers = 4

    stats = cpu_contention_runner(num_threads=num_threads, iterations=iterations,
                                  max_workers=max_workers,
                                  buggy=False, prod_mode=True)

    assert stats["errors"] == 0
    assert stats["total_ops"] == num_threads * iterations
    assert stats["queue_depth"] <= max_workers

@pytest.mark.contentions
def test_cpu_contention_buggy_is_correct(cpu_contention_runner):
    """
    Buggy path completes all operations but runs all workers simultaneously.

    NOTE: Like I/O contention, the bug affects CONCURRENCY CONTROL, not CORRECTNESS.
    """
    num_threads = 16
    iterations = 100

    stats = cpu_contention_runner(num_threads=num_threads, iterations=iterations,
                                  buggy=True, prod_mode=True)

    assert stats["errors"] == 0
    assert stats["total_ops"] == num_threads * iterations
    assert stats["queue_depth"] == num_threads

@pytest.mark.contentions
@pytest.mark.long
def test_cpu_contention_buggy_p99_latency_with_similar_throughput(cpu_contention_runner):
    num_threads = 64
    iterations = 5000
    max_workers = os.cpu_count()

    fixed = cpu_contention_runner(num_threads=num_threads, iterations=iterations,
                                  max_workers=max_workers, buggy=False, prod_mode=True)
    buggy = cpu_contention_runner(num_threads=num_threads, iterations=iterations,
                                  max_workers=max_workers, buggy=True, prod_mode=True)

    print("\n  Fixed (bounded CPU concurrency):\n"f"{fixed}")
    print("\n  Buggy (oversubscribed CPU):\n"f"{buggy}")

    # verify bounded concurrency in fixed case
    assert buggy["queue_depth"] > fixed["queue_depth"]

    # oversubscription should not provide meaningful throughput gain.
    throughput_ratio = (
        buggy["ops_per_sec"] /
        fixed["ops_per_sec"]
    )

    assert 0.85 <= throughput_ratio <= 1.15, (
        f"Unexpected throughput difference: "
        f"fixed={fixed['ops_per_sec']:.2f} ops/s "
        f"buggy={buggy['ops_per_sec']:.2f} ops/s"
    )

    # too many runnable threads cause scheduler pressure and cache thrashing
    assert buggy["task_p99_ms"] > (fixed["task_p99_ms"] * 10)

