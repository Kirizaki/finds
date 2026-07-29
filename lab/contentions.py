# finds - Copyright (c) 2026 Kirizaki
#
# TODO:
#   2. I/O contention - competing disk or network access causing throughput collapse or latency spikes.
#   3. CPU contention - compute-bound tasks starving each other, poor scheduling, or cache thrashing.

import threading
import time


def thread_contention_counter(
        num_threads: int = 8,
        increments_per_thread: int = 5000,
        buggy: bool = False) -> tuple[float, dict[int, int]]:
    """
    Increment a shared counter from many threads (hot-lock).
    Example applications: multiple threads/processes/servers
                          write to the same database.
    
    Args:
        buggy: If True, all threads contend on a single global lock.
               If False, each thread works on its own private counter
               (no lock contention at all), then the results are merged.

    Returns (elapsed time, bucket totals).

    NOTE: As this case is trivial, it shows real solution of solving hot-locks
          by 'sharding' the shared mutable. Other case of hot-locks would be
          a LRU (Least Recently Used) Cache, with 'fine-grained locking'.
          Long-story short, there are cases where we want to Cache frequently used
          data to avoid frequent heavy I/O actions.
          ie. scanning binary tree in RAID system (leafs can hold pointers to the same data)
          Buggy: Global lock for checking existance of leaf in cache & reading data
                 ie. leaf contains pointer to specific tier/disk/file, so we need to do heavy IO.
          Fixed: Global lock only to set placeholder - minimal contention,
                 and additional lock per leaf, for heavy IO.
    """

    num_buckets = 64
    counters = [0] * num_buckets  # shared mutable state across all threads

    if buggy:
        return buggy_case(num_buckets, counters, num_threads, increments_per_thread)
    else:
        return fixed_case(num_buckets, counters, num_threads, increments_per_thread)

def _start_and_join_threads(threads: threading.Thread):
    for t in threads:
        t.start()
    for t in threads:
        t.join()

def buggy_case(num_buckets: int, counters: int, num_threads: int, increments_per_thread: int):
    # one global lock - all threads serialise
    # TODO: Could pass as arg instrumented lock, to ie. record acquire/release timestamps?
    global_lock = threading.Lock()

    def _worker():
        for i in range(increments_per_thread):
            bucket = i % num_buckets
            with global_lock:
                counters[bucket] += 1
    
    start = time.perf_counter()
    threads = [threading.Thread(target=_worker) for t in range(num_threads)]
    _start_and_join_threads(threads)
    elapsed = time.perf_counter() - start

    totals = {b: counters[b] for b in range(num_buckets)}
    return elapsed, totals

def fixed_case(num_buckets: int, counters: int, num_threads: int, increments_per_thread: int):
        # no shared state (thread has private counters, merged at end)
        thread_counters = [None] * num_threads

        def _worker(tid: int):
            local = [0] * num_buckets  # thread-private counters - no lock needed
            for i in range(increments_per_thread):
                bucket = i % num_buckets
                local[bucket] += 1
            thread_counters[tid] = local  # publish results for the merge phase
        
        start = time.perf_counter()
        threads = [threading.Thread(target=_worker, args=(t,)) for t in range(num_threads)]
        _start_and_join_threads(threads)
        elapsed = time.perf_counter() - start

        # merge pet-thread results
        for local in thread_counters:
            if local:
                for b in range(num_buckets):
                    counters[b] += local[b]

        totals = {b: counters[b] for b in range(num_buckets)}
        return elapsed, totals

if __name__ == "__main__":
    elapsed, totals = thread_contention_counter(8, 50000, buggy=True)
    print(f"time elapsed: {elapsed} [s]")
    print(f"sum of count: {sum(totals.values())}")

    elapsed, totals = thread_contention_counter(8, 50000, buggy=False)
    print(f"time elapsed: {elapsed} [s]")
    print(f"sum of count: {sum(totals.values())}")

