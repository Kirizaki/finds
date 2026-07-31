# finds - Copyright (c) 2026 Kirizaki

import statistics

from pathlib import Path
from lab.contentions import thread_contention_counter, io_contention_disk_spammer, clean_artifacts


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

    for _ in range(10):
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

def test_io_contention_buggy_is_slower():
    """
    Buggy path should be slower then fixed due to contention.

    Repeate each measurement 3 times and compare medians to reduce noise.
    """
    fixed_times = []
    buggy_times = []

    destination = Path("./lab/artifacts/")
    destination.mkdir(exist_ok=True)

    for _ in range(3):
        fixed_time = io_contention_disk_spammer(
            destination=destination,
            num_threads=16,
            file_size_mb=1024,
            block_size=1024 * 1024,  # 1 MB
            buggy=False
        )
        fixed_times.append(fixed_time)
        clean_artifacts(destination)

        buggy_time  = io_contention_disk_spammer(
            destination=destination,
            num_threads=16,
            file_size_mb=1024,
            block_size=1024 * 1024,  # 1 MB
            buggy=True
        )
        buggy_times.append(buggy_time)
        clean_artifacts(destination)
    
    fixed_median = statistics.median(fixed_times)
    buggy_median = statistics.median(buggy_times)
    ratio = buggy_median / fixed_median if fixed_median > 0 else float("inf")
    print(f"\n  I/O contention - fixed={fixed_median:.4f}s  "
          f"buggy={buggy_median:.4f}s  median ratio={ratio:.2f}x")
    assert ratio > 6.0, (f"Expected buggy path to be >1.15x slower, but got {ratio:.2f}")

def test_io_contention_buggy_has_higher_median_file_latency():
    fixed = []
    buggy = []

    for _ in range(3):
        fixed.extend(io_contention_disk_spammer(..., buggy=False))
        buggy.extend(io_contention_disk_spammer(..., buggy=True))

    fixed_median = statistics.median(fixed)
    buggy_median = statistics.median(buggy)

    print(f"fixed={fixed_median:.3f}s  buggy={buggy_median:.3f}s")

    assert buggy_median > fixed_median * 1.15

def test_io_contention_buggy_has_higher_iowait():
    import psutil
    import threading
    import time

    fixed_iowait = []
    buggy_iowait = []

    def monitor(samples):
        while True:
            samples.append(psutil.cpu_times_percent(interval=0.1).iowait)

    for buggy, samples in [(False, fixed_iowait), (True, buggy_iowait)]:
        monitor_thread = threading.Thread(
            target=monitor,
            args=(samples,),
            daemon=True
        )
        monitor_thread.start()

        io_contention_disk_spammer(
            destination=Path("./lab/artifacts/"),
            num_threads=16,
            file_size_mb=1024,
            block_size=1024 * 1024,
            buggy=buggy
        )

        time.sleep(0.2)  # allow final sample

    fixed_avg = statistics.mean(fixed_iowait)
    buggy_avg = statistics.mean(buggy_iowait)

    print(
        f"iowait fixed={fixed_avg:.2f}% "
        f"buggy={buggy_avg:.2f}%"
    )

    assert buggy_avg > fixed_avg

def test_io_contention_buggy_has_lower_throughput():
    total_mb = 16 * 1024

    fixed = io_contention_disk_spammer(..., buggy=False)
    buggy = io_contention_disk_spammer(..., buggy=True)

    fixed_tp = total_mb / fixed
    buggy_tp = total_mb / buggy

    print(
        f"fixed={fixed_tp:.1f} MB/s "
        f"buggy={buggy_tp:.1f} MB/s"
    )

    assert buggy_tp < fixed_tp * 0.9

