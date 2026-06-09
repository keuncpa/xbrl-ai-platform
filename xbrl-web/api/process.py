"""
Vercel Python Serverless Function — XBRL 엔진 엔드포인트

POST /api/process
  요청 본문(JSON):
    {
      "accounts":        [{"name": "자산총계", "amount": 514531948000000, "level": 0}, ...],
      "prior_accounts":  [ ...전기 데이터(선택) ... ],
      "period_end":      "2024-12-31",
      "entity":          "삼성전자"
    }
  응답(JSON):
    {
      "ok": true,
      "mapping":      [...],   # M1 매핑 + M2 태깅 결과
      "validation":   {...},   # M3 검증 리포트
      "coverage":     {...},   # M2 태깅 커버리지
      "ixbrl_html":   "<...>", # M2 iXBRL 산출물(다운로드용)
      "change_report":{...},   # M4 변경 추적(전기 데이터가 있을 때만)
      "mapping_stats":{...}    # M1 매핑 통계
    }

핵심: 이 함수는 xbrl_platform 코어 엔진(M1~M4)을 그대로 호출합니다.
      웹 데모와 배치 파이프라인이 '같은 엔진'을 공유하므로 결과가 일치합니다.
"""

from http.server import BaseHTTPRequestHandler
import json
import sys
import os
import tempfile

# ── 코어 엔진 경로 등록 ──
_ENGINE_DIR = os.path.join(os.path.dirname(__file__), "_engine")
if _ENGINE_DIR not in sys.path:
    sys.path.insert(0, _ENGINE_DIR)

from m1_taxonomy_mapper import TaxonomyMapper   # noqa: E402
from m2_auto_tagger import AutoTagger           # noqa: E402
from m3_validator import Validator              # noqa: E402
from m4_change_tracker import ChangeTracker     # noqa: E402

TAXONOMY_PATH = os.path.join(_ENGINE_DIR, "data", "kor_ifrs_taxonomy.json")

import math  # noqa: E402


def _clean_json(obj):
    """JSON에 허용되지 않는 inf/-inf/NaN 값을 None 으로 재귀 변환."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _clean_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean_json(v) for v in obj]
    return obj


def _to_fs(items):
    """프론트엔드 accounts → 엔진 입력 형태로 변환"""
    out = []
    for a in items or []:
        name = (a.get("name") or "").strip()
        if not name:
            continue
        out.append({
            "계정과목": name,
            "금액": a.get("amount"),
            "수준": a.get("level", 0),
        })
    return out


def run_pipeline(payload):
    """M1 → M2 → M3 (+ M4) 통합 실행. 순수 함수라 로컬 테스트 가능."""
    accounts = payload.get("accounts", [])
    prior = payload.get("prior_accounts") or []
    period_end = payload.get("period_end", "2024-12-31")
    entity = payload.get("entity", "Entity")

    if not accounts:
        return {"ok": False, "error": "계정과목 데이터가 비어 있습니다."}

    # M1 + M2 : 매핑 후 iXBRL 태깅
    mapper = TaxonomyMapper(taxonomy_path=TAXONOMY_PATH)
    tagger = AutoTagger(taxonomy_mapper=mapper)
    tagged = tagger.tag_financial_statement(
        _to_fs(accounts), period_end=period_end, entity=entity
    )

    # M2 : iXBRL 산출물(HTML 문자열) — /tmp(쓰기가능)에 생성 후 회수
    tmp_path = os.path.join(tempfile.gettempdir(), "ixbrl_out.html")
    tagger.export_ixbrl(tagged, output_path=tmp_path, title=f"{entity} 재무상태표")
    with open(tmp_path, "r", encoding="utf-8") as f:
        ixbrl_html = f.read()

    coverage = tagger.get_coverage_report(tagged)

    # M4 : 전기 데이터가 있으면 변경 추적
    prior_tagged = None
    change_report = None
    if prior:
        try:
            prior_year = str(int(period_end[:4]) - 1)
        except ValueError:
            prior_year = "전기"
        prior_tagger = AutoTagger(taxonomy_mapper=mapper)
        prior_tagged = prior_tagger.tag_financial_statement(
            _to_fs(prior), period_end=f"{prior_year}-12-31", entity=entity
        )
        tracker = ChangeTracker()
        changes = tracker.compare(prior_tagged, tagged)
        change_report = tracker.generate_report(changes)

    # M3 : 검증 (전기 태깅이 있으면 이상치 탐지 포함)
    validator = Validator(taxonomy_path=TAXONOMY_PATH)
    validation = validator.validate(tagged, prior_tagged)

    # 프론트엔드 표시용 매핑 테이블
    mapping = [{
        "name": t["account_name"],
        "taxonomy_element": t.get("taxonomy_element") or f"ext:{t['account_name'].replace(' ', '')}",
        "confidence": t.get("confidence", 0),
        "is_extension": t.get("needs_extension", False),
        "amount": t.get("amount") or 0,
        "level": t.get("level", 0),
    } for t in tagged]

    map_results = mapper.map_accounts([a.get("name", "") for a in accounts if a.get("name")])

    return {
        "ok": True,
        "entity": entity,
        "period_end": period_end,
        "mapping": mapping,
        "validation": validation,
        "coverage": coverage,
        "ixbrl_html": ixbrl_html,
        "change_report": change_report,
        "mapping_stats": mapper.get_statistics(map_results),
    }


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get("content-length", 0) or 0)
            body = self.rfile.read(length) if length else b"{}"
            payload = json.loads(body or b"{}")
            result = run_pipeline(payload)
            self._send(200 if result.get("ok") else 400, result)
        except Exception as e:  # noqa: BLE001
            self._send(500, {"ok": False, "error": str(e)})

    def do_GET(self):
        self._send(200, {
            "ok": True,
            "message": "XBRL 엔진이 준비되었습니다. accounts를 POST 하세요.",
            "engine": "xbrl_platform M1~M4",
        })

    def _send(self, code, obj):
        # inf/-inf/NaN 은 유효한 JSON이 아니므로 None 으로 정리 (예: 전기 0 → 변동률 무한대)
        data = json.dumps(_clean_json(obj), ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
