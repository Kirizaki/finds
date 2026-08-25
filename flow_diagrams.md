# Logical Flow Diagrams — `lab/`

Flow diagrams for each concurrency scenario in the **finds** lab, showing both the **buggy** and **fixed** code paths.

---

## 1. Module Dependency Overview

```mermaid
graph TD
    subgraph "lab/"
        DL["deadlocks.py"]
        CT["contentions.py"]
        HZ["hazards.py"]
        IO["io_stats.py"]
    end

    subgraph "lab/utils/"
        LF["locks.py"]
        TF["threads.py"]
    end

    DL -->|"lock_factory"| LF
    CT -->|"lock_factory, thread_factory"| LF
    CT -->|"thread_factory"| TF
    CT -->|"IOStats"| IO
    HZ -->|"thread_factory"| TF
    DL -.->|"injected at call-site"| TF
```

---

## 2. Deadlock — Circular Wait ([`deadlocks.py`](file:///Users/greg/Documents/finds/lab/deadlocks.py))

### UploadBackend: Buggy Path (Circular Wait → Deadlock)

```mermaid
flowchart TD
    A["Thread A: upload_request()"] --> A1["Acquire quota_lock"]
    A1 --> A2["_reserve_quota()"]
    A2 --> A3["Acquire metadata_lock ⏳"]

    B["Thread B: cleanup_worker(buggy=True)"] --> B1["Acquire metadata_lock"]
    B1 --> B2["_cleanup_metadata()"]
    B2 --> B3["Acquire quota_lock ⏳"]

    A3 -. "blocked — held by B" .-> B1
    B3 -. "blocked — held by A" .-> A1

    style A3 fill:#e74c3c,color:#fff
    style B3 fill:#e74c3c,color:#fff
```

> [!CAUTION]
> **Thread A** holds `quota_lock` and waits for `metadata_lock`; **Thread B** holds `metadata_lock` and waits for `quota_lock`. Neither can proceed — **deadlock**.

### UploadBackend: Fixed Path (Consistent Lock Ordering)

```mermaid
flowchart TD
    A["Thread A: upload_request()"] --> A1["Acquire quota_lock"]
    A1 --> A2["_reserve_quota()"]
    A2 --> A3["Acquire metadata_lock"]
    A3 --> A4["_update_metadata()"]
    A4 --> A5["Release metadata_lock"]
    A5 --> A6["Release quota_lock"]

    B["Thread B: cleanup_worker(buggy=False)"] --> B1["Acquire quota_lock"]
    B1 --> B2["_cleanup_metadata()"]
    B2 --> B3["Acquire metadata_lock"]
    B3 --> B4["_recalculate_quota()"]
    B4 --> B5["Release metadata_lock"]
    B5 --> B6["Release quota_lock"]

    style A6 fill:#27ae60,color:#fff
    style B6 fill:#27ae60,color:#fff
```

> [!TIP]
> Both paths acquire locks in the **same order** (`quota` → `metadata`), preventing circular wait.

---

## 3. Thread Contention — Hot-Lock ([`contentions.py`](file:///Users/greg/Documents/finds/lab/contentions.py) · `SharedCounter`)

### Buggy Path: Serialised Hot-Lock

```mermaid
flowchart TD
    R["SharedCounter.run()"] --> INIT["counters = [0] × num_buckets"]
    INIT --> MODE{buggy?}
    MODE -- Yes --> HL["_serialized_hot_lock()"]
    HL --> GL["Create global_lock"]
    GL --> SPAWN["Spawn N threads"]

    subgraph "Each Thread"
        W1["for i in increments_per_thread"] --> BUCKET["bucket = i % num_buckets"]
        BUCKET --> LOCK["acquire global_lock 🔒"]
        LOCK --> INC["counters#91;bucket#93; += 1"]
        INC --> UNLOCK["release global_lock"]
        UNLOCK --> W1
    end

    SPAWN --> W1
    W1 --> |"all joined"| RET["Return bucket totals"]

    style LOCK fill:#e74c3c,color:#fff
```

> [!WARNING]
> Every increment across all threads serialises on a **single global lock** — threads spend almost all time waiting, not working.

### Fixed Path: Private (Sharded) Counters

