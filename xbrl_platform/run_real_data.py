"""
XBRL 공시 AI 자동화 플랫폼 - DART 실제 데이터 테스트
실제 상장사 재무제표를 DART API로 가져와 전체 파이프라인을 실행합니다.
"""

import os
import requests
import json
from pathlib import Path
from datetime import datetime
from utils import setup_logger, save_json, OUTPUT_DIR, ensure_dirs, parse_number

from m1_taxonomy_mapper import TaxonomyMapper
from m2_auto_tagger import AutoTagger
from m3_validator import Validator
from m4_change_tracker import ChangeTracker
from m6_extension_manager import ExtensionManager

logger = setup_logger('RealDataTest')

API_KEY = os.environ.get('DART_API_KEY', '')
DART_BASE = 'https://opendart.fss.or.kr/api'

# ── 대상 기업 ──
TARGET_COMPANIES = {
    '삼성전자':   {'corp_code': '00126380', 'stock_code': '005930'},
    'SK하이닉스': {'corp_code': '00164779', 'stock_code': '000660'},
    'LG전자':     {'corp_code': '00401731', 'stock_code': '066570'},
    '현대자동차': {'corp_code': '00164742', 'stock_code': '005380'},
}


def fetch_financial_statements(corp_code: str, year: str, fs_div: str = 'CFS') -> list[dict]:
    """DART API로 재무제표 조회"""
    if not API_KEY:
        raise SystemExit("DART_API_KEY 환경변수를 설정한 후 실행하세요. (https://opendart.fss.or.kr)")
    url = f'{DART_BASE}/fnlttSinglAcntAll.json'
    params = {
        'crtfc_key': API_KEY,
        'corp_code': corp_code,
        'bsns_year': year,
        'reprt_code': '11011',  # 사업보고서
        'fs_div': fs_div,       # CFS=연결, OFS=별도
    }

    r = requests.get(url, params=params, timeout=30)
    data = r.json()

    if data.get('status') != '000':
        logger.warning(f"DART API 오류: {data.get('message')} (corp_code={corp_code}, year={year})")
        return []

    return data.get('list', [])


def parse_bs_data(dart_items: list[dict], period: str = 'thstrm') -> list[dict]:
    """DART 응답에서 재무상태표 데이터 추출 및 파이프라인 입력 형태로 변환"""
    amount_key = f'{period}_amount'

    bs_items = [i for i in dart_items if i.get('sj_nm') == '재무상태표']

    # 총계/중분류 키워드 기반 계층 판단
    LEVEL_0_KEYWORDS = ['자산총계', '부채총계', '자본총계', '부채와자본총계']
    LEVEL_1_KEYWORDS = [
        '유동자산', '비유동자산', '유동부채', '비유동부채',
        '지배기업 소유주지분', '지배기업소유주지분', '비지배지분',
    ]

    result = []
    for item in bs_items:
        name = item.get('account_nm', '').strip()
        amount_str = item.get(amount_key, '')

        if not amount_str or amount_str.strip() == '':
            continue

        amount = parse_number(amount_str)
        if amount is None:
            continue

        # 계층 수준 판단
        if name in LEVEL_0_KEYWORDS or '총계' in name:
            level = 0
        elif name in LEVEL_1_KEYWORDS or name.startswith('유동') or name.startswith('비유동'):
            level = 1
        else:
            level = 2

        result.append({
            '계정과목': name,
            '금액': amount,
            '수준': level,
        })

    return result


def parse_is_data(dart_items: list[dict], period: str = 'thstrm') -> list[dict]:
    """DART 응답에서 손익계산서 데이터 추출"""
    amount_key = f'{period}_amount'
    is_items = [i for i in dart_items if i.get('sj_nm') in ['손익계산서', '포괄손익계산서']]

    result = []
    for item in is_items:
        name = item.get('account_nm', '').strip()
        amount_str = item.get(amount_key, '')
        if not amount_str or amount_str.strip() == '':
            continue
        amount = parse_number(amount_str)
        if amount is None:
            continue
        result.append({
            '계정과목': name,
            '금액': amount,
            '수준': 0,
        })

    return result


