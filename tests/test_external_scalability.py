# finds - Copyright (c) 2026 Kirizaki

"""
Scalability demonstration: apply the detection framework to code
that is NOT part of the lab stubs.

This simulates a third-party inventory reservation service with
the same classes of bugs (TOCTOU race, deadlock, contention) to
show the detectors generalise beyond the toy examples.
"""

import threading
import time
import multiprocessing as mp

import pytest

from tests.instrumentation.instrumented_locks import instrumented_lock_factory, TimeoutExpired
from tests.instrumentation.instrumented_thread import InstrumentedThreadFactory
from tests.instrumentation.utils import start_and_join_workers


# ---- mock external service: inventory reservation ----

class InventoryService:
    """
    Mock third-party inventory service with reservable stock.

    Buggy:  TOCTOU race on stock check (same pattern as UploadQuota,
            but different domain: e-commerce inventory).
    Fixed:  atomic check-and-reserve under lock.
    """
    def __init__(self, stock: int, buggy: bool = False):
        self.stock = stock
        self.buggy = buggy
        self.lock = threading.Lock()
        self.reserved = 0

    def reserve(self, quantity: int) -> bool:
        if self.buggy:
            return self._reserve_buggy(quantity)
        return self._reserve_fixed(quantity)

    def _reserve_buggy(self, quantity: int) -> bool:
        if self.stock >= quantity:
            time.sleep(0.001)  # TOCTOU window
            self.stock -= quantity
            self.reserved += quantity
            return True
        return False

    def _reserve_fixed(self, quantity: int) -> bool:
        with self.lock:
            if self.stock >= quantity:
                self.stock -= quantity
                self.reserved += quantity
                return True
            return False


class TransferService:
    """
    Mock third-party fund transfer service with two accounts.

    Buggy:  inconsistent lock ordering between debit and credit paths
            creates circular-wait deadlock.
    Fixed:  consistent lock ordering (always account_a then account_b).
    """
    def __init__(self, lock_factory, buggy: bool = False):
        self.account_a_lock = lock_factory("account_a")
        self.account_b_lock = lock_factory("account_b")
        self.buggy = buggy

    def transfer_a_to_b(self, amount):
        with self.account_a_lock:
            time.sleep(0.01)
            with self.account_b_lock:
                time.sleep(0.01)

    def transfer_b_to_a(self, amount):
        if self.buggy:
            # inconsistent order: b -> a (deadlock risk)
            first, second = self.account_b_lock, self.account_a_lock
        else:
            # consistent order: a -> b
            first, second = self.account_a_lock, self.account_b_lock

        with first:
            time.sleep(0.01)
            with second:
                time.sleep(0.01)


# ---- tests: TOCTOU on external inventory service ----

@pytest.mark.hazards
@pytest.mark.scalability
def test_external_inventory_toctou_detected():
    """
    Apply TOCTOU detector to a mock external inventory service.
    The detection pattern (oversubscription counting) works identically
    to the lab UploadQuota stub.
    """
    initial_stock = 100
    num_buyers = 200
    quantity_per_buyer = 1

    service = InventoryService(stock=initial_stock, buggy=True)
    thread_factory = InstrumentedThreadFactory()

    def buyer():
        service.reserve(quantity_per_buyer)

    threads = [thread_factory(target=buyer) for _ in range(num_buyers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # TOCTOU should cause overselling: more reserved than initial stock
    assert service.reserved > initial_stock, (
        f"Expected overselling but reserved={service.reserved} <= stock={initial_stock}")
    assert service.stock < 0, "Stock should go negative due to race"


@pytest.mark.hazards
@pytest.mark.scalability
def test_external_inventory_fixed_no_oversell():
    """
    Fixed inventory service never oversells, regardless of concurrency.
    """
    initial_stock = 100
    num_buyers = 200

    service = InventoryService(stock=initial_stock, buggy=False)
    thread_factory = InstrumentedThreadFactory()

    def buyer():
        service.reserve(1)

    threads = [thread_factory(target=buyer) for _ in range(num_buyers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert service.reserved <= initial_stock
    assert service.stock >= 0


# ---- tests: deadlock on external transfer service ----

def _mp_lock_factory(name: str):
    return instrumented_lock_factory(name.replace("account_a", "quota").replace("account_b", "metadata"))


@pytest.mark.deadlocks
@pytest.mark.scalability
def test_external_transfer_deadlock_detected(mocker):
    """
    Apply deadlock detector to a mock external fund transfer service.
    The timeout-based detection works identically to the lab UploadBackend stub.
    """
    from tests.instrumentation.instrumented_locks import InstrumentedLockBase
    mocker.patch.object(InstrumentedLockBase, "LOCK_TIMEOUT", 1.0)

    service = TransferService(lock_factory=_mp_lock_factory, buggy=True)
    results_queue = mp.Queue()
    start_event = mp.Event()

    def worker(direction, q):
        start_event.wait()
        try:
            if direction == "a_to_b":
                service.transfer_a_to_b(100)
            else:
                service.transfer_b_to_a(100)
            q.put({"status": "success", "direction": direction})
        except TimeoutExpired:
            q.put({"status": "timeout", "direction": direction})
        except Exception as e:
            q.put({"status": "error", "error": repr(e)})

    tasks_num = 30
    tasks = []
    for _ in range(tasks_num):
        tasks.append(mp.Process(target=worker, args=("a_to_b", results_queue)))
        tasks.append(mp.Process(target=worker, args=("b_to_a", results_queue)))

    start_and_join_workers(start_event, tasks)

    results = []
    while not results_queue.empty():
        results.append(results_queue.get())

    timeouts = sum(1 for r in results if r["status"] == "timeout")
    assert timeouts > 0, "Deadlock was not detected in external transfer service"


@pytest.mark.deadlocks
@pytest.mark.scalability
def test_external_transfer_fixed_no_deadlock(mocker):
    """
    Fixed transfer service completes all transfers without deadlock.
    """
    from tests.instrumentation.instrumented_locks import InstrumentedLockBase
    mocker.patch.object(InstrumentedLockBase, "LOCK_TIMEOUT", 5.0)

    service = TransferService(lock_factory=_mp_lock_factory, buggy=False)
    results_queue = mp.Queue()
    start_event = mp.Event()

    def worker(direction, q):
        start_event.wait()
        try:
            if direction == "a_to_b":
                service.transfer_a_to_b(100)
            else:
                service.transfer_b_to_a(100)
            q.put({"status": "success", "direction": direction})
        except TimeoutExpired:
            q.put({"status": "timeout", "direction": direction})

    tasks_num = 30
    tasks = []
    for _ in range(tasks_num):
        tasks.append(mp.Process(target=worker, args=("a_to_b", results_queue)))
        tasks.append(mp.Process(target=worker, args=("b_to_a", results_queue)))

    start_and_join_workers(start_event, tasks)

    results = []
    while not results_queue.empty():
        results.append(results_queue.get())

    timeouts = sum(1 for r in results if r["status"] == "timeout")
    assert timeouts == 0, f"Unexpected deadlock in fixed transfer service: {timeouts} timeouts"
    assert len(results) == tasks_num * 2
