# finds - Copyright (c) 2026 Kirizaki

# root conftest: pytest hooks (report summary, JUnit XML defaults)

import time
from collections import defaultdict

# ---- fault-detection result summary ----

_results = defaultdict(list)


def pytest_runtest_logreport(report):
    if report.when == "call":
        # extract fault class from markers
        fault_class = "other"
        for marker in ("contentions", "deadlocks", "hazards"):
            if marker in report.keywords:
                fault_class = marker
                break

        _results[fault_class].append({
            "name": report.nodeid.split("::")[-1],
            "outcome": report.outcome,
            "duration": report.duration,
        })


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    terminalreporter.section("Fault Detection Summary")

    fault_labels = {
        "contentions": "Resource Contention (thread / I/O / CPU)",
        "deadlocks": "Deadlocks (circular-wait)",
        "hazards": "Hazards / Race Conditions (TOCTOU)",
        "other": "Other",
    }

    total_passed = 0
    total_failed = 0
    total_time = 0.0

    for fault_class in ("contentions", "deadlocks", "hazards", "other"):
        items = _results.get(fault_class, [])
        if not items:
            continue

        label = fault_labels[fault_class]
        passed = sum(1 for i in items if i["outcome"] == "passed")
        failed = sum(1 for i in items if i["outcome"] == "failed")
        elapsed = sum(i["duration"] for i in items)

        total_passed += passed
        total_failed += failed
        total_time += elapsed

        status = "PASS" if failed == 0 else "FAIL"
        terminalreporter.write_line(
            f"  [{status}] {label}: {passed}/{len(items)} passed  ({elapsed:.2f}s)"
        )

        for item in items:
            icon = "+" if item["outcome"] == "passed" else "x"
            terminalreporter.write_line(
                f"        [{icon}] {item['name']}  ({item['duration']:.2f}s)"
            )

    terminalreporter.write_line("")
    terminalreporter.write_line(
        f"  Total: {total_passed} passed, {total_failed} failed  ({total_time:.2f}s)"
    )

    if total_failed == 0 and total_passed > 0:
        terminalreporter.write_line(
            "  All fault scenarios detected reliably."
        )
    elif total_failed > 0:
        terminalreporter.write_line(
            f"  {total_failed} detection(s) unreliable - review failing tests above."
        )
