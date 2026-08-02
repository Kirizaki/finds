# finds - Copyright (c) 2026 Kirizaki

import os
import time
import multiprocessing as mp


def test_lock_factory(name: str):
    return TimeoutLock(name)


class TimeoutExpired(Exception):
    pass

class TimeoutLock:
    """
    Lock wrapper with configurable acquisition timeout and debug tracing.

    Provides additional concurrency debugging information:
        - WAIT: when a process starts waiting for the lock
        - ACQUIRED: when the lock is acquired, including wait duration
        - RELEASE: when the lock is released

    Raises:
        TimeoutExpired:
            If the lock cannot be acquired within the configured timeout.
            This is useful for detecting potential deadlocks in tests where
            workers are expected to make progress within a bounded time.

    Notes:
        This class is intended ONLY for testing/fault-injection scenarios.
        Production code should use a regular lock implementation through the
        same lock factory interface without timeout instrumentation.
    """
    LOCK_TIMEOUT = float(os.getenv("LOCK_TIMEOUT", "120"))

    def __init__(self, name: str):
        self.name = name
        self._lock = mp.Lock()

    def acquire(self, *args, **kwargs):
        start = time.perf_counter()
        pid = os.getpid()

        print(f"[{pid}] WAIT {self.name}")

        kwargs["timeout"] = self.LOCK_TIMEOUT

        acquired = self._lock.acquire(*args, **kwargs)

        waited = time.perf_counter() - start

        if not acquired:
            print(f"[{pid}] LOCK_TIMEOUT {self.name} after {waited:.3f}s")
            raise TimeoutExpired(f"Timeout acquiring {self.name}")

        print(f"[{pid}] ACQUIRED {self.name} wait={waited:.6f}s")

        return True

    def release(self):
        self._lock.release()

        print(f"[{os.getpid()}] RELEASE {self.name}")

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()

