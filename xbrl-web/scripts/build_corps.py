"""빌드 시점에 DART 전체 등록법인 목록(비상장 포함)을 정적 JSON으로 생성.

Vercel 빌드 단계(prebuild)에서 실행됩니다:
  DART corpCode.zip 다운로드 → 파싱 → public/corps_all.json ([corp_code, name, stock_code] 배열)

실패해도 빌드는 계속됩니다(exit 0) — 이 경우 클라이언트는 /api/corps 서버리스 폴백을 사용합니다.
"""
import io
import json
import os
import sys
import xml.etree.ElementTree as ET
import zipfile
from urllib.request import urlopen

OUT = os.path.join(os.path.dirname(__file__), "..", "public", "corps_all.json")


def main():
    api_key = os.environ.get("DART_API_KEY", "")
    if not api_key:
        print("[build_corps] DART_API_KEY 미설정 → 정적 목록 생성 건너뜀 (서버리스 폴백 사용)")
        return

    print("[build_corps] DART corpCode.zip 다운로드 중...")
    with urlopen(f"https://opendart.fss.or.kr/api/corpCode.xml?crtfc_key={api_key}", timeout=120) as res:
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
            corps.append([code, name, stock])

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(corps, f, ensure_ascii=False, separators=(",", ":"))
    print(f"[build_corps] 완료: {len(corps):,}개 법인 → public/corps_all.json ({os.path.getsize(OUT)/1e6:.1f}MB)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001 — 빌드는 절대 깨뜨리지 않는다
        print(f"[build_corps] 실패(빌드는 계속): {e}", file=sys.stderr)
    sys.exit(0)
