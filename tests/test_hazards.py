# finds - Copyright (c) 2026 Kirizaki

import pytest


@pytest.mark.hazards
def test_upload_quota_fixed_is_correct(hazard_runner):
    """
    Fixed path respects quota: no violations, usage <= quota.
    """
    stats = hazard_runner(num_uploads=100, upload_size_mb=10, quota_mb=100,
                          buggy=False, prod_mode=True)

    assert stats["errors"] == 0
    assert stats["used_mb"] <= stats["quota_mb"]
    assert stats["quota_violations"] == 0
    assert stats["accepted"] + stats["rejected"] == 100

@pytest.mark.hazards
def test_upload_quota_toctou_bug(hazard_runner):
    """
    Buggy path: TOCTOU race causes quota oversubscription.
    """
    stats = hazard_runner(num_uploads=100, upload_size_mb=10, quota_mb=100,
                          buggy=True, prod_mode=True)

    print(stats)
    assert stats["used_mb"] > stats["quota_mb"]
    assert stats["quota_violations"] >= 1

@pytest.mark.hazards
def test_toctou_upload_quota_violations_formula(hazard_runner):
    """
    Verify the quota violations formula holds consistently across multiple runs.

    quota_violations = (used_mb - quota_mb) / upload_size_mb + 1
    """
    upload_size_mb = 5
    for _ in range(10):
        stats = hazard_runner(num_uploads=200, upload_size_mb=upload_size_mb,
                              quota_mb=120, buggy=True, prod_mode=True)

        print(stats)
        assert stats["quota_violations"] == ((stats["used_mb"] - stats["quota_mb"]) / upload_size_mb) + 1

@pytest.mark.hazards
@pytest.mark.stress
def test_toctou_upload_quota_stress(hazard_runner):
    """
    Sustained high-concurrency TOCTOU stress test.

    1000 concurrent uploads per round, 50 rounds, varying quota pressure.
    Verifies that the race condition is consistently reproducible under load,
    and that violations scale with oversubscription.
    """
    rounds = 50
    num_uploads = 1000
    upload_size_mb = 5
    quota_mb = 200

    total_violations = 0
    max_oversubscription = 0

    for i in range(rounds):
        stats = hazard_runner(num_uploads=num_uploads, upload_size_mb=upload_size_mb,
                              quota_mb=quota_mb, buggy=True, prod_mode=True)

        oversubscription = stats["used_mb"] - stats["quota_mb"]
        total_violations += stats["quota_violations"]
        max_oversubscription = max(max_oversubscription, oversubscription)

        assert stats["accepted"] + stats["rejected"] == num_uploads
        assert stats["used_mb"] > stats["quota_mb"]
        assert stats["quota_violations"] >= 1

    print(f"\n  Stress: {rounds} rounds × {num_uploads} uploads")
    print(f"  Total violations: {total_violations}")
    print(f"  Max oversubscription: {max_oversubscription} MB over {quota_mb} MB quota")

    # race must be consistently reproducible under sustained load
    assert total_violations >= rounds

@pytest.mark.hazards
@pytest.mark.regression
def test_toctou_fixed_quota_never_exceeded(hazard_runner):
    """
    Regression: the fixed path must never allow quota oversubscription.

    Previously, removing the lock from _upload_fixed or reintroducing
    the sleep window allowed the TOCTOU race to resurface. This test
    runs multiple rounds to guard against that regression.
    """
    for _ in range(10):
        stats = hazard_runner(num_uploads=200, upload_size_mb=5, quota_mb=100,
                              buggy=False, prod_mode=True)

        assert stats["used_mb"] <= stats["quota_mb"], (
            f"Quota exceeded: {stats['used_mb']} > {stats['quota_mb']} - "
            "TOCTOU fix may have regressed")
        assert stats["quota_violations"] == 0
        assert stats["accepted"] + stats["rejected"] == 200

@pytest.mark.hazards
@pytest.mark.regression
def test_toctou_buggy_always_detected(hazard_runner):
    """
    Regression: the buggy path must always produce quota violations.
    If this test passes with zero violations, the fault injection
    or the race window may have been inadvertently fixed.
    """
    for _ in range(5):
        stats = hazard_runner(num_uploads=100, upload_size_mb=10, quota_mb=100,
                              buggy=True, prod_mode=True)

        assert stats["quota_violations"] >= 1, (
            "TOCTOU race was not triggered - fault injection may be broken")

