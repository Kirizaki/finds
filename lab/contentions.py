# finds - Copyright (c) 2026 Kirizaki

import os
import hashlib
import threading
import time
import psutil
import statistics
from pathlib import Path
from tools.io_stats import IOStats
from threading import Semaphore, Thread

global_lock = threading.Lock()

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

MAX_WRITERS = 2
disk_sem = threading.Semaphore(MAX_WRITERS)

def writer(worker_id: int, file_size_mb: int, block_size: int, destination: Path, stats: IOStats):
    path = destination / f"file_{worker_id}"
    stats.writer_started()

    with open(path, "wb", buffering=0) as f:
        for _ in range(file_size_mb):
            data = os.urandom(block_size)
            # write & fsync latency is important for storage contention measurements
            # because it exposes end-to-end commit latency.
            # in NAS systems, contention can happen at the network layer,
            # filesystem layer, RAID/controller queues, storage tiers or disks.
            start = time.perf_counter()
            f.write(data)
            latency = time.perf_counter() - start
            stats.add_write_latency(latency)
            stats.add_bytes(block_size)
            f.flush()
            os.fsync(f.fileno())

        stats.writer_finished()


def spam(worker_id: int, file_size_mb: int, block_size: int, destination: Path,
         buggy: bool, disk_sem: Semaphore, stats: IOStats):
    if buggy:  # all writers hit storage simultaneously
        writer(worker_id, file_size_mb, block_size, destination, stats)
    else:  # controlled concurrency
        with disk_sem:
            writer(worker_id, file_size_mb, block_size, destination, stats)


def io_contention_disk_spammer(destination: Path, num_threads: int = 64, file_size_mb: int = 1024,
                               block_size: int = 1024 * 1024, buggy: bool = False):
    """
    Generate I/O contention using concurrent large-file writes.
    Example applications: multiple upload workers/processes/servers
                          writing large files to the same storage device/system.

    Args:
        buggy: If True, all workers write simultaneously,
               oversubscribing the storage subsystem and increasing
               queue depth and write latency.
               If False, worker concurrency is limited with a semaphore,
               keeping the number of concurrent writers within the
               "storage controller's capacity".

    Returns (elapsed time, write p99 latency, throughput,
            application queue depth).

    NOTE: This is a simplified reproduction of storage contention.
          Real-world examples include many clients uploading large
          files to the same SSD, NAS, RAID array or object storage.
          Buggy: Too many writers issue requests concurrently,
                 increasing storage queue depth and tail latency,
                 while overall throughput changes little.
          Fixed: Limit the number of concurrent writers to match
                 storage capacity (disk and/or network),
                 preserving throughput while significantly reducing latency.
    """
    stats = IOStats()

    # simulate storage controller queue depth limit
    disk_sem = Semaphore(16)

    threads = []
    start = time.perf_counter()

    for i in range(num_threads):
        t = Thread(target=spam, args=(i, file_size_mb, block_size, destination, buggy, disk_sem, stats))
        threads.append(t)

    _start_and_join_threads(threads)
    elapsed = time.perf_counter() - start

    write_lat = stats.write_latencies

    def percentile(values, p):
        if not values:
            return 0
        return (statistics.quantiles(values, n=100)[p - 1])

    return {
        "elapsed": elapsed,
        "write_p99_ms": percentile(write_lat, 99) * 1000,
        "throughput_mb_s": stats.bytes_written / elapsed / (1024 * 1024),
        "queue_depth": stats.max_queue_depth,
    }


def clean_artifacts(destination: Path):
    for item in destination.iterdir():
        if item.is_file():
            item.unlink()

###### CPU contention ######

# thread per cpu
cpu_sem = threading.Semaphore(os.cpu_count())
active_workers = 0
peak_workers = 0
workers_lock = threading.Lock()

