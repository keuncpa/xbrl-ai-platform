"""
XBRL 공시 AI 자동화 플랫폼 - 통합 파이프라인

전체 흐름:
  재무제표 → M1(Taxonomy 매핑) → M2(iXBRL 태깅) → M3(검증) → M4(변경 추적)
  → 공시 후 → M5(재무 분석) → M6(확장항목 관리) → M1 피드백

사용 예시:
    pipeline = XBRLPipeline()
    result = pipeline.run(current_data, prior_data, period="2025-12-31")
    pipeline.run_post_disclosure(["삼성전자", "SK하이닉스", "LG전자"])
"""

import sys
from pathlib import Path
from datetime import datetime
from utils import setup_logger, save_json, OUTPUT_DIR, ensure_dirs

from m1_taxonomy_mapper import TaxonomyMapper
from m2_auto_tagger import AutoTagger
from m3_validator import Validator
from m4_change_tracker import ChangeTracker
from m5_analytics import DARTAnalytics
from m6_extension_manager import ExtensionManager

logger = setup_logger('Pipeline')


class XBRLPipeline:
    """XBRL 공시 AI 자동화 통합 파이프라인"""

    def __init__(self, dart_api_key: str = None):
        ensure_dirs()
        logger.info("="*60)
        logger.info("  XBRL 공시 AI 자동화 플랫폼 초기화")
        logger.info("="*60)

        # 모듈 초기화
        self.m1 = TaxonomyMapper()
        self.m2 = AutoTagger(taxonomy_mapper=self.m1)
        self.m3 = Validator()
        self.m4 = ChangeTracker()
        self.m5 = DARTAnalytics(api_key=dart_api_key)
        self.m6 = ExtensionManager()

        logger.info("모듈 초기화 완료: M1~M6")

    def run(self, current_data: list[dict], prior_data: list[dict] = None,
            period_end: str = "2025-12-31", period_start: str = None,
            entity: str = "SampleCorp") -> dict:
        """
        코어 파이프라인 실행: M1 → M2 → M3 → M4

        Args:
            current_data: 당기 재무제표 데이터
            prior_data: 전기 재무제표 데이터 (선택)
            period_end: 기말일
            entity: 회사명

        Returns:
            파이프라인 실행 결과 (각 모듈 결과 포함)
        """
        print("\n" + "▓"*70)
        print("  XBRL 공시 AI 자동화 파이프라인 실행")
        print("▓"*70)

        result = {
            "entity": entity,
            "period": period_end,
            "started_at": str(datetime.now()),
            "modules": {},
        }

        # ── M1: Taxonomy 매핑 ──
        print("\n" + "─"*70)
        print("  [M1] Taxonomy Mapper 실행 중...")
        print("─"*70)
        account_names = [d.get('계정과목', '') for d in current_data if d.get('계정과목')]
        mapping_results = self.m1.map_accounts(account_names)
        mapping_stats = self.m1.get_statistics(mapping_results)
        self.m1.export_mapping_table(mapping_results)

        result["modules"]["M1"] = {
            "status": "완료",
            "stats": mapping_stats,
        }
        print(f"  매핑률: {mapping_stats['매핑률']} | 평균 신뢰도: {mapping_stats['평균 신뢰도']}")

        # 확장항목을 M6에 등록
        extensions = [r for r in mapping_results if r['needs_extension']]
        if extensions:
            ext_items = [{"label": r['input'], "parent": "ifrs-full:OtherCurrentAssets"} for r in extensions]
            self.m6.add_extensions(entity, ext_items)

        # ── M2: iXBRL 태깅 ──
        print("\n" + "─"*70)
        print("  [M2] Auto Tagger 실행 중...")
        print("─"*70)
        tagged_current = self.m2.tag_financial_statement(
            current_data, period_end=period_end, period_start=period_start, entity=entity
        )
        ixbrl_path = self.m2.export_ixbrl(tagged_current, title=f"{entity} 재무상태표")
        coverage = self.m2.get_coverage_report()

        result["modules"]["M2"] = {
            "status": "완료",
            "coverage": coverage,
            "ixbrl_file": str(ixbrl_path),
        }
        print(f"  커버리지: {coverage['coverage_rate']} | iXBRL: {ixbrl_path.name}")

        # ── M3: 검증 ──
        print("\n" + "─"*70)
        print("  [M3] Validator 실행 중...")
        print("─"*70)
        tagged_prior = None
        if prior_data:
            tagged_prior = self.m2.tag_financial_statement(prior_data, period_end="2024-12-31", entity=entity)

        validation = self.m3.validate(tagged_current, prior_items=tagged_prior)
        validation_path = self.m3.export_report(validation)

        result["modules"]["M3"] = {
            "status": validation['status'],
            "errors": validation['summary']['errors'],
            "warnings": validation['summary']['warnings'],
            "report_file": str(validation_path),
        }

        # 검증 실패 시 경고
        if not validation['summary']['passed']:
            print(f"  ⚠ 검증 실패! M2 재태깅을 검토하세요.")

        # ── M4: 변경 추적 ──
        if prior_data and tagged_prior:
            print("\n" + "─"*70)
            print("  [M4] Change Tracker 실행 중...")
            print("─"*70)
            changes = self.m4.compare(tagged_prior, tagged_current)
            change_report = self.m4.generate_report(changes)
            change_path = self.m4.export_report(change_report)

            result["modules"]["M4"] = {
                "status": "완료",
                "total_changes": change_report['total_changes'],
                "material_changes": change_report['material_changes'],
                "report_file": str(change_path),
            }
        else:
            result["modules"]["M4"] = {"status": "건너뜀 (전기 데이터 없음)"}

        result["completed_at"] = str(datetime.now())

        # 최종 요약
        self._print_summary(result)
        return result

    def run_post_disclosure(self, companies: list[str], year: str = "2024") -> dict:
        """
        공시 후 분석 파이프라인: M5 → M6

        Args:
            companies: 분석 대상 기업 목록
            year: 기준 연도
        """
        print("\n" + "▓"*70)
        print("  공시 후 분석 파이프라인 (M5 → M6)")
        print("▓"*70)

        result = {"modules": {}}

        # ── M5: 재무 분석 ──
        print("\n" + "─"*70)
        print("  [M5] Analytics 실행 중...")
        print("─"*70)
        comparison = self.m5.compare_companies(companies, year)
        dashboard_path = self.m5.export_dashboard(comparison)

        result["modules"]["M5"] = {
            "status": "완료",
            "companies": companies,
            "dashboard_file": str(dashboard_path),
        }
        print(f"  대시보드: {dashboard_path.name}")

        # ── M6: 확장항목 관리 ──
        print("\n" + "─"*70)
        print("  [M6] Extension Manager 실행 중...")
        print("─"*70)

        # 샘플 확장항목 등록 (실제로는 M1 파이프라인에서 자동 수집)
        sample_extensions = {
            "삼성전자": [
                {"label": "사용권자산", "parent": "ifrs-full:NoncurrentAssets"},
                {"label": "리스부채", "parent": "ifrs-full:NoncurrentLiabilities"},
                {"label": "계약자산", "parent": "ifrs-full:CurrentAssets"},
            ],
            "SK하이닉스": [
                {"label": "사용권자산", "parent": "ifrs-full:NoncurrentAssets"},
                {"label": "리스 부채", "parent": "ifrs-full:NoncurrentLiabilities"},
                {"label": "계약자산", "parent": "ifrs-full:CurrentAssets"},
            ],
            "LG전자": [
                {"label": "사용권 자산", "parent": "ifrs-full:NoncurrentAssets"},
                {"label": "리스부채", "parent": "ifrs-full:NoncurrentLiabilities"},
                {"label": "계약 자산", "parent": "ifrs-full:CurrentAssets"},
            ],
        }
        for company in companies:
            if company in sample_extensions:
                self.m6.add_extensions(company, sample_extensions[company])

        clusters = self.m6.cluster_extensions()
        suggestions = self.m6.suggest_standardization()
        feedback = self.m6.generate_m1_feedback()
        report_path = self.m6.export_report(suggestions)

        self.m6.print_summary()

        result["modules"]["M6"] = {
            "status": "완료",
            "clusters": len(clusters),
            "standardization_candidates": len(suggestions),
            "m1_feedback_items": len(feedback),
            "report_file": str(report_path),
        }

        # M1 피드백 적용
        print(f"  M1 피드백: {len(feedback)}건 → Taxonomy Mapper 학습 적용")
        for fb in feedback[:5]:
            self.m1.learn_mapping(fb['account_name'], fb['suggested_parent'])

        return result

    def _print_summary(self, result: dict):
        """최종 요약 출력"""
        print("\n" + "▓"*70)
        print("  파이프라인 실행 결과 요약")
        print("▓"*70)
        print(f"  회사: {result['entity']} | 기간: {result['period']}")
        print()

        for module, data in result['modules'].items():
            status = data.get('status', 'N/A')
            print(f"  [{module}] {status}")

            if module == 'M1':
                stats = data.get('stats', {})
                print(f"       매핑률: {stats.get('매핑률')} | 확장항목: {stats.get('확장항목 필요')}개")
            elif module == 'M2':
                cov = data.get('coverage', {})
                print(f"       커버리지: {cov.get('coverage_rate')}")
            elif module == 'M3':
                print(f"       ERROR: {data.get('errors', 0)}개 | WARNING: {data.get('warnings', 0)}개")
            elif module == 'M4' and 'total_changes' in data:
                print(f"       변경: {data['total_changes']}건 | 중요: {data['material_changes']}건")

        print(f"\n  완료 시각: {result.get('completed_at', 'N/A')}")
        print("▓"*70 + "\n")


