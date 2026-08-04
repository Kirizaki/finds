# finds - Copyright (c) 2026 Kirizaki

# root conftest: pytest hooks (report summary, HTML dashboard, JUnit XML)

from collections import defaultdict

import pytest

# ---- fault-detection result summary ----

_FAULT_MARKERS = ("contentions", "deadlocks", "hazards")
_FAULT_LABELS = {
    "contentions": "Resource Contention (thread / I/O / CPU)",
    "deadlocks": "Deadlocks (circular-wait)",
    "hazards": "Hazards / Race Conditions (TOCTOU)",
    "other": "Other",
}

_results = defaultdict(list)


def _fault_class_for(item_or_report):
    keywords = item_or_report.keywords
    for marker in _FAULT_MARKERS:
        if marker in keywords:
            return marker
    return "other"


def pytest_runtest_logreport(report):
    if report.when == "call":
        _results[_fault_class_for(report)].append({
            "name": report.nodeid.split("::")[-1],
            "outcome": report.outcome,
            "duration": report.duration,
        })


# ---- pytest-html integration ----

@pytest.hookimpl(optionalhook=True)
def pytest_html_results_table_header(cells):
    cells.insert(1, '<th class="sortable" data-column-type="faultClass">Fault Class</th>')
    cells.insert(2, '<th class="sortable time" data-column-type="duration">Duration (s)</th>')


@pytest.hookimpl(optionalhook=True)
def pytest_html_results_table_row(report, cells):
    fault_class = getattr(report, "_fault_class", "other")
    duration = getattr(report, "_duration_s", 0)
    cells.insert(1, f"<td>{fault_class}</td>")
    cells.insert(2, f"<td>{duration:.3f}</td>")


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Attach fault class and duration to report for HTML table hooks."""
    outcome = yield
    report = outcome.get_result()
    report._fault_class = _FAULT_LABELS.get(_fault_class_for(item), "Other")
    report._duration_s = report.duration if report.when == "call" else 0


@pytest.hookimpl(optionalhook=True)
def pytest_html_report_title(report):
    report.title = "finds - Fault Detection Dashboard"


@pytest.hookimpl(optionalhook=True)
def pytest_html_results_summary(prefix, summary, postfix):
    # inject fault-class summary table into HTML report header
    rows = []
    total_p, total_f, total_t = 0, 0, 0.0

    for fault_class in (*_FAULT_MARKERS, "other"):
        items = _results.get(fault_class, [])
        if not items:
            continue
        label = _FAULT_LABELS[fault_class]
        passed = sum(1 for i in items if i["outcome"] == "passed")
        failed = sum(1 for i in items if i["outcome"] == "failed")
        elapsed = sum(i["duration"] for i in items)
        total_p += passed
        total_f += failed
        total_t += elapsed
        status_color = "green" if failed == 0 else "red"
        rows.append(
            f'<tr><td style="color:{status_color};font-weight:bold">'
            f'{"PASS" if failed == 0 else "FAIL"}</td>'
            f"<td>{label}</td>"
            f"<td>{passed}/{len(items)}</td>"
            f"<td>{elapsed:.2f}s</td></tr>"
        )

    if rows:
        prefix.extend([
            "<h3>Fault Detection Summary</h3>",
            '<table style="border-collapse:collapse;margin-bottom:1em">',
            "<tr><th>Status</th><th>Fault Class</th><th>Passed</th><th>Time</th></tr>",
            *rows,
            f"<tr style='border-top:2px solid #333'><td></td><td><b>Total</b></td>"
            f"<td><b>{total_p} passed, {total_f} failed</b></td>"
            f"<td><b>{total_t:.2f}s</b></td></tr>",
            "</table>",
        ])


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    terminalreporter.section("Fault Detection Summary")

    total_passed = 0
    total_failed = 0
    total_time = 0.0

    for fault_class in (*_FAULT_MARKERS, "other"):
        items = _results.get(fault_class, [])
        if not items:
            continue

        label = _FAULT_LABELS[fault_class]
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
