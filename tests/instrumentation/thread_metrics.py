# finds - Copyright (c) 2026 Kirizaki

import time
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field

from tests.instrumentation.utils import get_percentile

# share by all threads - that's the WIN of threads vs Processes ;)
_thread_local = threading.local()


@dataclass
class ThreadMetrics:
    name: str
    started: float = 0
    finishedd: float = 0
    active_time: float = 0
    wait_time: float = 0
    sleep_time: float = 0
    lock_acquires: int = 0
    operations: int = 0
    lock_wait_samples: list[float] = field(default_factory=list)

    @property
    def runtime(self):
        return self.finishedd - self.started


def set_current_metrics(metrics: ThreadMetrics):
    _thread_local.metrics = metrics

def current_metrics() -> ThreadMetrics:
    return _thread_local.metrics

@contextmanager
def measure_active(metrics: ThreadMetrics):
    start = time.perf_counter()
    try:
        yield
    finally:
        metrics.active_time += time.perf_counter() - start


def gather_metrics(metrics: ThreadMetrics):
    return {
        "runtime": max(m.finishedd for m in metrics) - min(m.started for m in metrics),
        "active_time": sum(m.active_time for m in metrics),
        "wait_time": sum(m.wait_time for m in metrics),
        "operations": sum(m.operations for m in metrics),
        "lock_wait_p99": get_percentile([x for m in metrics for x in m.lock_wait_samples], 99),
    }

