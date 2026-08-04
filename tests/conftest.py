# finds - Copyright (c) 2026 Kirizaki

import multiprocessing as mp
import os
import queue

import pytest

from lab.contentions import (
    ComputeWorkerPool,
    ComputeWorkerPoolConfig,
    SharedCounter,
    SharedCounterConfig,
    StorageWriterPool,
    StorageWriterPoolConfig,
    clean_artifacts,
)
from lab.deadlocks import UploadBackend
from lab.hazards import UploadQuotaPool, UploadQuotaPoolConfig
from lab.utils.locks import production_lock_factory
from lab.utils.threads import production_thread_factory
from tests.contention_helpers import (
    cpu_contention_worker,
    gather_cpu_contention_stats,
    gather_io_contention_stats,
    gather_thread_contention_stats,
    io_contention_worker,
    thread_contention_worker,
)
from tests.deadlock_helpers import build_tasks, gather_stats
from tests.hazard_helpers import gather_hazard_stats, hazard_worker
from tests.instrumentation.instrumented_locks import instrumented_lock_factory
from tests.instrumentation.instrumented_thread import InstrumentedThreadFactory
from tests.instrumentation.utils import start_and_join_workers

# shared helpers

def _run_contention(backend_factory, worker_fn, gather_fn, iterations=1):
    """
    Common runner base for contention runners:
    arrange: create queue, build backend per iteration
    act:     call worker_fn(backend, queue) each iteration
    gather:  drain queue via gather_fn return stats
    """
    results_queue = queue.Queue()
    for _ in range(iterations):
        worker_fn(backend_factory(), results_queue)
    return gather_fn(results_queue)

# CONTENTION RUNNERS

@pytest.fixture
def thread_contention_runner():
    def run(num_threads=8, increments_per_thread=5000, num_buckets=64, prod_mode=False, buggy=False, iterations=1):
        lock_factory = production_lock_factory if prod_mode else instrumented_lock_factory

        def make_backend():
            config = SharedCounterConfig(num_threads, increments_per_thread, num_buckets)
            if prod_mode:
                return SharedCounter(lock_factory, production_thread_factory, config, buggy=buggy)
            else:
                return SharedCounter(lock_factory, InstrumentedThreadFactory(), config, buggy=buggy)

        return _run_contention(make_backend, thread_contention_worker, gather_thread_contention_stats, iterations)

    return run

@pytest.fixture
def io_contention_runner(tmp_path):
    def run(num_threads=64, file_size_mb=1024, block_size=1024*1024, max_writers=16, prod_mode=False, buggy=False, iterations=1):
        destination = tmp_path / "io_artifacts"
        destination.mkdir(exist_ok=True)

        thread_factory = production_thread_factory if prod_mode else InstrumentedThreadFactory()

        def make_backend():
            config = StorageWriterPoolConfig(num_threads, file_size_mb, block_size, max_writers)
            clean_artifacts(destination)
            return StorageWriterPool(thread_factory, config, destination, buggy=buggy)

        stats = _run_contention(make_backend, io_contention_worker, gather_io_contention_stats, iterations)
        clean_artifacts(destination)
        return stats

    return run

@pytest.fixture
def cpu_contention_runner():
    def run(num_threads=64, iterations=5000, buffer_size_mb=8, max_workers=os.cpu_count(), prod_mode=False, buggy=False, iterations_count=1):
        thread_factory = production_thread_factory if prod_mode else InstrumentedThreadFactory()

        def make_backend():
            config = ComputeWorkerPoolConfig(num_threads, iterations, buffer_size_mb, max_workers)
            return ComputeWorkerPool(thread_factory, config, buggy=buggy)

        return _run_contention(make_backend, cpu_contention_worker, gather_cpu_contention_stats, iterations_count)

    return run

# HAZARD RUNNERS

@pytest.fixture
def hazard_runner():
    def run(num_uploads=100, upload_size_mb=10, quota_mb=100, prod_mode=False, buggy=False, iterations=1):
        thread_factory = production_thread_factory if prod_mode else InstrumentedThreadFactory()

        def make_backend():
            config = UploadQuotaPoolConfig(num_uploads, upload_size_mb, quota_mb)
            return UploadQuotaPool(thread_factory, config, buggy=buggy)

        return _run_contention(make_backend, hazard_worker, gather_hazard_stats, iterations)

    return run

# DEADLOCK RUNNERS

@pytest.fixture
def deadlock_runner():
    def run(tasks_num: int, prod_mode: bool = False, buggy: bool = False):
        # shared stats across all tasks (processes)
        results_queue = mp.Queue()

        # specified factory
        if prod_mode:
            factory = production_lock_factory
        else:
            factory = instrumented_lock_factory

        # production (stub) code to be tested
        backend = UploadBackend(lock_factory=factory,buggy=buggy)

        # tasks start barrier event
        start_event = mp.Event()

        # prepare all tasks
        tasks = build_tasks(tasks_num, start_event, "upload", backend.upload_request, results_queue)
        tasks += build_tasks(tasks_num, start_event, "cleanup", backend.cleanup_worker, results_queue)

        # run all tasks
        start_and_join_workers(start_event, tasks)

        # return gathered results with lock metrics when instrumented
        if not prod_mode:
            return gather_stats(results_queue,
                                quota_lock=backend.quota_lock,
                                metadata_lock=backend.metadata_lock)
        return gather_stats(results_queue)

    return run

