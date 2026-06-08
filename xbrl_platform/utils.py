"""공통 유틸리티 모듈"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path

# ── 로깅 설정 ──
def setup_logger(name: str, level=logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        fmt = logging.Formatter('[%(asctime)s] %(name)s | %(levelname)s | %(message)s',
                                datefmt='%H:%M:%S')
        handler.setFormatter(fmt)
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger

# ── 경로 관리 ──
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"

def ensure_dirs():
    DATA_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)

# ── JSON 유틸 ──
def load_json(path: str | Path) -> dict:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(data: dict, path: str | Path):
    ensure_dirs()
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ── 타임스탬프 ──
def timestamp() -> str:
    return datetime.now().strftime('%Y%m%d_%H%M%S')

# ── 텍스트 정규화 ──
def normalize_text(text: str) -> str:
    """계정과목명 정규화: 공백/괄호 통일"""
    import re
    text = text.strip()
    text = re.sub(r'\s+', ' ', text)
    text = text.replace('（', '(').replace('）', ')')
    return text

# ── 숫자 파싱 ──
def parse_number(text: str) -> float | None:
    """문자열에서 숫자 추출 (콤마, 괄호 음수 처리)"""
    if not text or not isinstance(text, str):
        return None
    import re
    text = text.strip()
    is_negative = text.startswith('(') and text.endswith(')')
    text = re.sub(r'[(),\s원₩]', '', text)
    text = text.replace('−', '-').replace('–', '-')
    try:
        value = float(text)
        return -value if is_negative else value
    except ValueError:
        return None

# ── 결과 리포트 출력 ──
def print_report(title: str, items: list[dict], columns: list[str]):
    """콘솔에 테이블 형식 리포트 출력"""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")

    # 컬럼 폭 계산
    widths = {}
    for col in columns:
        max_w = len(col)
        for item in items:
            val = str(item.get(col, ''))
            max_w = max(max_w, len(val))
        widths[col] = min(max_w + 2, 40)

    # 헤더
    header = '  '.join(col.ljust(widths[col]) for col in columns)
    print(f"  {header}")
    print(f"  {'─'*len(header)}")

    # 데이터
    for item in items:
        row = '  '.join(str(item.get(col, '')).ljust(widths[col])[:widths[col]]
                        for col in columns)
        print(f"  {row}")

    print(f"{'='*70}\n")
