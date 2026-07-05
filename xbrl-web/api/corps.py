"""
Vercel Python Serverless Function — DART 전체 등록법인 검색 (비상장 포함)

GET /api/corps?q=검색어
  응답: { "ok": true, "results": [{"c": corp_code, "n": 기업명, "s": 종목코드(비상장은 "")}, ...] }

동작:
  - DART corpCode API(zip)를 최초 1회 다운로드해 /tmp 와 모듈 메모리에 캐시
  - 약 10만+ 등록법인(비상장 포함)에서 이름 부분일치 검색, 상위 30건 반환
  - 상장사(종목코드 보유) → 접두 일치 → 이름 길이 순으로 정렬해 관련도 높은 결과 우선
"""

from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from urllib.request import urlopen
import io
import json
import os
import xml.etree.ElementTree as ET
import zipfile

DART_CORPCODE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"
CACHE_PATH = os.path.join("/tmp", "dart_corps_all.json")
MAX_RESULTS = 30

_corps_cache = None  # 웜 인스턴스 간 재사용되는 모듈 레벨 캐시


def _load_corps():
    """전체 법인 목록 로드: 메모리 → /tmp → DART API 순."""
    global _corps_cache
    if _corps_cache is not None:
        return _corps_cache

    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                _corps_cache = json.load(f)
            return _corps_cache
        except (json.JSONDecodeError, OSError):
            pass  # 캐시 손상 시 재다운로드

    api_key = os.environ.get("DART_API_KEY", "")
    if not api_key:
        raise RuntimeError("DART_API_KEY 환경변수가 설정되지 않았습니다.")

    with urlopen(f"{DART_CORPCODE_URL}?crtfc_key={api_key}", timeout=30) as res:
        raw = res.read()

    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        xml_bytes = zf.read(zf.namelist()[0])

    root = ET.fromstring(xml_bytes)
    corps = []
    for node in root.iter("list"):
        name = (node.findtext("corp_name") or "").strip()
        code = (node.findtext("corp_code") or "").strip()
        stock = (node.findtext("stock_code") or "").strip()
        if name and code:
            corps.append({"c": code, "n": name, "s": stock})

    _corps_cache = corps
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(corps, f, ensure_ascii=False)
    except OSError:
        pass  # /tmp 캐시 실패는 무시 (다음 콜드스타트에서 재다운로드)
    return corps


def search_corps(corps, query, limit=MAX_RESULTS):
    """이름 부분일치 검색. 상장사 → 접두 일치 → 짧은 이름 순 정렬."""
    q = query.strip().lower()
    if not q:
        return []
    matches = [c for c in corps if q in c["n"].lower() or (c["s"] and q in c["s"])]
    matches.sort(key=lambda c: (
        0 if c["s"] else 1,                       # 상장사 우선
        0 if c["n"].lower().startswith(q) else 1,  # 접두 일치 우선
        len(c["n"]),
    ))
    return matches[:limit]


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            query = (qs.get("q") or [""])[0]
            if not query.strip():
                self._send(400, {"ok": False, "error": "q 파라미터가 필요합니다."})
                return
            corps = _load_corps()
            results = search_corps(corps, query)
            self._send(200, {"ok": True, "total_corps": len(corps), "results": results})
        except Exception:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            self._send(500, {"ok": False, "error": "법인 목록 조회에 실패했습니다. 잠시 후 다시 시도해 주세요."})

    def _send(self, code, obj):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        # 법인 목록은 일 단위로만 변하므로 CDN 캐시로 반복 검색 비용 절감
        self.send_header("Cache-Control", "s-maxage=86400, stale-while-revalidate=604800")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
