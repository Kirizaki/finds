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
    except TimeoutExpired as e:
        # cover suspected deadlocks (buggy)
        results_queue.put({
            "worker": worker_type,
            "status": "timeout",
            "waited_on": e.waited_on,
            "held_locks": e.held_locks,
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


def gather_stats(results_queue, quota_lock: InstrumentedMultiprocessingLock = None,
                 metadata_lock: InstrumentedMultiprocessingLock = None, contention_log: mp.Queue = None):
    stats = {
        "upload_completed": 0,
        "cleanup_completed": 0,
        "timeouts": 0,
        "upload_timeouts": 0,
        "cleanup_timeouts": 0,
        "errors": 0,
        # wait-for graph edges: list of (held_lock, waited_on) tuples
        "wait_for_edges": [],
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
                if result["worker"] == "upload":
                    stats["upload_timeouts"] += 1
                else:
                    stats["cleanup_timeouts"] += 1
                # records wait-for graph edges from timeout: held -> waited_on
                for held in result.get("held_locks", []):
                    stats["wait_for_edges"].append((held, result.get("waited_on")))
            elif result["status"] == "error":
                stats["errors"] += 1
        elif "lock_wait_latencies" in result:  # keep just for future benchmark
            if "quota" in result["lock_wait_latencies"]:
                stats["quota_lock_wait_latencies"].append(result["lock_wait_latencies"]["quota"])
            elif "metadata" in result["lock_wait_latencies"]:
                stats["metadata_lock_wait_latencies"].append(result["lock_wait_latencies"]["metadata"])
    # drain contention log: edges recorded at wait-time (before blocking)
    if contention_log is not None:
        while not contention_log.empty():
            stats["wait_for_edges"].append(contention_log.get_nowait())

    # keep just for future benchmark
    if quota_lock:
        stats["quota_lock_wait_p99_ms"] = get_percentile(stats["quota_lock_wait_latencies"], 99)
    if metadata_lock:
        stats["metadata_lock_wait_p99_ms"] = get_percentile(stats["metadata_lock_wait_latencies"], 99)

    return stats

