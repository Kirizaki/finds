# finds - Copyright (c) 2026 Kirizaki

import threading
import time

from tests.instrumentation.thread_metrics import ThreadMetrics, set_current_metrics


class InstrumentedThreadFactory:
    def __init__(self):
        self.metrics = []

    def __call__(self, target, args=()):
        metrics = ThreadMetrics(name=f"worker-{len(self.metrics)}")
        self.metrics.append(metrics)

        return InstrumentedThread(target=target, args=args, metrics=metrics,)

    def reset(self):
        self.metrics.clear()


class InstrumentedThread(threading.Thread):
    def __init__(self, *args, metrics: ThreadMetrics, **kwargs):
        super().__init__(*args, **kwargs)
        self.metrics = metrics

    def run(self):
        set_current_metrics(self.metrics)
        self.metrics.started = time.perf_counter()
        try:
            super().run()
        finally:
            self.metrics.finishedd = time.perf_counter()
            self.metrics.active_time = self.metrics.finishedd - self.metrics.started

