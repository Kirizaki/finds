# finds - Copyright (c) 2026 Kirizaki

from lab.hazards import toctou_upload_quota_race

def test_upload_quota_toctou_bug():
    result = toctou_upload_quota_race(
        num_uploads=100,
        upload_size_mb=10,
        quota_mb=100,
        buggy=True,
    )

    print(result)
    assert result["used_mb"] > result["quota_mb"]
    assert result["quota_violations"] > 1

def test_upload_quota_fixed():
    result = toctou_upload_quota_race(
        num_uploads=100,
        upload_size_mb=10,
        quota_mb=100,
        buggy=False,
    )

    print(result)
    assert result["used_mb"] <= result["quota_mb"]
    assert result["quota_violations"] == 0

def test_toctou_upload_quota_race_stress():
    upload_size_mb = 5
    for _ in range(10):

        buggy = toctou_upload_quota_race(
            num_uploads=200,
            upload_size_mb=upload_size_mb,
            quota_mb=120,
            buggy=True,
        )

        print(buggy)
        assert buggy["quota_violations"] == ((buggy["used_mb"] - buggy["quota_mb"]) / upload_size_mb) + 1

