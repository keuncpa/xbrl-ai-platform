"""M2 Auto Tagger — 태깅, HTML/XML 이스케이프, 컨텍스트 격리 테스트."""


def test_tagging_produces_ixbrl_tags(tagger, balanced_fs):
    tagged = tagger.tag_financial_statement(balanced_fs, period_end="2024-12-31", entity="테스트사")
    assert len(tagged) == len(balanced_fs)
    core = [t for t in tagged if t["taxonomy_element"] == "ifrs-full:Assets"]
    assert core and core[0]["ixbrl_tag"] is not None
    assert 'contextRef="ctx_20241231_연결"' in core[0]["ixbrl_tag"]


def test_export_escapes_special_chars(tagger, tmp_path):
    """계정명·회사명에 &, <, > 가 있어도 산출 HTML이 깨지지 않아야 한다."""
    fs = [{"계정과목": "R&D자산<특수>", "금액": 100, "수준": 0}]
    tagged = tagger.tag_financial_statement(fs, period_end="2024-12-31", entity="A&B<주>")
    out = tmp_path / "out.html"
    tagger.export_ixbrl(tagged, output_path=out, title="테스트<재무상태표>")
    html = out.read_text(encoding="utf-8")
    assert "R&amp;D자산&lt;특수&gt;" in html
    assert "A&amp;B&lt;주&gt;" in html
    assert "<특수>" not in html  # 원시 태그 형태로 남으면 안 됨


def test_context_isolation_between_entities(tagger, balanced_fs, tmp_path):
    """하나의 tagger로 두 회사를 연속 처리해도 컨텍스트가 섞이면 안 된다."""
    tagger.tag_financial_statement(balanced_fs, period_end="2023-12-31", entity="첫째회사")
    tagged_b = tagger.tag_financial_statement(balanced_fs, period_end="2024-12-31", entity="둘째회사")
    out = tmp_path / "b.html"
    tagger.export_ixbrl(tagged_b, output_path=out, title="둘째회사 재무상태표")
    html = out.read_text(encoding="utf-8")
    assert "첫째회사" not in html, "이전 회사 컨텍스트가 혼입됨"
    assert "둘째회사" in html


def test_string_amount_does_not_crash(tagger, tmp_path):
    """숫자가 아닌 금액이 섞여도 export가 예외 없이 동작해야 한다."""
    fs = [
        {"계정과목": "자산총계", "금액": 500, "수준": 0},
        {"계정과목": "주석참조항목", "금액": None, "수준": 2},
    ]
    tagged = tagger.tag_financial_statement(fs, period_end="2024-12-31", entity="테스트사")
    out = tmp_path / "s.html"
    tagger.export_ixbrl(tagged, output_path=out)
    assert out.exists()
