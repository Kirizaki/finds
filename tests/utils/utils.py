# finds - Copyright (c) 2026 Kirizaki

import threading
import multiprocessing as mp
import statistics


def start_and_join_workers(start_event: mp.Event, workers: list[threading.Thread | mp.Process]):
    # create all processes
    for r in workers:
        r.start()

    # release all workers together
    if start_event:
        start_event.set()

    # wait for completion
    for r in workers:
        r.join()


def get_percentile(values: list, percentile: int, normalize: int = 1):
    if not values:
        return 0
    return (statistics.quantiles(values, n=100)[percentile - 1] * normalize)

