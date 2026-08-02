# finds - Copyright (c) 2026 Kirizaki

import threading


class LockOrderValidator:
    """
    Detects lock acquisition order violations.

    Maintains a predefined global lock ordering and tracks locks acquired
    by each execution context.

    Example:
        Allowed:
            quota -> metadata

        Forbidden:
            metadata -> quota

    Raises:
        LockOrderViolation:
            When a lock is acquired in an order that can create a
            circular wait/deadlock.
    """

    def __init__(self, order):
        self.order = {
            name: index
            for index, name in enumerate(order)
        }

        self.local = threading.local()

    def acquire(self, lock_name):
        held = getattr(self.local, "held", [])

        if held:
            last_lock = held[-1]

            if self.order[lock_name] < self.order[last_lock]:
                raise LockOrderViolation(
                    f"Invalid lock order: "
                    f"{last_lock} -> {lock_name}"
                )

        held.append(lock_name)
        self.local.held = held

    def release(self, lock_name):
        held = self.local.held
        held.remove(lock_name)


class LockOrderViolation(Exception):
    pass

