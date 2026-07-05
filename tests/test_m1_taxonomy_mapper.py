"""M1 Taxonomy Mapper — 매핑 정확도·별칭·저신뢰(확장항목) 분류 테스트."""


def test_exact_match_assets(mapper):
    r = mapper.map_account("자산총계")
    assert r["best_match"] is not None
    assert r["best_match"]["id"] == "ifrs-full:Assets"
    assert r["confidence"] >= 0.99
    assert r["needs_extension"] is False


def test_alias_match(mapper):
    """별칭 사전: '매각예정자산' → 매각예정비유동자산."""
    r = mapper.map_account("매각예정자산")
    assert r["best_match"] is not None
    assert r["best_match"]["id"] == "ifrs-full:NoncurrentAssetsHeldForSale"
    assert r["confidence"] >= 0.99


def test_core_bs_elements(mapper):
    expected = {
        "유동자산": "ifrs-full:CurrentAssets",
        "비유동자산": "ifrs-full:NoncurrentAssets",
        "부채총계": "ifrs-full:Liabilities",
        "자본총계": "ifrs-full:Equity",
    }
    for name, elem_id in expected.items():
        r = mapper.map_account(name)
        assert r["best_match"]["id"] == elem_id, f"{name} → {r['best_match']['id']}"


def test_unknown_account_needs_extension(mapper):
    """표준에 없는 항목은 저신뢰 + 확장항목 후보로 분류돼야 한다."""
    r = mapper.map_account("가상화폐채굴장비충당손실적립금")
    assert r["confidence"] < 0.5
    assert r["needs_extension"] is True


def test_empty_and_whitespace_input(mapper):
    for bad in ["", "   "]:
        r = mapper.map_account(bad)
        assert r["best_match"] is None or r["confidence"] < 0.5
