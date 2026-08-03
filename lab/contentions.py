# finds - Copyright (c) 2026 Kirizaki

# 1. Thread contention: hot-lock serialisation bottleneck
# 2. i/o contention:    oversubscribed storage writers
# 3. cpu contention:    oversubscribed compute workeers

import os
import hashlib
import threading
import time
import psutil
import statistics
from pathlib import Path
from lab.io_stats import IOStats
from threading import Semaphore
from dataclasses import dataclass


###### thread contention ######

@dataclass
class SharedCounterConfig:
    num_threads: int = 8
    increments_per_thread: int = 5000
    num_buckets: int = 64


class SharedCounter:
    """
    Simulates shared counter service (ie. distributed databese writes).

    Buggy: single global lock serialises all threads (hot-lock)
    Fixed: each thread works on private counters, merged at end (sharding)

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
    def __init__(self, lock_factory, thread_factory, config: SharedCounterConfig, buggy: bool=False):
        self.lock_factory = lock_factory
        self.thread_factory = thread_factory
        self.config = config
        self.buggy: bool = buggy

    def run(self):
        """
        Increment shared counter from many threads.

        Returns bucket totals dict.
        """
        counters = [0] * self.config.num_buckets

        if self.buggy:
            return self._serialized_hot_lock(counters)
        else:
            return self._private_counters(counters)

    def _serialized_hot_lock(self, counters: list[int]):
        # one global lock - all threads serialise
        global_lock = self.lock_factory("counter")

        def _worker():
            for i in range(self.config.increments_per_thread):
                bucket = i % self.config.num_buckets
                with global_lock:
                    counters[bucket] += 1

        threads = [self.thread_factory(target=_worker) for t in range(self.config.num_threads)]
        SharedCounter.start_and_join_threads(threads)

        return {bucket: counters[bucket] for bucket in range(self.config.num_buckets)}

    def _private_counters(self, counters):
            # no shared state (thread has private counters, merged at end)
            thread_counters = [None] * self.config.num_threads

            def _worker(tid: int):
                local = [0] * self.config.num_buckets  # thread-private counters - no lock needed
                for i in range(self.config.increments_per_thread):
                    bucket = i % self.config.num_buckets
                    local[bucket] += 1
                thread_counters[tid] = local  # publish results for the merge phase

            threads = [self.thread_factory(target=_worker, args=(t,)) for t in range(self.config.num_threads)]
            SharedCounter.start_and_join_threads(threads)

            # merge pet-thread results
            for local in thread_counters:
                if local:
                    for b in range(self.config.num_buckets):
                        counters[b] += local[b]

            return {bucket: counters[bucket] for bucket in range(self.config.num_buckets)}

    @staticmethod
    def start_and_join_threads(threads):
        for t in threads:
            t.start()
        for t in threads:
            t.join()


###### I/O contention ######

@dataclass
class StorageWriterPoolConfig:
    num_threads: int = 64
    file_size_mb: int = 1024
    block_size: int = 1024 * 1024
    max_writers: int = 16


class StorageWriterPool:
    """
    Simulates concurrent storage writers (ie. upload workers writing to same storage).

    Buggy: all writers hit storage simultaneously, oversubscribing the storage
           subsystem and increasing queue depth and write latency.
    Fixed: writer concurrency is limited with a semaphore, keeping the number
           of concurrent writers within the storage controller's capacity.

    NOTE: This is a simplified reproduction of storage contention.
          Real-world examples include many clients uploading large
          files to the same SSD, NAS, RAID array or object storage.
    """
    def __init__(self, thread_factory, config: StorageWriterPoolConfig, destination: Path, buggy: bool = False):
        self.thread_factory = thread_factory
        self.config = config
        self.destination = destination
        self.buggy = buggy

    def run(self):
        stats = IOStats()
        disk_sem = Semaphore(self.config.max_writers)

        start = time.perf_counter()
        threads = [
            self.thread_factory(self._make_worker(i, stats, disk_sem))
            for i in range(self.config.num_threads)
        ]
        StorageWriterPool.start_and_join_threads(threads)
        elapsed = time.perf_counter() - start

        write_lat = stats.write_latencies

        return {
            "elapsed": elapsed,
            "bytes_written": stats.bytes_written,
            "write_p99_ms": StorageWriterPool._percentile(write_lat, 99) * 1000,
            "throughput_mb_s": stats.bytes_written / elapsed / (1024 * 1024),
            "queue_depth": stats.max_queue_depth,
        }

    def _make_worker(self, worker_id, stats, disk_sem):
        def _worker():
            if self.buggy:
                self._write(worker_id, stats)
            else:
                with disk_sem:
                    self._write(worker_id, stats)
        return _worker

    def _write(self, worker_id, stats):
        path = self.destination / f"file_{worker_id}"
        stats.writer_started()

        with open(path, "wb", buffering=0) as f:
            for _ in range(self.config.file_size_mb):
                data = os.urandom(self.config.block_size)
                # write & fsync latency is important for storage contention measurements
                # because it exposes end-to-end commit latency.
                # in NAS systems, contention can happen at the network layer,
                # filesystem layer, RAID/controller queues, storage tiers or disks.
                start = time.perf_counter()
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
                latency = time.perf_counter() - start
                stats.add_write_latency(latency)
                stats.add_bytes(self.config.block_size)

        stats.writer_finished()

    @staticmethod
    def start_and_join_threads(threads):
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    @staticmethod
    def _percentile(values, p):
        if not values:
            return 0
        return statistics.quantiles(values, n=100)[p - 1]


def clean_artifacts(destination: Path):
    for item in destination.iterdir():
        if item.is_file():
            item.unlink()

###### CPU contention ######

@dataclass
class ComputeWorkerPoolConfig:
    num_threads: int = 64
    iterations: int = 5000
    buffer_size_mb: int = 8
    max_workers: int = os.cpu_count()


class ComputeWorkerPool:
    """
    Simulates compute-bound workers (SHA-256 hashing) competing for CPU cores.

    Buggy: all workers execute simultaneously, oversubscribing CPU cores
           and increasing scheduler pressure and cache contention.
    Fixed: worker concurrency is limited with a semaphore, keeping the
           number of runnable tasks close to the available CPU cores.

    NOTE: This is a simplified reproduction of CPU contention.
          Real-world examples include image/video encoding,
          compression, encryption, checksum generation, or
          machine learning inference executed by many workers.
    """
    def __init__(self, thread_factory, config: ComputeWorkerPoolConfig, buggy: bool = False):
        self.thread_factory = thread_factory
        self.config = config
        self.buggy = buggy

    def run(self):
        buffer = os.urandom(self.config.buffer_size_mb * 1024 * 1024)
        cpu_sem = threading.Semaphore(self.config.max_workers)

        # thread-safe stats
        latencies = []
        latencies_lock = threading.Lock()
        active_workers = [0]
        peak_workers = [0]
        workers_lock = threading.Lock()

        process = psutil.Process()
        ctx_before = process.num_ctx_switches()
        cpu_time_before = process.cpu_times()

        def _worker():
            with workers_lock:
                active_workers[0] += 1
                peak_workers[0] = max(peak_workers[0], active_workers[0])

            local_latencies = []
            for _ in range(self.config.iterations):
                start = time.perf_counter()
                hashlib.sha256(buffer).digest()
                local_latencies.append((time.perf_counter() - start) * 1000)

            with latencies_lock:
                latencies.extend(local_latencies)

            with workers_lock:
                active_workers[0] -= 1

        def _bounded_worker():
            if self.buggy:
                _worker()
            else:
                with cpu_sem:
                    _worker()

        start = time.perf_counter()
        threads = [
            self.thread_factory(_bounded_worker)
            for _ in range(self.config.num_threads)
        ]
        ComputeWorkerPool.start_and_join_threads(threads)
        elapsed = time.perf_counter() - start

        ctx_after = process.num_ctx_switches()
        cpu_time_after = process.cpu_times()

        total_ops = self.config.num_threads * self.config.iterations

        context_switches = (
            (ctx_after.voluntary - ctx_before.voluntary)
            + (ctx_after.involuntary - ctx_before.involuntary)
        )
        cpu_time = (
            (cpu_time_after.user - cpu_time_before.user)
            + (cpu_time_after.system - cpu_time_before.system)
        )

        return {
            "elapsed": elapsed,
            "total_ops": total_ops,

            "task_p50_ms": statistics.median(latencies),
            "task_p95_ms": statistics.quantiles(latencies, n=100)[94],
            "task_p99_ms": statistics.quantiles(latencies, n=100)[98],

            "ops_per_sec": total_ops / elapsed,

            "queue_depth": peak_workers[0],

            "cpu_time_sec": cpu_time,
            "context_switches": context_switches,
        }

    @staticmethod
    def start_and_join_threads(threads):
        for t in threads:
            t.start()
        for t in threads:
            t.join()

