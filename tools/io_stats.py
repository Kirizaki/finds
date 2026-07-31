from dataclasses import dataclass, field
from threading import Lock


@dataclass
class IOStats:
    write_latencies: list[float] = field(default_factory=list)
    fsync_latencies: list[float] = field(default_factory=list)

    bytes_written: int = 0
    operations: int = 0
    failed_writes: int = 0
    timeouts: int = 0

    active_writers: int = 0
    max_queue_depth: int = 0

    lock: Lock = field(default_factory=Lock)

    def add_write_latency(self, latency: float):
        with self.lock:
            self.write_latencies.append(latency)

    def add_fsync_latency(self, latency: float):
        with self.lock:
            self.fsync_latencies.append(latency)

    def add_bytes(self, amount: int):
        with self.lock:
            self.bytes_written += amount
            self.operations += 1

    def writer_started(self):
        with self.lock:
            self.active_writers += 1
            self.max_queue_depth = max(
                self.max_queue_depth,
                self.active_writers
            )

    def writer_finished(self):
        with self.lock:
            self.active_writers -= 1

    def add_failure(self):
        with self.lock:
            self.failed_writes += 1