def run_real_pipeline():
    """실제 DART 데이터로 전체 파이프라인 실행"""
    ensure_dirs()

    print("\n" + "="*70)
    print("  XBRL 공시 AI 자동화 플랫폼 - DART 실제 데이터 테스트")
    print("="*70)
    print(f"  대상 기업: {', '.join(TARGET_COMPANIES.keys())}")
    print(f"  기준 연도: 2024 (사업보고서)")
    print("="*70)

    # 모듈 초기화
    m1 = TaxonomyMapper()
    m2 = AutoTagger(taxonomy_mapper=m1)
    m3 = Validator()
    m4 = ChangeTracker()
    m6 = ExtensionManager()

    all_results = {}

    for company_name, info in TARGET_COMPANIES.items():
        print(f"\n{'▓'*70}")
        print(f"  [{company_name}] DART 데이터 조회 중...")
        print(f"{'▓'*70}")

        # ── DART API로 재무제표 가져오기 ──
        dart_items = fetch_financial_statements(info['corp_code'], '2024')
        if not dart_items:
            print(f"  ⚠ {company_name}: 데이터 없음, 건너뜀")
            continue

        # 당기/전기 재무상태표 파싱
        current_bs = parse_bs_data(dart_items, 'thstrm')
        prior_bs = parse_bs_data(dart_items, 'frmtrm')

        # 손익계산서도 파싱
        current_is = parse_is_data(dart_items, 'thstrm')

        print(f"  당기 재무상태표: {len(current_bs)}개 항목")
        print(f"  전기 재무상태표: {len(prior_bs)}개 항목")
        print(f"  당기 손익계산서: {len(current_is)}개 항목")

        # 상위 항목 확인
        print(f"\n  [ 주요 재무데이터 (단위: 억원) ]")
        for item in current_bs[:5]:
            amt_eok = item['금액'] / 100000000
            print(f"    {item['계정과목']}: {amt_eok:,.0f}억원")
        for item in current_is[:3]:
            amt_eok = item['금액'] / 100000000
            print(f"    {item['계정과목']}: {amt_eok:,.0f}억원")

        # ── M1: Taxonomy 매핑 ──
        print(f"\n  [M1] Taxonomy Mapper 실행...")
        account_names = [d['계정과목'] for d in current_bs]
        mapping_results = m1.map_accounts(account_names)
        stats = m1.get_statistics(mapping_results)
        print(f"  매핑률: {stats['매핑률']} | 고신뢰: {stats['고신뢰 (>=0.8)']}개 | 확장항목 필요: {stats['확장항목 필요']}개")

        # 확장항목 M6에 등록
        extensions = [r for r in mapping_results if r['needs_extension']]
        if extensions:
            ext_items = [{"label": r['input']} for r in extensions]
            m6.add_extensions(company_name, ext_items)
            print(f"  확장항목 등록: {len(extensions)}개 → M6")

        # ── M2: iXBRL 태깅 ──
        print(f"\n  [M2] Auto Tagger 실행...")
        tagged_current = m2.tag_financial_statement(
            current_bs, period_end="2024-12-31", entity=company_name
        )
        ixbrl_path = m2.export_ixbrl(
            tagged_current,
            output_path=OUTPUT_DIR / f"ixbrl_{company_name}_2024.html",
            title=f"{company_name} 재무상태표 (2024)"
        )
        coverage = m2.get_coverage_report()
        print(f"  커버리지: {coverage['coverage_rate']} | 파일: {ixbrl_path.name}")

        # ── M3: 검증 ──
        print(f"\n  [M3] Validator 실행...")
        tagged_prior = None
        if prior_bs:
            tagged_prior = m2.tag_financial_statement(
                prior_bs, period_end="2023-12-31", entity=company_name
            )

        validation = m3.validate(tagged_current, prior_items=tagged_prior)
        m3.export_report(validation, OUTPUT_DIR / f"validation_{company_name}_2024.json")

        # ── M4: 변경 추적 ──
        change_report = None
        if tagged_prior:
            print(f"\n  [M4] Change Tracker 실행...")
            changes = m4.compare(tagged_prior, tagged_current)
            change_report = m4.generate_report(changes)
            m4.export_report(change_report, OUTPUT_DIR / f"changes_{company_name}_2024.json")

        all_results[company_name] = {
            "mapping_stats": stats,
            "coverage": coverage,
            "validation_status": validation['status'],
            "validation_errors": validation['summary']['errors'],
            "validation_warnings": validation['summary']['warnings'],
            "changes": change_report['total_changes'] if change_report else 0,
            "material_changes": change_report['material_changes'] if change_report else 0,
        }

    # ── M6: 확장항목 분석 ──
    print(f"\n{'▓'*70}")
    print(f"  [M6] Extension Manager - 전체 기업 확장항목 분석")
    print(f"{'▓'*70}")

    if m6.extensions:
        clusters = m6.cluster_extensions()
        suggestions = m6.suggest_standardization()
        m6.print_summary()
        m6.export_report(suggestions, OUTPUT_DIR / "extension_report_real.json")
    else:
        print("  확장항목 없음 (모든 항목이 표준 Taxonomy에 매핑됨)")

    # ── 최종 종합 요약 ──
    print(f"\n{'='*70}")
    print(f"  전체 파이프라인 실행 결과 종합")
    print(f"{'='*70}")

    for company, result in all_results.items():
        v_status = result['validation_status']
        print(f"\n  [{company}]")
        print(f"    M1 매핑률: {result['mapping_stats']['매핑률']} "
              f"(확장: {result['mapping_stats']['확장항목 필요']}개)")
        print(f"    M2 커버리지: {result['coverage']['coverage_rate']}")
        print(f"    M3 검증: [{v_status}] "
              f"ERROR={result['validation_errors']} / WARNING={result['validation_warnings']}")
        if result['changes']:
            print(f"    M4 변경: {result['changes']}건 (중요: {result['material_changes']}건)")

    print(f"\n  생성 파일 목록:")
    for f in sorted(OUTPUT_DIR.glob("*2024*")):
        print(f"    {f.name} ({f.stat().st_size:,} bytes)")

    print(f"\n{'='*70}")
    print(f"  DART 실제 데이터 테스트 완료!")
    print(f"{'='*70}\n")

    return all_results


if __name__ == "__main__":
    run_real_pipeline()
