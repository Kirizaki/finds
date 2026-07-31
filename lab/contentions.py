# finds - Copyright (c) 2026 Kirizaki
#
# TODO:
#   3. CPU contention - compute-bound tasks starving each other, poor scheduling, or cache thrashing.

import os
import threading
import time
import statistics
from pathlib import Path
from tools.io_stats import IOStats
from threading import Lock, Semaphore, Thread

global_lock = threading.Lock()
MAX_WRITERS = 2
disk_sem = threading.Semaphore(MAX_WRITERS)

###### thread contention ######

def thread_contention_counter(
        num_threads: int = 8,
        increments_per_thread: int = 5000,
        buggy: bool = False) -> tuple[float, dict[int, int]]:
    """
    Increment a shared counter from many threads (hot-lock).
    Example applications: multiple threads/processes/servers
                          write to the same database.
    
    Args:
        buggy: If True, all threads contend on a single global lock.
               If False, each thread works on its own private counter
               (no lock contention at all), then the results are merged.

    Returns (elapsed time, bucket totals).

    TODO: Could add instrumented lock as arg, to ie. record acquire/release timestamps?

    NOTE: As this case is trivial, it shows real solution of solving hot-locks
          by 'sharding' the shared mutable. Other case of hot-locks would be
          a LRU (Least Recently Used) Cache, with 'fine-grained locking'.
          Long-story short, there are cases where we want to Cache frequently used
          data to avoid frequent heavy I/O actions.
          ie. scanning binary tree in RAID system (leafs can hold pointers to the same data)
          Buggy: Global lock for checking existance of leaf in cache & reading data
                 ie. leaf contains pointer to specific tier/disk/file, so we need to do heavy IO.
          Fixed: Global lock only to set placeholder - minimal contention,
                 and additional lock per leaf, for heavy IO.
    """

    num_buckets = 64
    counters = [0] * num_buckets  # shared mutable state across all threads

    if buggy:
        return thread_contention_buggy_case(num_buckets, counters, num_threads, increments_per_thread)
    else:
        return thread_contention_fixed_case(num_buckets, counters, num_threads, increments_per_thread)


def _start_and_join_threads(threads: threading.Thread):
    for t in threads:
        t.start()
    for t in threads:
        t.join()


def thread_contention_buggy_case(num_buckets: int, counters: int, num_threads: int, increments_per_thread: int):
    # one global lock - all threads serialise
    global_lock = threading.Lock()

    def _worker():
        for i in range(increments_per_thread):
            bucket = i % num_buckets
            with global_lock:
                counters[bucket] += 1
    
    start = time.perf_counter()
    threads = [threading.Thread(target=_worker) for t in range(num_threads)]
    _start_and_join_threads(threads)
    elapsed = time.perf_counter() - start

    totals = {b: counters[b] for b in range(num_buckets)}
    return elapsed, totals


def thread_contention_fixed_case(num_buckets: int, counters: int, num_threads: int, increments_per_thread: int):
        # no shared state (thread has private counters, merged at end)
        thread_counters = [None] * num_threads

        def _worker(tid: int):
            local = [0] * num_buckets  # thread-private counters - no lock needed
            for i in range(increments_per_thread):
                bucket = i % num_buckets
                local[bucket] += 1
            thread_counters[tid] = local  # publish results for the merge phase
        
        start = time.perf_counter()
        threads = [threading.Thread(target=_worker, args=(t,)) for t in range(num_threads)]
        _start_and_join_threads(threads)
        elapsed = time.perf_counter() - start

        # merge pet-thread results
        for local in thread_counters:
            if local:
                for b in range(num_buckets):
                    counters[b] += local[b]

        totals = {b: counters[b] for b in range(num_buckets)}
        return elapsed, totals


###### I/O contention ######

def writer(
    worker_id: int,
    file_size_mb: int,
    block_size: int,
    destination: Path,
    stats: IOStats
):
    path = destination / f"file_{worker_id}"
    stats.writer_started()

    try:
        with open(path, "wb", buffering=0) as f:
            for _ in range(file_size_mb):
                data = os.urandom(block_size)
                start = time.perf_counter()

                try:
                    f.write(data)
                    latency = time.perf_counter() - start
                    stats.add_write_latency(latency)
                    stats.add_bytes(block_size)
                except OSError:
                    stats.add_failure()

            # fsync is the important part for storage contention
            start = time.perf_counter()

            try:
                f.flush()
                os.fsync(f.fileno())
                latency = time.perf_counter() - start
                stats.add_fsync_latency(latency)
            except OSError:
                stats.add_failure()
    finally:
        stats.writer_finished()


def spam(
    worker_id: int,
    file_size_mb: int,
    block_size: int,
    destination: Path,
    buggy: bool,
    disk_sem: Semaphore,
    stats: IOStats
):
    if buggy:
        # all writers hit storage simultaneously
        writer(
            worker_id,
            file_size_mb,
            block_size,
            destination,
            stats
        )
    else:
        # controlled concurrency
        with disk_sem:
            writer(
                worker_id,
                file_size_mb,
                block_size,
                destination,
                stats
            )


def io_contention_disk_spammer(
    destination: Path,
    num_threads: int = 128,
    file_size_mb: int = 1024,
    block_size: int = 1024 * 1024,
    buggy: bool = False
):
    stats = IOStats()

    # simulate storage controller queue depth limit
    disk_sem = Semaphore(16)

    threads = []
    start = time.perf_counter()

    for i in range(num_threads):
        t = Thread(
            target=spam,
            args=(
                i,
                file_size_mb,
                block_size,
                destination,
                buggy,
                disk_sem,
                stats
            )
        )

        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    elapsed = time.perf_counter() - start

    write_lat = stats.write_latencies
    fsync_lat = stats.fsync_latencies

    def percentile(values, p):
        if not values:
            return 0

        return (
            statistics.quantiles(
                values,
                n=100
            )[p - 1]
        )


    return {
        "elapsed": elapsed,
        "write_lat": write_lat,
        "fsync_lat": fsync_lat,
        "write_p50_ms":
            statistics.median(write_lat) * 1000
            if write_lat else 0,
        "write_p95_ms":
            percentile(write_lat, 95) * 1000,
        "write_p99_ms":
            percentile(write_lat, 99) * 1000,
        "fsync_p50_ms":
            statistics.median(fsync_lat) * 1000
            if fsync_lat else 0,
        "fsync_p95_ms":
            percentile(fsync_lat, 95) * 1000,
        "fsync_p99_ms":
            percentile(fsync_lat, 99) * 1000,
        "iops":
            stats.operations / elapsed,
        "throughput_mb_s":
            stats.bytes_written /
            elapsed /
            (1024 * 1024),
        "queue_depth":
            stats.max_queue_depth,
        "failed_writes":
            stats.failed_writes,
        "timeouts":
            stats.timeouts,
    }


def clean_artifacts(destination: Path):
    for item in destination.iterdir():
        if item.is_file():
            item.unlink()

