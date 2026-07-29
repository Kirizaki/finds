# finds - Copyright (c) 2026 Kirizaki

from lab.contentions import thread_contention_counter


def test_thread_contention_fixed_is_correct():
    """
    Fixed path produces correct totals.
    """
    _, totals = thread_contention_counter(
        num_threads=8,
        increments_per_thread=5000,
        buggy=False
    )
    assert sum(totals.values()) == 8 * 5000

def test_thread_contention_buggy_is_correct():
    """
    Buggy path should also produce correct totals.
    
    NOTE: The contention affects SPEED, not CORRECTNESS.
    """
    _, totals = thread_contention_counter(
        num_threads=8,
        increments_per_thread=5000,
        buggy=True
    )
    assert sum(totals.values()) == 8 * 5000

