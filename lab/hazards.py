# finds - Copyright (c) 2026 Kirizaki

import threading
import time
from dataclasses import dataclass


@dataclass
class UploadStats:
    accepted: int = 0
    rejected: int = 0
    quota_violations: int = 0


@dataclass
class UploadQuotaPoolConfig:
    num_uploads: int = 100
    upload_size_mb: int = 10
    quota_mb: int = 100


class UploadQuota:
    """
    Shared tenant quota enforcer.

    Buggy: TOCTOU race — check-then-act without atomicity.
    Fixed: check & reserve atomically under a lock.
    """
    def __init__(self, quota_mb: int, buggy: bool = False):
        self.quota_mb = quota_mb
        self.used_mb = 0
        self.buggy = buggy

        # fixed path lock
        self.lock = threading.Lock()

    def upload(self, size_mb: int, stats: UploadStats):
        if self.buggy:
            self._upload_buggy(size_mb, stats)
        else:
            self._upload_fixed(size_mb, stats)

    def _upload_buggy(self, size_mb: int, stats: UploadStats):
        """
        TOCTOU bug: Check quota first, update usage later.

        Another thread can pass the same check before usage is updated.
        """
        if self.used_mb + size_mb <= self.quota_mb:
            # simulate upload time window where another request can race
            time.sleep(0.001)

            self.used_mb += size_mb
            stats.accepted += 1
        else:
            stats.rejected += 1

    def _upload_fixed(self, size_mb: int, stats: UploadStats):
        """
        Fixed: Check & reserve quota atomically by guarding the usage with lock.
        """
        with self.lock:
            if self.used_mb + size_mb <= self.quota_mb:
                self.used_mb += size_mb
                stats.accepted += 1
            else:
                stats.rejected += 1


class UploadQuotaPool:
    """
    Simulates concurrent REST API uploads competing for shared tenant quota.

    Buggy: TOCTOU race allows multiple threads to pass the quota check
           before any of them updates usage, oversubscribing the quota.
    Fixed: quota check and reservation are atomic under a lock.

    NOTE: This is a simplified reproduction of a TOCTOU race condition.
          Real-world examples include cloud storage quota enforcement,
          rate limiting, and inventory reservation.
    """
    def __init__(self, thread_factory, config: UploadQuotaPoolConfig, buggy: bool = False):
        self.thread_factory = thread_factory
        self.config = config
        self.buggy = buggy

    def run(self):
        quota = UploadQuota(self.config.quota_mb, buggy=self.buggy)
        stats = UploadStats()

        threads = [
            self.thread_factory(self._make_worker(quota, stats))
            for _ in range(self.config.num_uploads)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # count quota violations post-run (single consistent check)
        if quota.used_mb > quota.quota_mb:
            stats.quota_violations = (quota.used_mb - quota.quota_mb) // self.config.upload_size_mb + 1

        return {
            "accepted": stats.accepted,
            "rejected": stats.rejected,
            "used_mb": quota.used_mb,
            "quota_mb": quota.quota_mb,
            "quota_violations": stats.quota_violations,
        }

    def _make_worker(self, quota, stats):
        def _worker():
            quota.upload(self.config.upload_size_mb, stats)
        return _worker

