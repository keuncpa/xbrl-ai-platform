"""
M1. Taxonomy Mapper - 계정과목 → XBRL 표준 Taxonomy 자동 매핑 엔진

기능:
  - KOR-IFRS Taxonomy 로드 및 인덱싱
  - 계정과목명 텍스트 유사도 기반 Top-K 매핑 추천
  - 산업별 매핑 패턴 학습 (이력 기반)
  - 확장항목(Extension) 필요 여부 판단

사용 예시:
    mapper = TaxonomyMapper()
    result = mapper.map_account("현금및현금성자산")
    result = mapper.map_accounts(["매출액", "재고자산", "영업이익"])
"""

import re
import json
from pathlib import Path
from difflib import SequenceMatcher
from collections import defaultdict
from utils import setup_logger, load_json, save_json, DATA_DIR, OUTPUT_DIR, normalize_text, print_report

logger = setup_logger('M1.TaxonomyMapper')


class TaxonomyMapper:
    """계정과목 → XBRL Taxonomy 자동 매핑 엔진"""

    def __init__(self, taxonomy_path: str | Path = None):
        self.taxonomy_path = taxonomy_path or DATA_DIR / "kor_ifrs_taxonomy.json"
        self.elements = []
        self.label_index = {}       # label_ko → element
        self.keyword_index = defaultdict(list)  # 키워드 → [elements]
        self.mapping_history = {}   # 과거 매핑 이력 (학습용)
        self._load_taxonomy()

    def _load_taxonomy(self):
        """Taxonomy 로드 및 인덱스 구축"""
        data = load_json(self.taxonomy_path)
        self.elements = data.get('elements', [])
        self.calc_rules = data.get('calculation_rules', [])

        for elem in self.elements:
            label = normalize_text(elem['label_ko'])
            self.label_index[label] = elem

            # 키워드 인덱스: 한글 레이블의 각 토큰으로 역인덱스
            tokens = self._tokenize(label)
            for token in tokens:
                self.keyword_index[token].append(elem)

        logger.info(f"Taxonomy 로드 완료: {len(self.elements)}개 요소, {len(self.keyword_index)}개 키워드")

    def _tokenize(self, text: str) -> list[str]:
        """한글 계정과목명 토큰화"""
        # 한글 형태소 단위 근사 분리: 조사/접미사 패턴 기반
        text = normalize_text(text)
        # 괄호 내용 분리
        parts = re.split(r'[()및,\s]+', text)
        tokens = []
        for part in parts:
            if len(part) >= 2:
                tokens.append(part)
                # 복합어 분리: "유동자산" → "유동", "자산"
                if len(part) >= 4:
                    for i in range(2, len(part)-1):
                        sub1, sub2 = part[:i], part[i:]
                        if len(sub1) >= 2 and len(sub2) >= 2:
                            tokens.extend([sub1, sub2])
        return list(set(tokens))

    def _text_similarity(self, s1: str, s2: str) -> float:
        """두 텍스트 간 유사도 (0~1)"""
        s1 = normalize_text(s1)
        s2 = normalize_text(s2)

        # 1. 완전 일치
        if s1 == s2:
            return 1.0

        # 2. 포함 관계 — 단, 길이 비율이 너무 다르면 감점
        #    "자산" in "자산총계"는 0.9이지만, "자산" in "순확정급여자산"은 0.4 수준
        if s1 in s2 or s2 in s1:
            shorter, longer = (s1, s2) if len(s1) <= len(s2) else (s2, s1)
            length_ratio = len(shorter) / len(longer)
            if length_ratio >= 0.7:  # 길이가 비슷하면 높은 유사도
                return 0.9
            elif length_ratio >= 0.5:
                return 0.6 + length_ratio * 0.3
            else:
                # 짧은 단어가 긴 단어에 포함될 뿐, 실질적으로 다른 항목
                pass  # 아래 일반 유사도 로직으로 처리

        # 3. SequenceMatcher (편집 거리 기반)
        seq_ratio = SequenceMatcher(None, s1, s2).ratio()

        # 4. 키워드 겹침 (Jaccard) — 2글자 미만 토큰 제외하여 정밀도 향상
        tokens1 = set(t for t in self._tokenize(s1) if len(t) >= 2)
        tokens2 = set(t for t in self._tokenize(s2) if len(t) >= 2)
        if tokens1 and tokens2:
            jaccard = len(tokens1 & tokens2) / len(tokens1 | tokens2)
        else:
            jaccard = 0.0

        # 가중 평균
        return seq_ratio * 0.6 + jaccard * 0.4

    def map_account(self, account_name: str, top_k: int = 3) -> dict:
        """
        단일 계정과목을 Taxonomy에 매핑

        Args:
            account_name: 계정과목명 (예: "현금및현금성자산")
            top_k: 추천 결과 수

        Returns:
            {
                "input": "현금및현금성자산",
                "best_match": {...},
                "confidence": 0.95,
                "candidates": [...],
                "needs_extension": False
            }
        """
        account_name = normalize_text(account_name)

        # 1. 이력 기반 매핑 (학습된 매핑이 있으면 우선)
        if account_name in self.mapping_history:
            hist = self.mapping_history[account_name]
            logger.info(f"이력 매핑: {account_name} → {hist['id']} (이력 기반)")
            return {
                "input": account_name,
                "best_match": hist,
                "confidence": 1.0,
                "candidates": [hist],
                "needs_extension": False,
                "method": "history"
            }

        # 2. 정확 일치
        if account_name in self.label_index:
            exact = self.label_index[account_name]
            logger.info(f"정확 매핑: {account_name} → {exact['id']}")
            return {
                "input": account_name,
                "best_match": exact,
                "confidence": 1.0,
                "candidates": [exact],
                "needs_extension": False,
                "method": "exact"
            }

        # 3. 유사도 기반 검색
        scores = []
        for elem in self.elements:
            sim = self._text_similarity(account_name, elem['label_ko'])
            if sim > 0.2:
                scores.append((sim, elem))

        scores.sort(key=lambda x: x[0], reverse=True)
        candidates = scores[:top_k]

        if not candidates:
            logger.warning(f"매핑 실패: {account_name} → 확장항목 필요")
            return {
                "input": account_name,
                "best_match": None,
                "confidence": 0.0,
                "candidates": [],
                "needs_extension": True,
                "method": "none",
                "extension_suggestion": self._suggest_extension(account_name)
            }

        best_score, best_elem = candidates[0]
        needs_ext = best_score < 0.5

        if needs_ext:
            logger.info(f"저신뢰 매핑: {account_name} → {best_elem['id']} (신뢰도: {best_score:.2f}, 확장항목 검토 필요)")
        else:
            logger.info(f"유사도 매핑: {account_name} → {best_elem['id']} (신뢰도: {best_score:.2f})")

        return {
            "input": account_name,
            "best_match": best_elem,
            "confidence": round(best_score, 4),
            "candidates": [{"score": round(s, 4), **e} for s, e in candidates],
            "needs_extension": needs_ext,
            "method": "similarity"
        }

    def map_accounts(self, account_names: list[str], top_k: int = 3) -> list[dict]:
        """복수 계정과목 일괄 매핑"""
        results = []
        for name in account_names:
            result = self.map_account(name, top_k)
            results.append(result)
        return results

    def _suggest_extension(self, account_name: str) -> dict:
        """확장항목 생성 제안"""
        # 가장 가까운 부모 요소 추정
        tokens = self._tokenize(account_name)
        parent_candidates = []
        for token in tokens:
            for elem in self.keyword_index.get(token, []):
                parent_candidates.append(elem)

        parent = parent_candidates[0] if parent_candidates else None
        ext_id = f"ext:{account_name.replace(' ', '')}"

        return {
            "extension_id": ext_id,
            "label_ko": account_name,
            "suggested_parent": parent['id'] if parent else "ifrs-full:OtherCurrentAssets",
            "reason": "표준 Taxonomy에 매칭되는 요소가 없어 확장항목 생성이 필요합니다."
        }

    def learn_mapping(self, account_name: str, taxonomy_id: str):
        """매핑 이력 학습 (사용자 피드백 반영)"""
        account_name = normalize_text(account_name)
        for elem in self.elements:
            if elem['id'] == taxonomy_id:
                self.mapping_history[account_name] = elem
                logger.info(f"매핑 학습: {account_name} → {taxonomy_id}")
                return True
        logger.warning(f"학습 실패: {taxonomy_id} 요소를 찾을 수 없음")
        return False

    def export_mapping_table(self, results: list[dict], output_path: str | Path = None) -> Path:
        """매핑 결과를 JSON 파일로 내보내기"""
        output_path = output_path or OUTPUT_DIR / f"mapping_result_{__import__('datetime').datetime.now():%Y%m%d_%H%M%S}.json"
        export_data = {
            "generated_at": str(__import__('datetime').datetime.now()),
            "total_accounts": len(results),
            "mapped_count": sum(1 for r in results if r['best_match']),
            "extension_needed": sum(1 for r in results if r['needs_extension']),
            "mappings": results
        }
        save_json(export_data, output_path)
        logger.info(f"매핑 결과 저장: {output_path}")
        return output_path

    def get_statistics(self, results: list[dict]) -> dict:
        """매핑 결과 통계"""
        total = len(results)
        mapped = sum(1 for r in results if r['best_match'])
        high_conf = sum(1 for r in results if r['confidence'] >= 0.8)
        mid_conf = sum(1 for r in results if 0.5 <= r['confidence'] < 0.8)
        low_conf = sum(1 for r in results if 0 < r['confidence'] < 0.5)
        no_match = sum(1 for r in results if r['confidence'] == 0)
        ext_needed = sum(1 for r in results if r['needs_extension'])

        return {
            "총 계정과목": total,
            "매핑 성공": mapped,
            "고신뢰 (>=0.8)": high_conf,
            "중신뢰 (0.5~0.8)": mid_conf,
            "저신뢰 (<0.5)": low_conf,
            "매핑 실패": no_match,
            "확장항목 필요": ext_needed,
            "매핑률": f"{mapped/total*100:.1f}%" if total else "N/A",
            "평균 신뢰도": f"{sum(r['confidence'] for r in results)/total:.3f}" if total else "N/A"
        }


