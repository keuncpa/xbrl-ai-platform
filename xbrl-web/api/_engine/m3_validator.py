"""
M3. Validator - XBRL 파일 자동 검증 및 오류 탐지

기능:
  - Calculation Linkbase 기반 합산 검증
  - 대차대조표 균형 검증 (자산 = 부채 + 자본)
  - 전기 대비 이상치 탐지 (비율 변동, 금액 급변)
  - 필수 항목 누락 검사
  - 검증 리포트 생성 (Pass/Fail + 오류 상세)

사용 예시:
    validator = Validator(taxonomy_path)
    report = validator.validate(tagged_items)
    report = validator.validate_with_prior(tagged_items, prior_items)
"""

import json
from pathlib import Path
from datetime import datetime
from utils import setup_logger, load_json, save_json, DATA_DIR, OUTPUT_DIR, print_report

logger = setup_logger('M3.Validator')


class ValidationError:
    """검증 오류 항목"""
    SEVERITY_ERROR = "ERROR"
    SEVERITY_WARNING = "WARNING"
    SEVERITY_INFO = "INFO"

    def __init__(self, rule: str, severity: str, message: str,
                 element: str = None, expected=None, actual=None):
        self.rule = rule
        self.severity = severity
        self.message = message
        self.element = element
        self.expected = expected
        self.actual = actual

    def to_dict(self):
        return {
            "rule": self.rule,
            "severity": self.severity,
            "message": self.message,
            "element": self.element,
            "expected": self.expected,
            "actual": self.actual,
        }


