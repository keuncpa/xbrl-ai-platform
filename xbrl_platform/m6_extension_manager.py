"""
M6. Extension Manager - 확장항목 클러스터링 및 표준화 제안

기능:
  - 다수 기업의 확장항목(Extension) 수집 및 관리
  - 텍스트 유사도 기반 유사 확장항목 클러스터링
  - 표준화 후보 자동 추천
  - M1 Taxonomy Mapper 피드백 데이터 생성

사용 예시:
    manager = ExtensionManager()
    manager.add_extensions("삼성전자", [...])
    clusters = manager.cluster_extensions()
    suggestions = manager.suggest_standardization()
    feedback = manager.generate_m1_feedback()
"""

from collections import defaultdict
from difflib import SequenceMatcher
from datetime import datetime
from pathlib import Path
from utils import setup_logger, save_json, OUTPUT_DIR, normalize_text

logger = setup_logger('M6.ExtensionMgr')


class ExtensionManager:
    """확장항목 클러스터링 및 표준화 제안 엔진"""

    SIMILARITY_THRESHOLD = 0.6  # 유사도 기준

    def __init__(self):
        self.extensions = []  # 전체 확장항목 리스트
        self.by_company = defaultdict(list)  # 회사별 확장항목
        self.clusters = []

    def add_extensions(self, company: str, extensions: list[dict]):
        """
        기업의 확장항목 등록

        Args:
            company: 회사명
            extensions: [{"label": "사용권자산", "parent": "ifrs-full:NoncurrentAssets", ...}, ...]
        """
        for ext in extensions:
            item = {
                "company": company,
                "label": normalize_text(ext.get('label', '')),
                "label_en": ext.get('label_en', ''),
                "parent": ext.get('parent', ''),
                "category": ext.get('category', '재무상태표'),
                "data_type": ext.get('data_type', 'monetary'),
                "amount": ext.get('amount'),
            }
            self.extensions.append(item)
            self.by_company[company].append(item)

        logger.info(f"확장항목 등록: {company} - {len(extensions)}개")

    def _similarity(self, s1: str, s2: str) -> float:
        """텍스트 유사도"""
        s1 = normalize_text(s1)
        s2 = normalize_text(s2)
        if s1 == s2:
            return 1.0
        return SequenceMatcher(None, s1, s2).ratio()

    def cluster_extensions(self) -> list[dict]:
        """
        유사 확장항목 클러스터링

        Returns:
            클러스터 리스트 [{"representative": "...", "members": [...], "count": N}, ...]
        """
        if not self.extensions:
            logger.warning("등록된 확장항목이 없습니다.")
            return []

        # 이미 할당된 항목 추적
        assigned = set()
        clusters = []

        for i, ext_a in enumerate(self.extensions):
            if i in assigned:
                continue

            cluster = {
                "representative": ext_a['label'],
                "parent": ext_a['parent'],
                "category": ext_a['category'],
                "members": [ext_a],
                "companies": {ext_a['company']},
                "labels": {ext_a['label']},
            }
            assigned.add(i)

            for j, ext_b in enumerate(self.extensions):
                if j in assigned:
                    continue

                sim = self._similarity(ext_a['label'], ext_b['label'])
                if sim >= self.SIMILARITY_THRESHOLD:
                    cluster['members'].append(ext_b)
                    cluster['companies'].add(ext_b['company'])
                    cluster['labels'].add(ext_b['label'])
                    assigned.add(j)

            cluster['company_count'] = len(cluster['companies'])
            cluster['member_count'] = len(cluster['members'])
            cluster['companies'] = list(cluster['companies'])
            cluster['labels'] = list(cluster['labels'])
            clusters.append(cluster)

        # 다수 기업에서 사용하는 항목 우선 정렬
        clusters.sort(key=lambda c: c['company_count'], reverse=True)
        self.clusters = clusters

        logger.info(f"클러스터링 완료: {len(self.extensions)}개 항목 → {len(clusters)}개 클러스터")
        return clusters

    def suggest_standardization(self, min_companies: int = 2) -> list[dict]:
        """
        표준화 후보 추천

        Args:
            min_companies: 최소 기업 수 (이 이상의 기업에서 사용하는 항목만 추천)

        Returns:
            표준화 제안 리스트
        """
        if not self.clusters:
            self.cluster_extensions()

        suggestions = []
        for cluster in self.clusters:
            if cluster['company_count'] >= min_companies:
                suggestion = {
                    "proposed_label": cluster['representative'],
                    "proposed_id": f"kor-ext:{cluster['representative'].replace(' ', '')}",
                    "parent_element": cluster['parent'],
                    "category": cluster['category'],
                    "company_count": cluster['company_count'],
                    "companies": cluster['companies'],
                    "variant_labels": cluster['labels'],
                    "priority": "높음" if cluster['company_count'] >= 3 else "보통",
                    "reason": f"{cluster['company_count']}개 기업에서 유사한 확장항목을 사용 중이므로 표준 Taxonomy에 추가를 권고합니다.",
                }
                suggestions.append(suggestion)

        logger.info(f"표준화 후보: {len(suggestions)}건 (기준: {min_companies}개 기업 이상)")
        return suggestions

    def generate_m1_feedback(self) -> list[dict]:
        """
        M1 Taxonomy Mapper 피드백 데이터 생성

        Returns:
            M1에 전달할 매핑 사전 업데이트 데이터
        """
        feedback = []

        for cluster in self.clusters:
            if cluster['company_count'] >= 2:
                # 대표 레이블 → 부모 요소 매핑 정보
                for label in cluster['labels']:
                    feedback.append({
                        "account_name": label,
                        "suggested_parent": cluster['parent'],
                        "is_extension": True,
                        "frequency": cluster['company_count'],
                        "representative_label": cluster['representative'],
                    })

        logger.info(f"M1 피드백 데이터 생성: {len(feedback)}건")
        return feedback

    def export_report(self, suggestions: list[dict] = None,
                      output_path: str | Path = None) -> Path:
        """표준화 제안 리포트 저장"""
        if suggestions is None:
            suggestions = self.suggest_standardization()

        output_path = output_path or OUTPUT_DIR / f"extension_report_{datetime.now():%Y%m%d_%H%M%S}.json"

        report = {
            "generated_at": str(datetime.now()),
            "total_extensions": len(self.extensions),
            "total_companies": len(self.by_company),
            "total_clusters": len(self.clusters),
            "standardization_candidates": len(suggestions),
            "suggestions": suggestions,
            "by_company_summary": {
                company: len(exts) for company, exts in self.by_company.items()
            },
        }
        save_json(report, output_path)
        logger.info(f"확장항목 리포트 저장: {output_path}")
        return Path(output_path)

    def print_summary(self):
        """요약 출력"""
        print(f"\n{'='*70}")
        print(f"  M6 확장항목 관리 요약")
        print(f"{'='*70}")
        print(f"  총 확장항목: {len(self.extensions)}개")
        print(f"  등록 기업: {len(self.by_company)}개")
        print(f"  클러스터: {len(self.clusters)}개")

        suggestions = self.suggest_standardization()
        print(f"  표준화 후보: {len(suggestions)}건")

        if suggestions:
            print(f"\n  [ 표준화 후보 Top 5 ]")
            for s in suggestions[:5]:
                print(f"    '{s['proposed_label']}' - {s['company_count']}개 기업 사용")
                print(f"      유사 레이블: {', '.join(s['variant_labels'][:3])}")
                print(f"      부모 요소: {s['parent_element']}")
                print(f"      우선순위: {s['priority']}")
                print()

        print(f"{'='*70}\n")


