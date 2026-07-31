from dataclasses import dataclass, field
from threading import Lock


@dataclass
class IOStats:
    latencies: list[float] = field(default_factory=list)
    bytes_written: int = 0
    failed_writes: int = 0
    timeouts: int = 0

    lock: Lock = field(default_factory=Lock)

    def add_latency(self, value):
        with self.lock:
            self.latencies.append(value)

    def add_bytes(self, value):
        with self.lock:
            self.bytes_written += value

    def add_failure(self):
        with self.lock:
            self.failed_writes += 1

