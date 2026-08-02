# finds - Copyright (c) 2026 Kirizaki

import pytest
import multiprocessing as mp


from lab.deadlocks import UploadBackend, production_lock_factory

from tests.utils.locks import test_lock_factory
from tests.utils.utils import start_and_join_workers
from tests.deadlock_helpers import build_tasks, gather_stats


@pytest.fixture
def deadlock_runner():
    def run(tasks_num: int, prod_lock_factory: bool = False, buggy: bool = False):
        # shared stats across all tasks (processes)
        results_queue = mp.Queue()

        # specified factory
        if prod_lock_factory:
            factory = production_lock_factory
        else:
            factory = test_lock_factory

        # production (stub) code to be tested
        backend = UploadBackend(lock_factory=factory,buggy=buggy)

        # tasks start barrier event
        start_event = mp.Event()

        # prepare all tasks
        tasks = build_tasks(tasks_num, start_event, "upload", backend.upload_request, results_queue)
        tasks += build_tasks(tasks_num, start_event, "cleanup", backend.cleanup_worker, results_queue)

        # run all tasks
        start_and_join_workers(start_event, tasks)

        # return gathered results
        return gather_stats(results_queue)

    return run