# ── 데모 실행 ──
def demo():
    """M1 Taxonomy Mapper 데모"""
    print("\n" + "="*70)
    print("  M1. Taxonomy Mapper - 계정과목 자동 매핑 데모")
    print("="*70)

    mapper = TaxonomyMapper()

    # 테스트 계정과목 목록
    test_accounts = [
        "현금및현금성자산",        # 정확 일치
        "매출채권",              # 정확 일치
        "재고자산",              # 정확 일치
        "유형자산",              # 정확 일치
        "매출액",               # 정확 일치
        "판매비와관리비",         # 정확 일치
        "현금및현금등가물",       # 유사 매핑 (약간 다른 표현)
        "단기매출채권",          # 유사 매핑
        "기계장치",             # 확장항목 필요 가능
        "사용권자산",            # 확장항목 필요
        "리스부채",             # 확장항목 필요
        "장기선급비용",          # 확장항목 필요 가능
    ]

    results = mapper.map_accounts(test_accounts)

    # 결과 출력
    report_items = []
    for r in results:
        match_id = r['best_match']['id'].split(':')[1] if r['best_match'] else "N/A"
        report_items.append({
            "계정과목": r['input'],
            "매핑결과": match_id,
            "신뢰도": f"{r['confidence']:.2f}",
            "방식": r['method'],
            "확장필요": "Y" if r['needs_extension'] else "N"
        })

    print_report("매핑 결과", report_items, ["계정과목", "매핑결과", "신뢰도", "방식", "확장필요"])

    # 통계
    stats = mapper.get_statistics(results)
    print("[ 매핑 통계 ]")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    # 매핑 결과 저장
    output_path = mapper.export_mapping_table(results)
    print(f"\n매핑 결과 저장: {output_path}")

    # 학습 기능 데모
    print("\n[ 매핑 학습 데모 ]")
    mapper.learn_mapping("사용권자산", "ifrs-full:PropertyPlantAndEquipment")
    re_result = mapper.map_account("사용권자산")
    print(f"  학습 후 재매핑: 사용권자산 → {re_result['best_match']['id']} (신뢰도: {re_result['confidence']})")

    return results


if __name__ == "__main__":
    demo()
