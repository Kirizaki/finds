# finds - Copyright (c) 2026 Kirizaki

import threading
import time
from dataclasses import dataclass


@dataclass
class UploadStats:
    accepted: int = 0
    rejected: int = 0
    quota_violations: int = 0


class UploadQuota:
    """"""
    def __init__(self, quota_mb: int):
        self.quota_mb = quota_mb
        self.used_mb = 0

        # fixed path lock
        self.lock = threading.Lock()

    def upload_buggy(self, size_mb: int, stats: UploadStats):
        """
        TOCTOU bug: Check quota first, update usage later.

        Another thread can pass the same check before usage is updated.
        """
        if self.used_mb + size_mb <= self.quota_mb:
            # simulate upload time window where another request can race
            time.sleep(0.001)

            self.used_mb += size_mb
            stats.accepted += 1
            if self.used_mb > self.quota_mb:
                stats.quota_violations += 1
                # NOTE: we could also simulate ENOSPC
                # import errno
                # raise OSError(errno.ENOSPC, "No space left on device")
        else:
            stats.rejected += 1


    def upload_fixed(self, size_mb: int, stats: UploadStats):
        """
        Fixed: Check & reserve quota atomically by guarding the usage with lock.
        """

        with self.lock:
            if self.used_mb + size_mb <= self.quota_mb:
                self.used_mb += size_mb
                stats.accepted += 1
                # NOTE: Of course, here also simulate ENOSPC
                # if self.used_mb > self.quota_mb:
                    # import errno
                    # raise OSError(errno.ENOSPC, "No space left on device")
            else:
                stats.rejected += 1


def upload_worker(quota: UploadQuota, size_mb: int, buggy: bool, stats: UploadStats):
    if buggy:
        quota.upload_buggy(size_mb, stats)
    else:
        quota.upload_fixed(size_mb, stats)


def toctou_upload_quota_race(num_uploads: int = 100, upload_size_mb: int = 10,
                             quota_mb: int = 100, buggy: bool = False):
    """
    Simulate concurrent REST API uploads competing for shared tenant quota.

    Args: TBD
    """

    quota = UploadQuota(quota_mb)
    stats = UploadStats()

    threads = []

    for _ in range(num_uploads):
        t = threading.Thread(
            target=upload_worker,
            args=(
                quota,
                upload_size_mb,
                buggy,
                stats,
            )
        )
        threads.append(t)

    for t in threads:
        t.start()

    for t in threads:
        t.join()

    if quota.used_mb > quota.quota_mb:
        stats.quota_violations += 1

    return {
        "accepted": stats.accepted,
        "rejected": stats.rejected,
        "used_mb": quota.used_mb,
        "quota_mb": quota.quota_mb,
        "quota_violations": stats.quota_violations,
    }

