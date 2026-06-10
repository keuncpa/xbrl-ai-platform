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
import os
import json
import math
from pathlib import Path
from difflib import SequenceMatcher
from collections import defaultdict
from utils import setup_logger, load_json, save_json, DATA_DIR, OUTPUT_DIR, normalize_text, print_report

logger = setup_logger('M1.TaxonomyMapper')

# 임베딩(의미 기반) 매칭은 API 키가 설정된 경우에만 활성화 (없으면 별칭+텍스트 유사도로 동작)
_EMBED_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
_EMBED_KEY = os.environ.get("OPENAI_API_KEY") or os.environ.get("EMBEDDING_API_KEY")
_EMBED_ENDPOINT = os.environ.get("EMBEDDING_ENDPOINT", "https://api.openai.com/v1/embeddings")
_TAX_EMB_CACHE = {}  # 워밍된 컨테이너 재사용용 (label -> vector)


class TaxonomyMapper:
    """계정과목 → XBRL Taxonomy 자동 매핑 엔진"""

    def __init__(self, taxonomy_path: str | Path = None, use_embeddings: bool = None):
        self.taxonomy_path = taxonomy_path or DATA_DIR / "kor_ifrs_taxonomy.json"
        self.elements = []
        self.label_index = {}       # label_ko/별칭(정규화) → element
        self.keyword_index = defaultdict(list)  # 키워드 → [elements]
        self.mapping_history = {}   # 과거 매핑 이력 (학습용)
        # 임베딩(의미 기반) 매칭: 키가 있으면 자동 활성화, 없으면 별칭+텍스트 유사도로 폴백
        self.use_embeddings = bool(_EMBED_KEY) if use_embeddings is None else use_embeddings
        self._load_taxonomy()
        if self.use_embeddings:
            logger.info(f"임베딩 매칭 활성화 (model={_EMBED_MODEL})")

    def _match_labels(self, elem: dict) -> list[str]:
        """요소의 매칭 후보 레이블 = 표준 레이블 + 별칭"""
        labels = [elem['label_ko']] + list(elem.get('aliases', []))
        # 정규화 + 중복 제거 (순서 유지)
        seen, out = set(), []
        for lbl in labels:
            n = normalize_text(lbl)
            if n and n not in seen:
                seen.add(n)
                out.append(n)
        return out

    def _load_taxonomy(self):
        """Taxonomy 로드 및 인덱스 구축 (별칭 포함)"""
        data = load_json(self.taxonomy_path)
        self.elements = data.get('elements', [])
        self.calc_rules = data.get('calculation_rules', [])

        for elem in self.elements:
            for label in self._match_labels(elem):   # 표준 레이블 + 별칭 모두 색인
                self.label_index.setdefault(label, elem)
                for token in self._tokenize(label):
                    self.keyword_index[token].append(elem)

        n_alias = sum(len(e.get('aliases', [])) for e in self.elements)
        logger.info(f"Taxonomy 로드 완료: {len(self.elements)}개 요소(별칭 {n_alias}개), {len(self.keyword_index)}개 키워드")

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

        # 3. 유사도 기반 검색 (별칭 포함: 각 요소의 표준 레이블 + 별칭 중 최고 점수)
        scores = {}
        for elem in self.elements:
            sim = max(self._text_similarity(account_name, lbl) for lbl in self._match_labels(elem))
            if sim > 0.2:
                scores[elem['id']] = (sim, elem)

        # 3-1. 임베딩(의미) 매칭 보강 — 키가 설정된 경우에만. 텍스트 점수와 max로 결합.
        method = "similarity"
        if self.use_embeddings:
            emb = self._embedding_scores(account_name)  # {elem_id: 0~1}
            if emb:
                method = "hybrid"
                for elem in self.elements:
                    ec = emb.get(elem['id'], 0.0)
                    if elem['id'] in scores:
                        prev, _ = scores[elem['id']]
                        scores[elem['id']] = (max(prev, ec), elem)
                    elif ec > 0.2:
                        scores[elem['id']] = (ec, elem)

        ranked = sorted(scores.values(), key=lambda x: x[0], reverse=True)
        candidates = ranked[:top_k]

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
            logger.info(f"{method} 매핑: {account_name} → {best_elem['id']} (신뢰도: {best_score:.2f})")

        return {
            "input": account_name,
            "best_match": best_elem,
            "confidence": round(best_score, 4),
            "candidates": [{"score": round(s, 4), **e} for s, e in candidates],
            "needs_extension": needs_ext,
            "method": method
        }

    # ── 임베딩(의미 기반) 매칭 헬퍼 ──────────────────────────────
    def _embedding_scores(self, text: str) -> dict:
        """입력명 vs 모든 요소 레이블의 코사인 유사도 → {elem_id: 0~1}. 실패 시 폴백."""
        try:
            tax = self._ensure_tax_embeddings()
            vec = self._embed([text])[0]
            return {eid: self._cos_to_conf(self._cosine(vec, ev)) for eid, ev in tax.items()}
        except Exception as ex:  # noqa: BLE001
            logger.warning(f"임베딩 매칭 실패 → 텍스트 유사도로 폴백: {ex}")
            self.use_embeddings = False
            return {}

    def _ensure_tax_embeddings(self) -> dict:
        """요소 레이블 임베딩을 1회 계산 후 캐시(컨테이너 메모리 + /tmp)."""
        cache_key = f"{_EMBED_MODEL}:{len(self.elements)}"
        if cache_key in _TAX_EMB_CACHE:
            return _TAX_EMB_CACHE[cache_key]
        import tempfile
        import hashlib
        cache_file = os.path.join(
            tempfile.gettempdir(),
            "taxemb_" + hashlib.md5(cache_key.encode()).hexdigest() + ".json"
        )
        if os.path.exists(cache_file):
            data = load_json(cache_file)
            _TAX_EMB_CACHE[cache_key] = data
            return data
        vecs = self._embed([e['label_ko'] for e in self.elements])
        data = {e['id']: vecs[i] for i, e in enumerate(self.elements)}
        try:
            with open(cache_file, "w") as f:
                json.dump(data, f)
        except Exception:  # noqa: BLE001
            pass
        _TAX_EMB_CACHE[cache_key] = data
        return data

    def _embed(self, texts: list[str]) -> list[list[float]]:
        """임베딩 API 호출 (표준 라이브러리 urllib 사용 — 외부 패키지 불필요)."""
        import urllib.request
        body = json.dumps({"model": _EMBED_MODEL, "input": texts}).encode("utf-8")
        req = urllib.request.Request(
            _EMBED_ENDPOINT, data=body,
            headers={"Authorization": f"Bearer {_EMBED_KEY}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            resp = json.loads(r.read().decode("utf-8"))
        return [d["embedding"] for d in resp["data"]]

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        return dot / (na * nb) if na and nb else 0.0

    @staticmethod
    def _cos_to_conf(cos: float) -> float:
        """문장 임베딩 코사인을 0~1 신뢰도로 스케일 (동의어 ~0.6+, 무관 ~0.2-)."""
        return max(0.0, min(1.0, (cos - 0.2) / 0.7))

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