```mermaid
flowchart TD
    R["SharedCounter.run()"] --> INIT["counters = [0] × num_buckets"]
    INIT --> MODE{buggy?}
    MODE -- No --> PC["_private_counters()"]
    PC --> ALLOC["thread_counters = [None] × num_threads"]
    ALLOC --> SPAWN["Spawn N threads"]

    subgraph "Each Thread (tid)"
        LOCAL["local = [0] × num_buckets"] --> LOOP["for i in increments_per_thread"]
        LOOP --> BKT["bucket = i % num_buckets"]
        BKT --> LINC["local#91;bucket#93; += 1"]
        LINC --> LOOP
        LOOP --> |done| PUB["thread_counters#91;tid#93; = local"]
    end

    SPAWN --> LOCAL
    PUB --> |"all joined"| MERGE["Merge: counters#91;b#93; += local#91;b#93;"]
    MERGE --> RET["Return bucket totals"]

    style LOCAL fill:#27ae60,color:#fff
    style PUB fill:#27ae60,color:#fff
```

> [!TIP]
> Each thread works on **private counters** — zero lock contention during the hot loop. Results are merged once after all threads finish.

---

## 4. I/O Contention — Storage Writers ([`contentions.py`](file:///Users/greg/Documents/finds/lab/contentions.py) · `StorageWriterPool`)

### Overall Flow

```mermaid
flowchart TD
    R["StorageWriterPool.run()"] --> STATS["IOStats()"]
    STATS --> SEM["disk_sem = Semaphore(max_writers)"]
    SEM --> SPAWN["Spawn num_threads workers"]

    subgraph "Worker (worker_id)"
        MW["_make_worker()"] --> CHK{buggy?}
        CHK -- Yes --> DIRECT["_write() — no gate"]
        CHK -- No --> GATE["acquire disk_sem"]
        GATE --> WRITE["_write()"]
        WRITE --> REL["release disk_sem"]
    end

    SPAWN --> MW
    MW --> |"all joined"| RESULT["Return elapsed, bytes, p99, throughput, queue_depth"]

    style DIRECT fill:#e74c3c,color:#fff
    style GATE fill:#27ae60,color:#fff
```

### `_write()` Detail

```mermaid
flowchart TD
    START["_write(worker_id, stats)"] --> PATH["path = destination / file_{id}"]
    PATH --> STARTED["stats.writer_started()"]
    STARTED --> OPEN["open(path, 'wb', buffering=0)"]
    OPEN --> LOOP["for _ in file_size_mb"]
    LOOP --> RAND["data = os.urandom(block_size)"]
    RAND --> T0["start = perf_counter()"]
    T0 --> W["f.write(data)"]
    W --> FL["f.flush()"]
    FL --> FSYNC["os.fsync(f.fileno())"]
    FSYNC --> LAT["latency = perf_counter() - start"]
    LAT --> REC["stats.add_write_latency(latency)"]
    REC --> BYTES["stats.add_bytes(block_size)"]
    BYTES --> LOOP
    LOOP --> |done| FIN["stats.writer_finished()"]
```

> [!IMPORTANT]
> **Buggy**: All 64 writers hit the storage simultaneously → high queue depth, elevated p99 latency.
> **Fixed**: `Semaphore(max_writers=16)` gates writer concurrency, keeping queue depth within controller capacity.

---

## 5. CPU Contention — Compute Workers ([`contentions.py`](file:///Users/greg/Documents/finds/lab/contentions.py) · `ComputeWorkerPool`)

```mermaid
flowchart TD
    R["ComputeWorkerPool.run()"] --> BUF["buffer = os.urandom(buffer_size_mb)"]
    BUF --> SEM["cpu_sem = Semaphore(max_workers=cpu_count)"]
    SEM --> SNAP1["Snapshot ctx_switches & cpu_time"]
    SNAP1 --> SPAWN["Spawn num_threads → _bounded_worker"]

    subgraph "_bounded_worker()"
        BW{buggy?}
        BW -- Yes --> WDIRECT["_worker() — no gate"]
        BW -- No --> ACQS["acquire cpu_sem"]
        ACQS --> WGATED["_worker()"]
        WGATED --> RELS["release cpu_sem"]
    end

    subgraph "_worker()"
        TRACK["active_workers += 1, update peak"] --> LOOP["for _ in iterations"]
        LOOP --> HASH["hashlib.sha256(buffer).digest()"]
        HASH --> TIME["record latency (ms)"]
        TIME --> LOOP
        LOOP --> |done| PUBLISH["extend latencies list"]
        PUBLISH --> DEC["active_workers -= 1"]
    end

    SPAWN --> BW
    BW --> |"all joined"| SNAP2["Snapshot ctx_switches & cpu_time"]
    SNAP2 --> RESULT["Return elapsed, p50/p95/p99,\nops/sec, queue_depth,\ncpu_time, context_switches"]

    style WDIRECT fill:#e74c3c,color:#fff
    style ACQS fill:#27ae60,color:#fff
```

