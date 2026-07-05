"""M4 Change Tracker — 신규·삭제·금액변동·중요성 판단 테스트."""
from m4_change_tracker import ChangeTracker, ChangeType


def _tag(tagger, fs, year, entity="테스트사"):
    return tagger.tag_financial_statement(fs, period_end=f"{year}-12-31", entity=entity)


def test_detects_added_removed_and_amount_change(tagger, balanced_fs):
    prior = _tag(tagger, balanced_fs, 2023)
    current_fs = [dict(x) for x in balanced_fs]
    # 금액 변동: 유동자산 200 → 260 (+30%, 자산총계의 5% 초과 → 중요 변동)
    for item in current_fs:
        if item["계정과목"] == "유동자산":
            item["금액"] = 260
    # 삭제: 비유동부채 제거 / 신규: 무형자산 추가
    current_fs = [x for x in current_fs if x["계정과목"] != "비유동부채"]
    current_fs.append({"계정과목": "무형자산", "금액": 50, "수준": 2})
    current = _tag(tagger, current_fs, 2024)

    tracker = ChangeTracker()
    changes = tracker.compare(prior, current)
    types = {c["type"] for c in changes}
    assert ChangeType.ADDED in types
    assert ChangeType.REMOVED in types
    assert ChangeType.AMOUNT_CHANGED in types

    report = tracker.generate_report(changes)
    assert report["total_changes"] == len(changes)
    assert report["material_changes"] >= 1  # 유동자산 +60 (자산총계 500의 12%)


def test_no_changes_when_identical(tagger, balanced_fs):
    prior = _tag(tagger, balanced_fs, 2023)
    current = _tag(tagger, balanced_fs, 2024)
    changes = ChangeTracker().compare(prior, current)
    assert all(c["type"] != ChangeType.AMOUNT_CHANGED for c in changes)


def test_all_zero_amounts_do_not_crash(tagger):
    """금액이 전부 0/None이어도 max() ValueError가 나면 안 된다 (회귀 테스트)."""
    fs = [
        {"계정과목": "자산총계", "금액": 0, "수준": 0},
        {"계정과목": "부채총계", "금액": None, "수준": 0},
    ]
    prior = _tag(tagger, fs, 2023)
    current = _tag(tagger, fs, 2024)
    changes = ChangeTracker().compare(prior, current)  # 예외 없이 완료돼야 함
    assert isinstance(changes, list)
