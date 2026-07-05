"""
M4. Change Tracker - XBRL 공시 변경사항 자동 추적 및 요약

기능:
  - 전기/당기 XBRL 태깅 데이터 비교 (diff)
  - 변경 유형 분류 (신규, 삭제, 금액변동, Taxonomy변경)
  - 중요성(Materiality) 기준 필터링
  - 변경사항 자연어 요약 리포트 생성

사용 예시:
    tracker = ChangeTracker()
    changes = tracker.compare(prior_tagged, current_tagged)
    report = tracker.generate_report(changes, materiality=0.05)
"""

from datetime import datetime
from pathlib import Path
from utils import setup_logger, save_json, OUTPUT_DIR, print_report

logger = setup_logger('M4.ChangeTracker')


class ChangeType:
    ADDED = "신규 추가"
    REMOVED = "삭제"
    AMOUNT_CHANGED = "금액 변동"
    TAXONOMY_CHANGED = "Taxonomy 변경"
    CONFIDENCE_CHANGED = "신뢰도 변동"


class ChangeTracker:
    """XBRL 공시 변경사항 자동 추적 엔진"""

    def __init__(self, materiality_threshold: float = 0.05):
        """
        Args:
            materiality_threshold: 중요성 기준 (기본 5%)
        """
        self.materiality = materiality_threshold

    def compare(self, prior_items: list[dict], current_items: list[dict]) -> list[dict]:
        """
        전기/당기 태깅 데이터 비교

        Args:
            prior_items: 전기 태깅 결과
            current_items: 당기 태깅 결과

        Returns:
            변경사항 리스트
        """
        # 계정과목 기준 인덱싱
        prior_map = {item['account_name']: item for item in prior_items}
        current_map = {item['account_name']: item for item in current_items}

        changes = []

        # 기준금액 (중요성 판단용): 자산총계
        base_amount = None
        for item in current_items:
            if item.get('taxonomy_element') == 'ifrs-full:Assets':
                base_amount = abs(item.get('amount', 0))
                break
        if not base_amount:
            amounts = [abs(item.get('amount', 0)) for item in current_items
                       if isinstance(item.get('amount'), (int, float)) and item.get('amount')]
            base_amount = max(amounts) if amounts else 1  # 금액이 전무한 입력에서도 ValueError 방지

        logger.info(f"변경 추적 시작: 전기 {len(prior_items)}개 / 당기 {len(current_items)}개")
        logger.info(f"중요성 기준: 자산총계 {base_amount:,.0f} x {self.materiality:.0%} = {base_amount * self.materiality:,.0f}")

        # 1. 당기에 새로 추가된 항목
        for name, current in current_map.items():
            if name not in prior_map:
                change = {
                    "type": ChangeType.ADDED,
                    "account_name": name,
                    "taxonomy_element": current.get('taxonomy_element'),
                    "prior_amount": None,
                    "current_amount": current.get('amount'),
                    "difference": current.get('amount'),
                    "change_rate": None,
                    "is_material": self._is_material(current.get('amount'), base_amount),
                }
                changes.append(change)

        # 2. 전기에 있었지만 당기에 없는 항목
        for name, prior in prior_map.items():
            if name not in current_map:
                change = {
                    "type": ChangeType.REMOVED,
                    "account_name": name,
                    "taxonomy_element": prior.get('taxonomy_element'),
                    "prior_amount": prior.get('amount'),
                    "current_amount": None,
                    "difference": -prior.get('amount') if prior.get('amount') else None,
                    "change_rate": -1.0,
                    "is_material": self._is_material(prior.get('amount'), base_amount),
                }
                changes.append(change)

        # 3. 양쪽에 있는 항목: 금액/Taxonomy 변경 검사
        for name in set(prior_map.keys()) & set(current_map.keys()):
            prior = prior_map[name]
            current = current_map[name]

            prior_amt = prior.get('amount')
            current_amt = current.get('amount')
            prior_tax = prior.get('taxonomy_element')
            current_tax = current.get('taxonomy_element')

            # Taxonomy 변경
            if prior_tax != current_tax:
                changes.append({
                    "type": ChangeType.TAXONOMY_CHANGED,
                    "account_name": name,
                    "taxonomy_element": current_tax,
                    "prior_taxonomy": prior_tax,
                    "prior_amount": prior_amt,
                    "current_amount": current_amt,
                    "difference": None,
                    "change_rate": None,
                    "is_material": True,
                })

            # 금액 변경
            if prior_amt is not None and current_amt is not None and prior_amt != current_amt:
                diff = current_amt - prior_amt
                rate = diff / abs(prior_amt) if prior_amt != 0 else float('inf')

                changes.append({
                    "type": ChangeType.AMOUNT_CHANGED,
                    "account_name": name,
                    "taxonomy_element": current_tax,
                    "prior_amount": prior_amt,
                    "current_amount": current_amt,
                    "difference": diff,
                    "change_rate": round(rate, 4),
                    "is_material": self._is_material(abs(diff), base_amount),
                })

        # 중요성 순 정렬
        changes.sort(key=lambda c: abs(c.get('difference') or 0), reverse=True)
        logger.info(f"변경사항 {len(changes)}개 감지 (중요 변동: {sum(1 for c in changes if c['is_material'])}개)")

        return changes

    def _is_material(self, amount, base_amount) -> bool:
        """중요성 판단"""
        if amount is None or base_amount is None or base_amount == 0:
            return False
        return abs(amount) / abs(base_amount) >= self.materiality

    def generate_report(self, changes: list[dict], material_only: bool = False) -> dict:
        """변경사항 리포트 생성"""
        if material_only:
            changes = [c for c in changes if c['is_material']]

        # 유형별 분류
        by_type = {}
        for c in changes:
            t = c['type']
            by_type.setdefault(t, []).append(c)

        # 자연어 요약 생성
        summary_lines = self._generate_summary(changes, by_type)

        report = {
            "generated_at": str(datetime.now()),
            "materiality_threshold": f"{self.materiality:.0%}",
            "total_changes": len(changes),
            "material_changes": sum(1 for c in changes if c['is_material']),
            "by_type": {t: len(items) for t, items in by_type.items()},
            "summary": summary_lines,
            "changes": changes,
        }

        # 콘솔 출력
        print(f"\n{'='*70}")
        print(f"  M4 변경 추적 리포트")
        print(f"{'='*70}")
        print(f"  총 변경: {len(changes)}개 | 중요 변동: {report['material_changes']}개")
        print(f"  중요성 기준: {self.materiality:.0%}")
        print(f"{'─'*70}")

        for t, items in by_type.items():
            print(f"\n  [{t}] ({len(items)}건)")
            for item in items[:5]:
                mat_flag = " ★" if item['is_material'] else ""
                if item['type'] == ChangeType.AMOUNT_CHANGED:
                    rate = f" ({item['change_rate']:+.0%})" if item['change_rate'] else ""
                    print(f"    {item['account_name']}: {item['prior_amount']:,.0f} → {item['current_amount']:,.0f} "
                          f"(차이: {item['difference']:+,.0f}{rate}){mat_flag}")
                elif item['type'] == ChangeType.ADDED:
                    print(f"    {item['account_name']}: {item['current_amount']:,.0f} (신규){mat_flag}")
                elif item['type'] == ChangeType.REMOVED:
                    print(f"    {item['account_name']}: {item['prior_amount']:,.0f} (삭제){mat_flag}")
                elif item['type'] == ChangeType.TAXONOMY_CHANGED:
                    print(f"    {item['account_name']}: {item.get('prior_taxonomy')} → {item['taxonomy_element']}{mat_flag}")

        print(f"\n{'─'*70}")
        print("  [ 자연어 요약 ]")
        for line in summary_lines:
            print(f"  {line}")
        print(f"{'='*70}\n")

        return report

    def _generate_summary(self, changes: list[dict], by_type: dict) -> list[str]:
        """변경사항 자연어 요약"""
        lines = []

        # 전체 요약
        material = [c for c in changes if c['is_material']]
        lines.append(f"당기 재무제표에서 총 {len(changes)}건의 변경이 감지되었으며, 이 중 {len(material)}건이 중요한 변동입니다.")

        # 금액 변동 요약
        amount_changes = by_type.get(ChangeType.AMOUNT_CHANGED, [])
        material_increases = [c for c in amount_changes if c['is_material'] and (c.get('difference', 0) or 0) > 0]
        material_decreases = [c for c in amount_changes if c['is_material'] and (c.get('difference', 0) or 0) < 0]

        if material_increases:
            top = material_increases[0]
            lines.append(
                f"가장 큰 증가 항목은 '{top['account_name']}'으로, "
                f"전기 대비 {abs(top['difference']):,.0f}원({abs(top.get('change_rate', 0)):.0%}) 증가했습니다."
            )

        if material_decreases:
            top = sorted(material_decreases, key=lambda c: c.get('difference', 0))[0]
            lines.append(
                f"가장 큰 감소 항목은 '{top['account_name']}'으로, "
                f"전기 대비 {abs(top['difference']):,.0f}원({abs(top.get('change_rate', 0)):.0%}) 감소했습니다."
            )

        # 신규/삭제 항목
        added = by_type.get(ChangeType.ADDED, [])
        removed = by_type.get(ChangeType.REMOVED, [])
        if added:
            names = ', '.join(c['account_name'] for c in added[:3])
            lines.append(f"신규 추가된 항목: {names}" + (f" 외 {len(added)-3}건" if len(added) > 3 else ""))
        if removed:
            names = ', '.join(c['account_name'] for c in removed[:3])
            lines.append(f"삭제된 항목: {names}" + (f" 외 {len(removed)-3}건" if len(removed) > 3 else ""))

        return lines

    def export_report(self, report: dict, output_path: str | Path = None) -> Path:
        """리포트 JSON 저장"""
        output_path = output_path or OUTPUT_DIR / f"change_report_{datetime.now():%Y%m%d_%H%M%S}.json"
        save_json(report, output_path)
        logger.info(f"변경 리포트 저장: {output_path}")
        return Path(output_path)


