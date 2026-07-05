"""pytest 공통 설정 — 코어 엔진(xbrl_platform)을 flat import 경로로 등록."""
import sys
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent.parent / "xbrl_platform"
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

import pytest  # noqa: E402

from m1_taxonomy_mapper import TaxonomyMapper  # noqa: E402
from m2_auto_tagger import AutoTagger  # noqa: E402


@pytest.fixture(scope="session")
def mapper():
    return TaxonomyMapper(taxonomy_path=str(ENGINE_DIR / "data" / "kor_ifrs_taxonomy.json"))


@pytest.fixture()
def tagger(mapper):
    return AutoTagger(taxonomy_mapper=mapper)


@pytest.fixture()
def balanced_fs():
    """자산 = 부채 + 자본이 성립하는 최소 재무상태표."""
    return [
        {"계정과목": "자산총계", "금액": 500, "수준": 0},
        {"계정과목": "유동자산", "금액": 200, "수준": 1},
        {"계정과목": "비유동자산", "금액": 300, "수준": 1},
        {"계정과목": "부채총계", "금액": 100, "수준": 0},
        {"계정과목": "유동부채", "금액": 60, "수준": 1},
        {"계정과목": "비유동부채", "금액": 40, "수준": 1},
        {"계정과목": "자본총계", "금액": 400, "수준": 0},
    ]
