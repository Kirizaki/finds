# finds - Copyright (c) 2026 Kirizaki

import statistics
import time


def thread_contention_worker(backend, results_queue):
    """Wrap CounterBackend.run() with metrics"""
    try:
        start = time.perf_counter()
        totals = backend.run()
        elapsed = time.perf_counter() - start
        results_queue.put({
            "status": "success",
            "elapsed": elapsed,
            "totals": totals,
            "metrics": getattr(backend.thread_factory, "metrics", []),
        })
    except Exception as e:
        results_queue.put({
            "status": "error",
            "error": repr(e),
        })


def io_contention_worker(backend, results_queue):
    """Wrap StorageWriterPool.run() with metrics"""
    try:
        result = backend.run()
        results_queue.put({
            "status": "success",
            **result,
        })
    except Exception as e:
        results_queue.put({
            "status": "error",
            "error": repr(e),
        })


def cpu_contention_worker(backend, results_queue):
    """Wrap ComputeWorkerPool.run() with metrics"""
    try:
        result = backend.run()
        results_queue.put({
            "status": "success",
            **result,
        })
    except Exception as e:
        results_queue.put({
            "status": "error",
            "error": repr(e),
        })


def gather_thread_contention_stats(results_queue):
    stats = {
        "runs": 0,
        "errors": 0,
        "elapsed_times": [],
        "totals": {},
        "metrics": [],
    }

    while not results_queue.empty():
        result = results_queue.get()
        if result["status"] == "success":
            stats["runs"] += 1
            stats["elapsed_times"].append(result["elapsed"])
            stats["totals"] = result["totals"]
            stats["metrics"].extend(result.get("metrics", []))
        elif result["status"] == "error":
            stats["errors"] += 1

    if stats["elapsed_times"]:
        stats["median_elapsed"] = statistics.median(stats["elapsed_times"])

    return stats


def gather_io_contention_stats(results_queue):
    stats = {
        "runs": 0,
        "errors": 0,
    }
    last_result = None

    while not results_queue.empty():
        result = results_queue.get()
        if result["status"] == "success":
            stats["runs"] += 1
            last_result = result
        elif result["status"] == "error":
            stats["errors"] += 1

    if last_result:
        stats["elapsed"] = last_result["elapsed"]
        stats["bytes_written"] = last_result["bytes_written"]
        stats["write_p99_ms"] = last_result["write_p99_ms"]
        stats["throughput_mb_s"] = last_result["throughput_mb_s"]
        stats["queue_depth"] = last_result["queue_depth"]

    return stats


def gather_cpu_contention_stats(results_queue):
    stats = {
        "runs": 0,
        "errors": 0,
    }
    last_result = None

    while not results_queue.empty():
        result = results_queue.get()
        if result["status"] == "success":
            stats["runs"] += 1
            last_result = result
        elif result["status"] == "error":
            stats["errors"] += 1

    if last_result:
        for key in ("elapsed", "total_ops", "task_p50_ms", "task_p95_ms", "task_p99_ms",
                     "ops_per_sec", "queue_depth",
                     "cpu_time_sec", "context_switches"):
            stats[key] = last_result.get(key, 0)

    return stats

