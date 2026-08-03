# finds - Copyright (c) 2026 Kirizaki

#   1. Classic circular-wait deadlocks (e.g., inconsistent lock ordering).

import time
import multiprocessing as mp


class UploadBackend:
    """
    Simulates REST upload backend shared resources:
        - quota_lock
        - metadata_lock

    Buggy (circular wait):
        - upload_request: quota -> metadata
        - cleanup_request: metadata -> quota

    Fixed (consistent order):
        - upload_request: quota -> metadata
        - cleanup_request: quota -> metadata
    """
    def __init__(self, lock_factory, buggy: bool = False):
        # dependency injection (production | instrumented/debug)
        self.metadata_lock = lock_factory("metadata")
        self.quota_lock = lock_factory("quota")
        self.buggy = buggy

    def upload_request(self, metadata, metadata_size):
        """
        Simulates POST /upload
        quota -> metadata
        """
        with self.quota_lock:
            self._reserve_quota(metadata)

            with self.metadata_lock:
                self._update_metadata(metadata_size)

    def _reserve_quota(self, _):
        # simulate quota reservation with metadata_size
        time.sleep(0.01)

    def _update_metadata(self, _):
        # simulate metadata upload
        time.sleep(0.03)

    def cleanup_worker(self, metadata, metadata_size):
        """
        Simulates background worker (ie. metadata update, quota recalc.)

        Args: buggy: if True:   lock metadata -> lock quota
                     otherwise: lock qouta -> lock metadata
        """
        if self.buggy:
             first = self.metadata_lock
             second = self.quota_lock
        else:
             first = self.quota_lock
             second = self.metadata_lock

        with first:
            self._cleanup_metadata(metadata)

            with second:
                self._recalculate_quota(metadata_size)

    def _cleanup_metadata(self, _):
        # simulate metadata update
        time.sleep(0.03)

    def _recalculate_quota(self, _):
        # simulate quota recalculation
        time.sleep(0.01)

