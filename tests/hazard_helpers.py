# finds - Copyright (c) 2026 Kirizaki


def hazard_worker(backend, results_queue):
    """Wrap UploadQuotaPool.run() with results collection"""
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


def gather_hazard_stats(results_queue):
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
        for key in ("accepted", "rejected", "used_mb", "quota_mb", "quota_violations"):
            stats[key] = last_result[key]

    return stats