# ── 데모 실행 ──
def demo():
    """M6 Extension Manager 데모"""
    print("\n" + "="*70)
    print("  M6. Extension Manager - 확장항목 표준화 제안 데모")
    print("="*70)

    manager = ExtensionManager()

    # 여러 기업의 확장항목 등록 (실제로는 M1 매핑에서 자동 수집)
    manager.add_extensions("삼성전자", [
        {"label": "사용권자산", "parent": "ifrs-full:NoncurrentAssets", "amount": 5000000000000},
        {"label": "리스부채", "parent": "ifrs-full:NoncurrentLiabilities", "amount": 4500000000000},
        {"label": "계약자산", "parent": "ifrs-full:CurrentAssets", "amount": 2000000000000},
        {"label": "계약부채", "parent": "ifrs-full:CurrentLiabilities", "amount": 1500000000000},
        {"label": "기타포괄손익누계액", "parent": "ifrs-full:Equity", "amount": 300000000000},
    ])

    manager.add_extensions("SK하이닉스", [
        {"label": "사용권자산", "parent": "ifrs-full:NoncurrentAssets", "amount": 800000000000},
        {"label": "리스 부채", "parent": "ifrs-full:NoncurrentLiabilities", "amount": 700000000000},  # 띄어쓰기 다름
        {"label": "계약자산", "parent": "ifrs-full:CurrentAssets", "amount": 500000000000},
        {"label": "파생상품자산", "parent": "ifrs-full:CurrentAssets", "amount": 200000000000},
    ])

    manager.add_extensions("LG전자", [
        {"label": "사용권 자산", "parent": "ifrs-full:NoncurrentAssets", "amount": 1200000000000},  # 띄어쓰기 다름
        {"label": "리스부채", "parent": "ifrs-full:NoncurrentLiabilities", "amount": 1100000000000},
        {"label": "계약 자산", "parent": "ifrs-full:CurrentAssets", "amount": 300000000000},  # 띄어쓰기 다름
        {"label": "계약부채", "parent": "ifrs-full:CurrentLiabilities", "amount": 400000000000},
        {"label": "기타포괄손익누계액", "parent": "ifrs-full:Equity", "amount": 150000000000},
        {"label": "파생상품자산", "parent": "ifrs-full:CurrentAssets", "amount": 100000000000},
    ])

    manager.add_extensions("현대자동차", [
        {"label": "사용권자산", "parent": "ifrs-full:NoncurrentAssets", "amount": 3000000000000},
        {"label": "리스부채", "parent": "ifrs-full:NoncurrentLiabilities", "amount": 2800000000000},
        {"label": "계약자산", "parent": "ifrs-full:CurrentAssets", "amount": 1000000000000},
        {"label": "계약부채", "parent": "ifrs-full:CurrentLiabilities", "amount": 800000000000},
        {"label": "기타포괄손익 누계액", "parent": "ifrs-full:Equity", "amount": 500000000000},
    ])

    # 클러스터링 + 표준화 제안
    clusters = manager.cluster_extensions()
    suggestions = manager.suggest_standardization(min_companies=2)

    # 요약 출력
    manager.print_summary()

    # M1 피드백 데이터
    feedback = manager.generate_m1_feedback()
    print(f"  M1 피드백 데이터: {len(feedback)}건 생성")
    for fb in feedback[:3]:
        print(f"    '{fb['account_name']}' → 부모: {fb['suggested_parent']} ({fb['frequency']}개 기업)")

    # 리포트 저장
    output_path = manager.export_report(suggestions)
    print(f"\n  리포트 저장: {output_path}")

    return suggestions


if __name__ == "__main__":
    demo()