def cpu_worker(buffer: bytes, iterations: int, metrics: dict):
    global active_workers, peak_workers

    with workers_lock:
        active_workers += 1
        peak_workers = max(peak_workers, active_workers)

    latencies = []

    for _ in range(iterations):
        start = time.perf_counter()
        # cpu job
        hashlib.sha256(buffer).digest()
        latency = (time.perf_counter() - start) * 1000
        latencies.append(latency)

    metrics["latencies"].extend(latencies)

    with workers_lock:
        active_workers -= 1


def spam_cpu(buffer: bytes, iterations: int, metrics: dict, buggy: bool):
    if buggy:
        # unlimited concurrency:
        # all workers compete for CPU time
        cpu_worker(buffer, iterations, metrics)
    else:
        # controlled concurrency:
        # avoid oversubscribing CPU cores
        with cpu_sem:
            cpu_worker(buffer, iterations, metrics)


def cpu_contention_hash_spammer(num_threads: int = 64, iterations: int = 5000, buffer_size_mb: int = 8, buggy: bool = False):
    """
    Generate CPU contention using compute-bound SHA-256 hashing.
    Example applications: cryptography, checksum generation,
                        compression, image/video processing.

    Args:
        buggy: If True, all workers execute simultaneously,
               oversubscribing CPU cores and increasing scheduler
               pressure and CPU cache contention.
               If False, worker concurrency is limited with a semaphore,
               keeping the number of runnable tasks close to the
               available CPU cores.

    Returns (elapsed time, latency percentiles, throughput,
            CPU utilization, context switches, queue depth).

    NOTE: This is a simplified reproduction of CPU contention.
          Real-world examples include image/video encoding,
          compression, encryption, checksum generation, or
          machine learning inference executed by many workers.
          Buggy: Too many CPU-bound tasks execute simultaneously,
                 causing excessive context switching, scheduler
                 overhead and cache thrashing.
          Fixed: Limit the number of concurrent CPU-bound workers
                 to approximately the number of available CPU cores,
                 preserving throughput while significantly reducing
                 tail latency and/or distribute the heavy-lifting
                 across distributed assets.
    """

    global peak_workers, active_workers

    peak_workers = 0
    active_workers = 0

    process = psutil.Process()

    cpu_before = psutil.cpu_percent(interval=None)

    ctx_before = process.num_ctx_switches()
    cpu_time_before = process.cpu_times()
    print(f"cpu_before: {cpu_before}")
    print(f"ctx_before: {ctx_before}")
    buffer = os.urandom(
        buffer_size_mb * 1024 * 1024
    )

    metrics = {
        "latencies": []
    }

    threads = []

    start = time.perf_counter()

    for _ in range(num_threads):
        t = threading.Thread( target=spam_cpu, args=(buffer, iterations, metrics, buggy))
        threads.append(t)

    _start_and_join_threads(threads)

    elapsed = time.perf_counter() - start

    cpu_after = psutil.cpu_percent(interval=None)

    ctx_after = process.num_ctx_switches()
    cpu_time_after = process.cpu_times()
    print(f"ctx_after: {ctx_after}")
    print(f"ctx_after: {ctx_after}")

    latencies = metrics["latencies"]

    context_switches = (
        (ctx_after.voluntary - ctx_before.voluntary)
        +
        (ctx_after.involuntary - ctx_before.involuntary)
    )

    cpu_time = (
        (cpu_time_after.user - cpu_time_before.user)
        +
        (cpu_time_after.system - cpu_time_before.system)
    )

    total_ops = num_threads * iterations

    return {
        "elapsed": elapsed,

        "task_p50_ms": statistics.median(latencies),
        "task_p95_ms": statistics.quantiles(
            latencies,
            n=100
        )[94],
        "task_p99_ms": statistics.quantiles(
            latencies,
            n=100
        )[98],

        "ops_per_sec": total_ops / elapsed,

        # application-level queue pressure
        "queue_depth": peak_workers,

        # CPU measurements
        "cpu_percent": cpu_after,
        "cpu_time_sec": cpu_time,

        # scheduler pressure
        "context_switches": context_switches,
    }