class Validator:
    """XBRL 파일 자동 검증 엔진"""

    # 필수 공시 항목 (재무상태표 기준)
    REQUIRED_ELEMENTS = [
        "ifrs-full:Assets",
        "ifrs-full:Liabilities",
        "ifrs-full:Equity",
        "ifrs-full:CurrentAssets",
        "ifrs-full:NoncurrentAssets",
    ]

    # 이상치 판단 기준 (전기 대비 변동률)
    ANOMALY_THRESHOLD_HIGH = 1.0    # 100% 이상 변동 → WARNING
    ANOMALY_THRESHOLD_EXTREME = 5.0  # 500% 이상 변동 → ERROR (실제 BS에서 극단적 변동)

    def __init__(self, taxonomy_path: str | Path = None):
        self.taxonomy_path = taxonomy_path or DATA_DIR / "kor_ifrs_taxonomy.json"
        self.calc_rules = []
        self.errors = []
        self._load_rules()

    def _load_rules(self):
        """Calculation 규칙 로드"""
        data = load_json(self.taxonomy_path)
        self.calc_rules = data.get('calculation_rules', [])
        logger.info(f"검증 규칙 로드: {len(self.calc_rules)}개 Calculation Rule")

    def validate(self, tagged_items: list[dict], prior_items: list[dict] = None) -> dict:
        """
        태깅된 항목 전체 검증

        Args:
            tagged_items: M2에서 생성한 태깅 결과 리스트
            prior_items: 전기 태깅 결과 (이상치 탐지용, 선택)

        Returns:
            검증 리포트 dict
        """
        self.errors = []

        # 값 인덱스 구축
        value_map = self._build_value_map(tagged_items)

        logger.info(f"검증 시작: {len(tagged_items)}개 항목, {len(value_map)}개 값")

        # 1. 필수 항목 검사
        self._check_required_elements(value_map)

        # 2. Calculation Linkbase 합산 검증
        self._check_calculations(value_map)

        # 3. 대차대조표 균형 검증
        self._check_balance_sheet_equation(value_map)

        # 4. 음수 값 검사
        self._check_negative_values(tagged_items)

        # 5. 태깅 완성도 검사
        self._check_tagging_completeness(tagged_items)

        # 6. 전기 대비 이상치 탐지
        if prior_items:
            prior_map = self._build_value_map(prior_items)
            self._check_anomalies(value_map, prior_map)

        # 리포트 생성
        report = self._generate_report(tagged_items)
        return report

    def _build_value_map(self, tagged_items: list[dict]) -> dict:
        """taxonomy_element → 금액 매핑 (중복 시 신뢰도 높은 값 유지)"""
        value_map = {}
        confidence_map = {}  # 각 element의 최고 신뢰도 추적
        for item in tagged_items:
            elem = item.get('taxonomy_element')
            amount = item.get('amount')
            conf = item.get('confidence', 0)
            if elem and amount is not None:
                if elem not in value_map or conf > confidence_map.get(elem, 0):
                    value_map[elem] = amount
                    confidence_map[elem] = conf
        return value_map

    def _check_required_elements(self, value_map: dict):
        """필수 항목 누락 검사"""
        for req in self.REQUIRED_ELEMENTS:
            if req not in value_map:
                self.errors.append(ValidationError(
                    rule="REQUIRED_ELEMENT",
                    severity=ValidationError.SEVERITY_ERROR,
                    message=f"필수 항목 누락: {req}",
                    element=req
                ))
            else:
                logger.info(f"필수항목 확인: {req} = {value_map[req]:,.0f}")

    def _check_calculations(self, value_map: dict):
        """Calculation Linkbase 합산 검증 (모든 하위 항목 존재 시에만 엄격 검증)"""
        for rule in self.calc_rules:
            parent_id = rule['parent']
            parent_val = value_map.get(parent_id)

            if parent_val is None:
                continue

            if rule['operation'] == 'sum':
                children_ids = rule['children']
                present_children = [c for c in children_ids if c in value_map]

                if not present_children:
                    continue

                children_sum = sum(value_map.get(c, 0) for c in children_ids)
                diff = abs(parent_val - children_sum)

                # 모든 하위 항목이 존재할 때만 엄격 검증
                all_present = len(present_children) == len(children_ids)

                if all_present and diff > 1:
                    self.errors.append(ValidationError(
                        rule="CALCULATION_SUM",
                        severity=ValidationError.SEVERITY_ERROR,
                        message=f"합산 불일치: {parent_id} ({parent_val:,.0f}) != 하위 합계 ({children_sum:,.0f}), 차이: {diff:,.0f}",
                        element=parent_id,
                        expected=parent_val,
                        actual=children_sum
                    ))
                elif all_present:
                    logger.info(f"합산 검증 통과: {parent_id}")
                elif not all_present and children_sum > abs(parent_val) * 1.01:
                    # 일부 하위 항목만 있는데 합계가 부모를 초과하면 WARNING
                    missing = [c for c in children_ids if c not in value_map]
                    self.errors.append(ValidationError(
                        rule="CALCULATION_SUM",
                        severity=ValidationError.SEVERITY_WARNING,
                        message=f"부분 합산 초과: {parent_id} ({parent_val:,.0f}) < 하위 합계 ({children_sum:,.0f}), 누락: {missing}",
                        element=parent_id,
                        expected=parent_val,
                        actual=children_sum
                    ))
                else:
                    logger.info(f"합산 부분 검증 (일부 하위 누락): {parent_id} | 존재: {len(present_children)}/{len(children_ids)}")

            elif rule['operation'] == 'subtract':
                add_ids = rule.get('children', [])
                sub_ids = rule.get('subtract', [])

                # 모든 구성요소가 존재할 때만 검증
                all_present = all(c in value_map for c in add_ids + sub_ids)
                if not all_present:
                    continue

                calc_val = sum(value_map.get(c, 0) for c in add_ids) - sum(value_map.get(c, 0) for c in sub_ids)
                diff = abs(parent_val - calc_val)
                if diff > 1:
                    self.errors.append(ValidationError(
                        rule="CALCULATION_SUBTRACT",
                        severity=ValidationError.SEVERITY_ERROR,
                        message=f"차감 계산 불일치: {parent_id} ({parent_val:,.0f}) != 계산값 ({calc_val:,.0f})",
                        element=parent_id,
                        expected=parent_val,
                        actual=calc_val
                    ))

    def _check_balance_sheet_equation(self, value_map: dict):
        """자산 = 부채 + 자본 검증 (부채와자본총계 교차검증 포함)"""
        assets = value_map.get('ifrs-full:Assets')
        liabilities = value_map.get('ifrs-full:Liabilities')
        equity = value_map.get('ifrs-full:Equity')
        liab_equity = value_map.get('ifrs-full:LiabilitiesAndEquity')

        # 검증 1: 부채와자본총계 = 자산총계
        if liab_equity is not None and assets is not None:
            diff = abs(liab_equity - assets)
            if diff > 1:
                self.errors.append(ValidationError(
                    rule="BS_EQUATION",
                    severity=ValidationError.SEVERITY_ERROR,
                    message=f"부채와자본총계({liab_equity:,.0f}) != 자산총계({assets:,.0f}), 차이: {diff:,.0f}",
                    element="BS_EQUATION",
                    expected=liab_equity,
                    actual=assets
                ))
            else:
                logger.info(f"부채와자본총계 = 자산총계 검증 통과: {liab_equity:,.0f}")

        # 검증 2: 자산 = 부채 + 자본
        if all(v is not None for v in [assets, liabilities, equity]):
            diff = abs(assets - (liabilities + equity))
            if diff > 1:
                self.errors.append(ValidationError(
                    rule="BS_EQUATION",
                    severity=ValidationError.SEVERITY_ERROR,
                    message=f"대차대조표 불균형: 자산({assets:,.0f}) != 부채({liabilities:,.0f}) + 자본({equity:,.0f}), 차이: {diff:,.0f}",
                    element="BS_EQUATION",
                    expected=assets,
                    actual=liabilities + equity
                ))
            else:
                logger.info(f"대차대조표 균형 검증 통과: {assets:,.0f} = {liabilities:,.0f} + {equity:,.0f}")

    def _check_negative_values(self, tagged_items: list[dict]):
        """부적절한 음수 값 검사"""
        positive_only = [
            'ifrs-full:Assets', 'ifrs-full:CurrentAssets', 'ifrs-full:NoncurrentAssets',
            'ifrs-full:CashAndCashEquivalents', 'ifrs-full:Inventories',
            'ifrs-full:IssuedCapital',
        ]
        for item in tagged_items:
            elem = item.get('taxonomy_element')
            amount = item.get('amount')
            if elem in positive_only and amount is not None and amount < 0:
                self.errors.append(ValidationError(
                    rule="NEGATIVE_VALUE",
                    severity=ValidationError.SEVERITY_WARNING,
                    message=f"비정상 음수: {elem} = {amount:,.0f} (양수 예상)",
                    element=elem,
                    expected=">= 0",
                    actual=amount
                ))

    def _check_tagging_completeness(self, tagged_items: list[dict]):
        """태깅 완성도 검사"""
        total = len(tagged_items)
        untagged = [t for t in tagged_items if not t.get('ixbrl_tag') and t.get('amount') is not None]
        extensions = [t for t in tagged_items if t.get('needs_extension')]

        if untagged:
            self.errors.append(ValidationError(
                rule="TAGGING_COMPLETENESS",
                severity=ValidationError.SEVERITY_WARNING,
                message=f"미태깅 항목 {len(untagged)}개: {', '.join(t['account_name'] for t in untagged[:5])}",
                expected=total,
                actual=total - len(untagged)
            ))

        if extensions:
            self.errors.append(ValidationError(
                rule="EXTENSION_NEEDED",
                severity=ValidationError.SEVERITY_INFO,
                message=f"확장항목 필요 {len(extensions)}개: {', '.join(t['account_name'] for t in extensions[:5])}",
            ))

    def _check_anomalies(self, current_map: dict, prior_map: dict):
        """전기 대비 이상치 탐지"""
        for elem_id, current_val in current_map.items():
            prior_val = prior_map.get(elem_id)
            if prior_val is None or prior_val == 0:
                continue

            change_rate = abs((current_val - prior_val) / prior_val)

            if change_rate >= self.ANOMALY_THRESHOLD_EXTREME:
                self.errors.append(ValidationError(
                    rule="ANOMALY_EXTREME",
                    severity=ValidationError.SEVERITY_WARNING,  # 이상치는 검토 항목이지 오류가 아님
                    message=f"극심 변동: {elem_id} 전기 {prior_val:,.0f} → 당기 {current_val:,.0f} (변동률: {change_rate:.0%})",
                    element=elem_id,
                    expected=prior_val,
                    actual=current_val
                ))
            elif change_rate >= self.ANOMALY_THRESHOLD_HIGH:
                self.errors.append(ValidationError(
                    rule="ANOMALY_HIGH",
                    severity=ValidationError.SEVERITY_WARNING,
                    message=f"대폭 변동: {elem_id} 전기 {prior_val:,.0f} → 당기 {current_val:,.0f} (변동률: {change_rate:.0%})",
                    element=elem_id,
                    expected=prior_val,
                    actual=current_val
                ))

    def _generate_report(self, tagged_items: list[dict]) -> dict:
        """검증 리포트 생성"""
        errors = [e for e in self.errors if e.severity == ValidationError.SEVERITY_ERROR]
        warnings = [e for e in self.errors if e.severity == ValidationError.SEVERITY_WARNING]
        infos = [e for e in self.errors if e.severity == ValidationError.SEVERITY_INFO]

        passed = len(errors) == 0
        status = "PASS" if passed else "FAIL"

        report = {
            "status": status,
            "generated_at": str(datetime.now()),
            "summary": {
                "total_items": len(tagged_items),
                "errors": len(errors),
                "warnings": len(warnings),
                "info": len(infos),
                "passed": passed,
            },
            "errors": [e.to_dict() for e in errors],
            "warnings": [e.to_dict() for e in warnings],
            "info": [e.to_dict() for e in infos],
        }

        # 콘솔 출력
        status_icon = "PASS" if passed else "FAIL"
        print(f"\n{'='*70}")
        print(f"  M3 검증 결과: [{status_icon}]")
        print(f"  ERROR: {len(errors)}개 | WARNING: {len(warnings)}개 | INFO: {len(infos)}개")
        print(f"{'='*70}")

        for e in errors:
            print(f"  [ERROR]   {e.message}")
        for w in warnings:
            print(f"  [WARNING] {w.message}")
        for i in infos:
            print(f"  [INFO]    {i.message}")
        print()

        return report

    def export_report(self, report: dict, output_path: str | Path = None) -> Path:
        """검증 리포트 JSON 저장"""
        output_path = output_path or OUTPUT_DIR / f"validation_report_{datetime.now():%Y%m%d_%H%M%S}.json"
        save_json(report, output_path)
        logger.info(f"검증 리포트 저장: {output_path}")
        return Path(output_path)