# ── 전체 데모 ──
def full_demo():
    """통합 파이프라인 전체 데모"""
    pipeline = XBRLPipeline()

    # ━━━ Phase 1: 코어 파이프라인 ━━━
    current_data = [
        {"계정과목": "자산총계", "금액": 5000000000, "수준": 0},
        {"계정과목": "유동자산", "금액": 2000000000, "수준": 1},
        {"계정과목": "현금및현금성자산", "금액": 500000000, "수준": 2},
        {"계정과목": "단기금융상품", "금액": 300000000, "수준": 2},
        {"계정과목": "매출채권", "금액": 800000000, "수준": 2},
        {"계정과목": "재고자산", "금액": 400000000, "수준": 2},
        {"계정과목": "비유동자산", "금액": 3000000000, "수준": 1},
        {"계정과목": "유형자산", "금액": 2000000000, "수준": 2},
        {"계정과목": "무형자산", "금액": 500000000, "수준": 2},
        {"계정과목": "투자부동산", "금액": 500000000, "수준": 2},
        {"계정과목": "부채총계", "금액": 2000000000, "수준": 0},
        {"계정과목": "유동부채", "금액": 1200000000, "수준": 1},
        {"계정과목": "매입채무", "금액": 600000000, "수준": 2},
        {"계정과목": "단기차입금", "금액": 600000000, "수준": 2},
        {"계정과목": "비유동부채", "금액": 800000000, "수준": 1},
        {"계정과목": "장기차입금", "금액": 800000000, "수준": 2},
        {"계정과목": "자본총계", "금액": 3000000000, "수준": 0},
        {"계정과목": "자본금", "금액": 1000000000, "수준": 1},
        {"계정과목": "이익잉여금", "금액": 2000000000, "수준": 1},
    ]

    prior_data = [
        {"계정과목": "자산총계", "금액": 4000000000, "수준": 0},
        {"계정과목": "유동자산", "금액": 1500000000, "수준": 1},
        {"계정과목": "현금및현금성자산", "금액": 100000000, "수준": 2},
        {"계정과목": "매출채권", "금액": 700000000, "수준": 2},
        {"계정과목": "재고자산", "금액": 700000000, "수준": 2},
        {"계정과목": "비유동자산", "금액": 2500000000, "수준": 1},
        {"계정과목": "유형자산", "금액": 2000000000, "수준": 2},
        {"계정과목": "영업권", "금액": 500000000, "수준": 2},
        {"계정과목": "부채총계", "금액": 1800000000, "수준": 0},
        {"계정과목": "유동부채", "금액": 1000000000, "수준": 1},
        {"계정과목": "비유동부채", "금액": 800000000, "수준": 1},
        {"계정과목": "자본총계", "금액": 2200000000, "수준": 0},
        {"계정과목": "자본금", "금액": 1000000000, "수준": 1},
        {"계정과목": "이익잉여금", "금액": 1200000000, "수준": 1},
    ]

    # 코어 파이프라인 실행
    core_result = pipeline.run(
        current_data=current_data,
        prior_data=prior_data,
        period_end="2025-12-31",
        entity="(주)데모코퍼레이션"
    )

    # ━━━ Phase 2: 공시 후 분석 ━━━
    post_result = pipeline.run_post_disclosure(
        companies=["삼성전자", "SK하이닉스", "LG전자"],
        year="2024"
    )

    print("\n" + "="*70)
    print("  전체 파이프라인 데모 완료!")
    print("  output/ 폴더에서 생성된 파일들을 확인하세요.")
    print("="*70)

    return core_result, post_result


if __name__ == "__main__":
    full_demo()
