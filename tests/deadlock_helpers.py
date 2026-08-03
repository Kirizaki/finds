# finds - Copyright (c) 2026 Kirizaki

import multiprocessing as mp

from tests.instrumentation.instrumented_locks import InstrumentedMultiprocessingLock, TimeoutExpired
from tests.instrumentation.utils import get_percentile


def backend_endpoint_wrapper(worker_type, target, results_queue):
    """Wrap with metrics"""
    try:
        # TODO: Apply real TestClient with FastAPI in backend!
        target("mock_metadata", 123)
        results_queue.put({
            "worker": worker_type,
            "status": "success"
        })
    except TimeoutExpired:
        # cover suspected deadlocks (buggy)
        results_queue.put({
            "worker": worker_type,
            "status": "timeout"
        })
    except Exception as e:
        # cover any future regressions
        results_queue.put({
            "worker": worker_type,
            "status": "error",
            "error": repr(e)
        })


def synchronized_worker(start_event, worker_type, target, results_queue):
    """Simulate real-world workers burst"""
    start_event.wait()
    backend_endpoint_wrapper(worker_type, target, results_queue)


def build_tasks(num_tasks, start_event, type, target, results_queue):
    return [
        mp.Process(target=synchronized_worker,
                                args=(start_event, type, target, results_queue))
        for _ in range(num_tasks)
        ]


def gather_stats(results_queue, quota_lock: InstrumentedMultiprocessingLock = None, metadata_lock: InstrumentedMultiprocessingLock = None):
    stats = {
        "upload_completed": 0,
        "cleanup_completed": 0,
        "timeouts": 0,
        "errors": 0,
        "quota_lock_wait_latencies": [],
        "metadata_lock_wait_latencies": [],
        "quota_lock_wait_p99_ms": 0,
        "metadata_lock_wait_p99_ms": 0,
    }

    while not results_queue.empty():
        result = results_queue.get()

        if "status" in result:
            if result["status"] == "success":
                if result["worker"] == "upload":
                    stats["upload_completed"] += 1
                else:
                    stats["cleanup_completed"] += 1
            elif result["status"] == "timeout":
                stats["timeouts"] += 1
            elif result["status"] == "error":
                stats["errors"] += 1
        elif "lock_wait_latencies" in result:  # keep just for future benchmark
            if "quota" in result["lock_wait_latencies"]:
                stats["quota_lock_wait_latencies"].append(result["lock_wait_latencies"]["quota"])
            elif "metadata" in result["lock_wait_latencies"]:
                stats["metadata_lock_wait_latencies"].append(result["lock_wait_latencies"]["metadata"])

    # keep just for future benchmark
    if quota_lock:
        stats["quota_lock_wait_p99_ms"] = get_percentile(stats["quota_lock_wait_latencies"], 99)
    if metadata_lock:
        stats["metadata_lock_wait_p99_ms"] = get_percentile(stats["metadata_lock_wait_latencies"], 99)

    return stats

