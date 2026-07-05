"""/api/corps 검색 로직(search_corps) 단위 테스트 — 순수 함수 부분만 검증."""
import importlib.util
from pathlib import Path

CORPS_PY = Path(__file__).resolve().parent.parent / "xbrl-web" / "api" / "corps.py"
spec = importlib.util.spec_from_file_location("corps_api", CORPS_PY)
corps_api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(corps_api)

SAMPLE = [
    {"c": "00000001", "n": "삼성전자", "s": "005930"},
    {"c": "00000002", "n": "삼성디스플레이", "s": ""},
    {"c": "00000003", "n": "삼성전자판매", "s": ""},
    {"c": "00000004", "n": "엘지전자", "s": "066570"},
    {"c": "00000005", "n": "비바리퍼블리카", "s": ""},
]


def test_substring_match_includes_unlisted():
    r = corps_api.search_corps(SAMPLE, "삼성")
    names = [c["n"] for c in r]
    assert "삼성전자" in names
    assert "삼성디스플레이" in names  # 비상장 포함


def test_listed_first_then_prefix():
    r = corps_api.search_corps(SAMPLE, "삼성")
    assert r[0]["n"] == "삼성전자"  # 상장사 우선
    assert r[0]["s"] != ""


def test_stock_code_search():
    r = corps_api.search_corps(SAMPLE, "066570")
    assert len(r) == 1 and r[0]["n"] == "엘지전자"


def test_empty_query_returns_nothing():
    assert corps_api.search_corps(SAMPLE, "  ") == []


def test_limit_respected():
    many = [{"c": f"{i:08d}", "n": f"테스트기업{i}", "s": ""} for i in range(100)]
    assert len(corps_api.search_corps(many, "테스트", limit=30)) == 30