> [!IMPORTANT]
> **Buggy**: 64 threads all compete for `cpu_count` cores → involuntary context switches spike, per-op latency increases.
> **Fixed**: Semaphore limits active workers to `cpu_count`, minimising scheduler pressure and cache thrashing.

---

## 6. TOCTOU Race — Upload Quota ([`hazards.py`](file:///Users/greg/Documents/finds/lab/hazards.py))

### Buggy Path: Check-Then-Act Without Lock

```mermaid
flowchart TD
    UP["UploadQuota.upload(size_mb, stats)"] --> CHK{buggy?}
    CHK -- Yes --> TOCTOU["_upload_buggy()"]

    subgraph "_upload_buggy() — TOCTOU Race"
        CHECK["used_mb + size_mb <= quota_mb ?"]
        CHECK -- Yes --> SLEEP["sleep(0.001) ⚠️ race window"]
        SLEEP --> UPDATE["used_mb += size_mb"]
        UPDATE --> ACC["stats.accepted += 1"]
        CHECK -- No --> REJ["stats.rejected += 1"]
    end

    TOCTOU --> CHECK

    style SLEEP fill:#e74c3c,color:#fff
```

> [!CAUTION]
> Between the quota **check** and the **update**, other threads can pass the same check — quota is oversubscribed.

### Fixed Path: Atomic Check-and-Reserve

```mermaid
flowchart TD
    UP["UploadQuota.upload(size_mb, stats)"] --> CHK{buggy?}
    CHK -- No --> FIXED["_upload_fixed()"]

    subgraph "_upload_fixed() — Atomic"
        LOCK["acquire self.lock 🔒"] --> CHECK2["used_mb + size_mb <= quota_mb ?"]
        CHECK2 -- Yes --> UPD2["used_mb += size_mb\nstats.accepted += 1"]
        CHECK2 -- No --> REJ2["stats.rejected += 1"]
        UPD2 --> UNLOCK["release self.lock"]
        REJ2 --> UNLOCK
    end

    FIXED --> LOCK

    style LOCK fill:#27ae60,color:#fff
```

### UploadQuotaPool Orchestration

```mermaid
flowchart TD
    POOL["UploadQuotaPool.run()"] --> Q["UploadQuota(quota_mb, buggy)"]
    Q --> S["UploadStats()"]
    S --> SPAWN["Spawn num_uploads threads"]
    SPAWN --> |"each thread"| WORK["quota.upload(upload_size_mb, stats)"]
    WORK --> |"all joined"| VIOL{"used_mb > quota_mb ?"}
    VIOL -- Yes --> CALC["quota_violations = overflow // upload_size + 1"]
    VIOL -- No --> NONE["quota_violations = 0"]
    CALC --> RET["Return accepted, rejected,\nused_mb, quota_mb,\nquota_violations"]
    NONE --> RET
```

---

## 7. IOStats — Thread-Safe Statistics Collector ([`io_stats.py`](file:///Users/greg/Documents/finds/lab/io_stats.py))

```mermaid
flowchart TD
    subgraph "IOStats (all methods guarded by self.lock)"
        AWS["add_write_latency(lat)"] --> AWL["write_latencies.append(lat)"]
        AB["add_bytes(amount)"] --> ABU["bytes_written += amount\noperations += 1"]
        WS["writer_started()"] --> WSA["active_writers += 1\nmax_queue_depth = max(...)"]
        WF["writer_finished()"] --> WFA["active_writers -= 1"]
    end
```

---

## 8. Utility Factories ([`utils/`](file:///Users/greg/Documents/finds/lab/utils))

```mermaid
flowchart TD
    subgraph "locks.py — production_lock_factory(name)"
        LF_IN["name"] --> C1{"'counter'?"}
        C1 -- Yes --> TL["threading.Lock()"]
        C1 -- No --> C2{"'quota' | 'metadata'?"}
        C2 -- Yes --> ML["multiprocessing.Lock()"]
        C2 -- No --> ERR["raise NotImplementedError"]
    end

    subgraph "threads.py — production_thread_factory(target, args)"
        TF_IN["target, args"] --> TH["threading.Thread(target, args)"]
    end
```

> [!NOTE]
> Factories are injected into `SharedCounter`, `StorageWriterPool`, `ComputeWorkerPool`, and `UploadBackend`, enabling **test/instrumented locks and threads** to be swapped in without changing business logic.
