# finds - Copyright (c) 2026 Kirizaki

import multiprocessing as mp
import os
import threading
import time

from tests.instrumentation.thread_metrics import current_metrics


def instrumented_lock_factory(name: str):
    if name == "counter":
        return InstrumentedThreadLock(name)
    elif name in ["quota", "metadata"]:
        return InstrumentedMultiprocessingLock(name)

    raise NotImplementedError("Not yet :(")


class TimeoutExpired(Exception):
    pass


class InstrumentedLockBase:
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
    LOCK_TIMEOUT: float = float(os.getenv("LOCK_TIMEOUT", "120"))
    # by default disabled due to spam
    LOCK_VERBOSE: bool = False

    def __init__(self, name: str, lock):
        self.name: str = name
        self._lock = lock

    def acquire(self, *args, **kwargs):
        start = time.perf_counter()
        if self.LOCK_VERBOSE:
            print(f"[{os.getpid()}] WAIT {self.name}")

        kwargs["timeout"] = self.LOCK_TIMEOUT
        acquired = self._lock.acquire(*args, **kwargs)

        waited = time.perf_counter() - start
        if not acquired:
            print(f"[{os.getpid()}] LOCK_TIMEOUT {self.name} after {waited:.3f}s")
            raise TimeoutExpired(f"Timeout acquiring {self.name}")

        if self.LOCK_VERBOSE:
            print(f"[{os.getpid()}] ACQUIRED {self.name} wait={waited:.6f}s")
        return True

    def release(self):
        if self.LOCK_VERBOSE:
            print(f"[{os.getpid()}] RELEASE {self.name}")
        self._lock.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()


class InstrumentedMultiprocessingLock(InstrumentedLockBase):
    def __init__(self, name):
        super().__init__(name, mp.Lock())

class InstrumentedThreadLock(InstrumentedLockBase):
    def __init__(self, name):
        super().__init__(name, threading.Lock())

    def acquire(self, *args, **kwargs):
        start = time.perf_counter()
        if self.LOCK_VERBOSE:
            print(f"[{os.getpid()}] WAIT {self.name}")

        kwargs["timeout"] = self.LOCK_TIMEOUT
        acquired = self._lock.acquire(*args, **kwargs)

        waited = time.perf_counter() - start
        metrics = current_metrics()
        metrics.wait_time += waited
        metrics.lock_wait_samples.append(waited)
        if not acquired:
            print(f"[{os.getpid()}] LOCK_TIMEOUT {self.name} after {waited:.3f}s")
            raise TimeoutExpired(f"Timeout acquiring {self.name}")

        metrics.lock_acquires += 1
        if self.LOCK_VERBOSE:
            print(f"[{os.getpid()}] ACQUIRED {self.name} wait={waited:.6f}s")
        return True

