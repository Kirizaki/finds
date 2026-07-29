# finds - Copyright (c) 2026 Kirizaki

import statistics

from lab.contentions import thread_contention_counter


def test_thread_contention_fixed_is_correct():
    """
    Fixed path produces correct totals.
    """
    _, totals = thread_contention_counter(
        num_threads=8,
        increments_per_thread=50000,
        buggy=False
    )
    assert sum(totals.values()) == 8 * 50000

def test_thread_contention_buggy_is_correct():
    """
    Buggy path should also produce correct totals.
    
    NOTE: The contention affects SPEED, not CORRECTNESS.
    """
    _, totals = thread_contention_counter(
        num_threads=8,
        increments_per_thread=50000,
        buggy=True
    )
    assert sum(totals.values()) == 8 * 50000

def test_thread_contention_buggy_is_slower():
    """
    Buggy path should be slower then fixed due to contention.

    Repeate each measurement 10 times and compare medians to reduce noise.
    """
    fixed_times = []
    buggy_times = []

    for _ in range(100):
        fixed_time, _ = thread_contention_counter(
            num_threads=8,
            increments_per_thread=50000,
            buggy=False
        )
        fixed_times.append(fixed_time)

        buggy_time, _ = thread_contention_counter(
            num_threads=8,
            increments_per_thread=50000,
            buggy=True
        )
        buggy_times.append(buggy_time)
    
    fixed_median = statistics.median(fixed_times)
    buggy_median = statistics.median(buggy_times)
    ratio = buggy_median / fixed_median if fixed_median > 0 else float("inf")
    print(f"\n  Thread contention - fixed={fixed_median:.4f}s  "
          f"buggy={buggy_median:.4f}s  median ratio={ratio:.2f}x")
    assert ratio > 1.15, (f"Expected buggy path to be >1.15x slower, but got {ratio:.2f}")