# ── 데모 실행 ──
def demo():
    """M3 Validator 데모"""
    from m1_taxonomy_mapper import TaxonomyMapper
    from m2_auto_tagger import AutoTagger

    print("\n" + "="*70)
    print("  M3. Validator - XBRL 자동 검증 데모")
    print("="*70)

    # M1 → M2 → M3 파이프라인
    mapper = TaxonomyMapper()
    tagger = AutoTagger(taxonomy_mapper=mapper)

    # 샘플 데이터 (의도적으로 합산 오류 포함)
    bs_data = [
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

    tagged = tagger.tag_financial_statement(bs_data, period_end="2025-12-31")

    # 검증 실행
    validator = Validator()
    report = validator.validate(tagged)

    # 전기 데이터로 이상치 탐지 테스트
    print("\n--- 전기 대비 이상치 탐지 ---")
    prior_data = [
        {"계정과목": "자산총계", "금액": 4000000000, "수준": 0},
        {"계정과목": "유동자산", "금액": 1500000000, "수준": 1},
        {"계정과목": "현금및현금성자산", "금액": 100000000, "수준": 2},  # 5배 증가!
        {"계정과목": "비유동자산", "금액": 2500000000, "수준": 1},
        {"계정과목": "부채총계", "금액": 1800000000, "수준": 0},
        {"계정과목": "자본총계", "금액": 2200000000, "수준": 0},
    ]
    prior_tagged = tagger.tag_financial_statement(prior_data, period_end="2024-12-31")

    report_with_prior = validator.validate(tagged, prior_items=prior_tagged)

    # 리포트 저장
    output_path = validator.export_report(report_with_prior)
    print(f"검증 리포트 저장: {output_path}")

    return report_with_prior


if __name__ == "__main__":
    demo()
