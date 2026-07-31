# finds - Copyright (c) 2026 Kirizaki
#
# TODO:
#   3. CPU contention - compute-bound tasks starving each other, poor scheduling, or cache thrashing.

import os
import threading
import time

from pathlib import Path

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

def writer(worker_id: int, file_size_mb: int, block_size: int, destination: Path):
    path = destination / f"file_{worker_id}"

    print(f"start {worker_id}")

    with open(path, "wb", buffering=0) as f:
        for i in range(file_size_mb):
            f.write(os.urandom(block_size))

            if i % 100 == 0:
                print(f"worker {worker_id}: {i} MB")

        print(f"fsync {worker_id}")
        os.fsync(f.fileno())

    print(f"done {worker_id}")


def spam(worker_id: int, file_size_mb: int, block_size: int, destination: Path, buggy: bool):
    if buggy:
        writer(worker_id, file_size_mb, block_size, destination)
    else:
        with disk_sem:
            writer(worker_id, file_size_mb, block_size, destination)


def io_contention_disk_spammer(
        destination: Path,
        num_threads: int = 8,
        file_size_mb: int = 1024,
        block_size: int = 1024 * 1024,  # 1 MB
        buggy: bool = False):
    """
    Generate heavy concurrent disk writes to create I/O contention.
    Example applications: multiple upload workers/processes/servers
                        writing large files to the same storage device.

    Args:
        buggy: If True, all workers write simultaneously, saturating
            the storage subsystem (queue depth, bandwidth, device latency).
            If False, concurrency is limited (e.g. semaphore/thread pool),
            reducing I/O contention while preserving throughput.

    Returns:
        Elapsed execution time.

    TODO: Could collect per-thread write latency, IOPS, throughput,
        queue depth, or block-layer statistics.

    NOTE: This is a simplified reproduction of storage contention.
          Real-world example would be multiple clients uploading
          large files to the same SSD/NAS and typical mitigation
          technique would be:
          - limiting concurrent writers (semaphore - as in example).
          - separating workloads onto different storage devices.
    """
    threads = []
    start = time.perf_counter()

    for i in range(num_threads):
        t = threading.Thread(
            target=spam,
            args=(i, file_size_mb, block_size, destination, buggy))
        threads.append(t)

    _start_and_join_threads(threads)
    elapsed = time.perf_counter() - start

    return elapsed


def clean_artifacts(destination: Path):
    for item in destination.iterdir():
        if item.is_file():
            item.unlink()