# ── 데모 실행 ──
def demo():
    """M4 Change Tracker 데모"""
    from m1_taxonomy_mapper import TaxonomyMapper
    from m2_auto_tagger import AutoTagger

    print("\n" + "="*70)
    print("  M4. Change Tracker - 변경사항 추적 데모")
    print("="*70)

    mapper = TaxonomyMapper()
    tagger = AutoTagger(taxonomy_mapper=mapper)

    # 전기 데이터
    prior_data = [
        {"계정과목": "자산총계", "금액": 4000000000, "수준": 0},
        {"계정과목": "유동자산", "금액": 1500000000, "수준": 1},
        {"계정과목": "현금및현금성자산", "금액": 100000000, "수준": 2},
        {"계정과목": "매출채권", "금액": 700000000, "수준": 2},
        {"계정과목": "재고자산", "금액": 700000000, "수준": 2},
        {"계정과목": "비유동자산", "금액": 2500000000, "수준": 1},
        {"계정과목": "유형자산", "금액": 2000000000, "수준": 2},
        {"계정과목": "영업권", "금액": 500000000, "수준": 2},  # 당기에 삭제
        {"계정과목": "부채총계", "금액": 1800000000, "수준": 0},
        {"계정과목": "자본총계", "금액": 2200000000, "수준": 0},
    ]

    # 당기 데이터
    current_data = [
        {"계정과목": "자산총계", "금액": 5000000000, "수준": 0},
        {"계정과목": "유동자산", "금액": 2000000000, "수준": 1},
        {"계정과목": "현금및현금성자산", "금액": 500000000, "수준": 2},  # 5배 증가!
        {"계정과목": "매출채권", "금액": 800000000, "수준": 2},
        {"계정과목": "재고자산", "금액": 400000000, "수준": 2},  # 43% 감소
        {"계정과목": "단기금융상품", "금액": 300000000, "수준": 2},  # 신규!
        {"계정과목": "비유동자산", "금액": 3000000000, "수준": 1},
        {"계정과목": "유형자산", "금액": 2500000000, "수준": 2},
        {"계정과목": "투자부동산", "금액": 500000000, "수준": 2},  # 신규!
        {"계정과목": "부채총계", "금액": 2000000000, "수준": 0},
        {"계정과목": "자본총계", "금액": 3000000000, "수준": 0},
    ]

    prior_tagged = tagger.tag_financial_statement(prior_data, period_end="2024-12-31")
    current_tagged = tagger.tag_financial_statement(current_data, period_end="2025-12-31")

    # 변경 추적
    tracker = ChangeTracker(materiality_threshold=0.05)
    changes = tracker.compare(prior_tagged, current_tagged)
    report = tracker.generate_report(changes)

    # 저장
    output_path = tracker.export_report(report)
    print(f"변경 리포트 저장: {output_path}")

    return report


if __name__ == "__main__":
    demo()
