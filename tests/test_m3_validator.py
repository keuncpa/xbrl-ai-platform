"""M3 Validator — BS 균형·합산·필수항목 검증 규칙 테스트."""
from pathlib import Path

from conftest import ENGINE_DIR
from m3_validator import Validator

TAX = str(Path(ENGINE_DIR) / "data" / "kor_ifrs_taxonomy.json")


def _validate(tagger, fs):
    tagged = tagger.tag_financial_statement(fs, period_end="2024-12-31", entity="테스트사")
    return Validator(taxonomy_path=TAX).validate(tagged)


def test_balanced_bs_passes(tagger, balanced_fs):
    report = _validate(tagger, balanced_fs)
    assert report["status"] == "PASS"
    assert len(report["errors"]) == 0


def test_unbalanced_bs_fails(tagger, balanced_fs):
    """자산(500) ≠ 부채(100)+자본(300) → ERROR + FAIL."""
    fs = [dict(x) for x in balanced_fs]
    for item in fs:
        if item["계정과목"] == "자본총계":
            item["금액"] = 300
    report = _validate(tagger, fs)
    assert report["status"] == "FAIL"
    assert any(e["rule"].startswith("BS_") or "균형" in e["message"] or "BALANCE" in e["rule"].upper()
               for e in report["errors"])


def test_calculation_mismatch_detected(tagger, balanced_fs):
    """유동자산+비유동자산 ≠ 자산총계 → 합산 오류 검출."""
    fs = [dict(x) for x in balanced_fs]
    for item in fs:
        if item["계정과목"] == "유동자산":
            item["금액"] = 150  # 150+300=450 ≠ 500
    report = _validate(tagger, fs)
    assert report["status"] == "FAIL"


def test_missing_required_element_fails(tagger):
    fs = [{"계정과목": "자산총계", "금액": 500, "수준": 0}]
    report = _validate(tagger, fs)
    assert report["status"] == "FAIL"
    assert any(e["rule"] == "REQUIRED_ELEMENT" for e in report["errors"])
