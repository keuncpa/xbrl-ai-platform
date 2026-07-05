"""
M5. Analytics - DART XBRL 데이터 기반 재무 분석 대시보드

기능:
  - DART Open API 연동 (기업 검색, 재무제표 조회)
  - 주요 재무비율 자동 산출
  - 동일 산업 기업 간 비교 분석
  - 시계열 트렌드 분석
  - HTML 대시보드 리포트 생성

사용 예시:
    analytics = DARTAnalytics(api_key="YOUR_DART_API_KEY")
    data = analytics.get_financial_data("삼성전자", "2024")
    ratios = analytics.calculate_ratios(data)
    analytics.export_dashboard([company1, company2], "dashboard.html")

참고: DART API 키는 https://opendart.fss.or.kr 에서 무료 발급
"""

import json
from datetime import datetime
from pathlib import Path
from utils import setup_logger, save_json, OUTPUT_DIR

logger = setup_logger('M5.Analytics')


class FinancialRatios:
    """재무비율 계산기"""

    @staticmethod
    def calculate(data: dict) -> dict:
        """
        재무데이터로부터 주요 재무비율 산출

        Args:
            data: {"자산총계": ..., "부채총계": ..., "매출액": ..., ...}

        Returns:
            비율 dict
        """
        def safe_div(a, b):
            if b and b != 0:
                return round(a / b, 4)
            return None

        assets = data.get('자산총계', 0)
        liabilities = data.get('부채총계', 0)
        equity = data.get('자본총계', 0)
        current_assets = data.get('유동자산', 0)
        current_liabilities = data.get('유동부채', 0)
        revenue = data.get('매출액', 0)
        cost_of_sales = data.get('매출원가', 0)
        gross_profit = data.get('매출총이익', 0)
        operating_income = data.get('영업이익', 0)
        net_income = data.get('당기순이익', 0)
        inventories = data.get('재고자산', 0)
        receivables = data.get('매출채권', 0)

        ratios = {
            # 안정성 비율
            "부채비율": safe_div(liabilities, equity),
            "유동비율": safe_div(current_assets, current_liabilities),
            "자기자본비율": safe_div(equity, assets),

            # 수익성 비율
            "매출총이익률": safe_div(gross_profit, revenue),
            "영업이익률": safe_div(operating_income, revenue),
            "순이익률": safe_div(net_income, revenue),
            "ROA": safe_div(net_income, assets),
            "ROE": safe_div(net_income, equity),

            # 활동성 비율
            "총자산회전율": safe_div(revenue, assets),
            "재고자산회전율": safe_div(cost_of_sales, inventories) if inventories else None,
            "매출채권회전율": safe_div(revenue, receivables) if receivables else None,
        }

        return ratios

    @staticmethod
    def format_ratio(name: str, value) -> str:
        """비율 포맷팅"""
        if value is None:
            return "N/A"
        if name in ["부채비율", "유동비율"]:
            return f"{value*100:.1f}%"
        elif name in ["매출총이익률", "영업이익률", "순이익률", "ROA", "ROE", "자기자본비율"]:
            return f"{value*100:.2f}%"
        elif name in ["총자산회전율", "재고자산회전율", "매출채권회전율"]:
            return f"{value:.2f}회"
        return f"{value:.4f}"


class DARTAnalytics:
    """DART 데이터 기반 재무 분석 엔진"""

    DART_BASE_URL = "https://opendart.fss.or.kr/api"

    def __init__(self, api_key: str = None):
        """
        Args:
            api_key: DART Open API 키 (없으면 샘플 데이터 사용)
        """
        self.api_key = api_key
        self.ratio_calc = FinancialRatios()

        if not api_key:
            logger.info("DART API 키 미설정 → 샘플 데이터 모드로 실행")

    def get_financial_data(self, company_name: str, year: str = "2024") -> dict:
        """
        기업 재무데이터 조회

        실제 API 연동 시: DART Open API /api/fnlttSinglAcntAll.json 호출
        API 미설정 시: 샘플 데이터 반환
        """
        if self.api_key:
            return self._fetch_from_dart(company_name, year)
        else:
            return self._get_sample_data(company_name, year)

    def _fetch_from_dart(self, company_name: str, year: str) -> dict:
        """DART API 호출 자리 (실호출은 미구현 — run_real_data.py 참고).

        NOTE: M5 데모는 내장 샘플 데이터로 동작합니다. 실제 DART 연동은
        run_real_data.py 의 fetch_financial_statements() 패턴으로 확장 가능합니다.
        """
        logger.warning("M5 실제 DART 호출은 미구현 상태 → 샘플 데이터로 대체합니다.")
        try:
            import requests

            # 1. 기업 코드 조회 (실제 구현 시)
            # corp_code = self._search_company(company_name)

            # 2. 재무제표 조회
            # url = f"{self.DART_BASE_URL}/fnlttSinglAcntAll.json"
            # params = {
            #     "crtfc_key": self.api_key,
            #     "corp_code": corp_code,
            #     "bsns_year": year,
            #     "reprt_code": "11011",  # 사업보고서
            #     "fs_div": "CFS",  # 연결재무제표
            # }
            # response = requests.get(url, params=params)
            # return self._parse_dart_response(response.json())

            logger.info(f"DART API 호출: {company_name} ({year})")
            return self._get_sample_data(company_name, year)

        except Exception as e:
            logger.error(f"DART API 호출 실패: {e}")
            return self._get_sample_data(company_name, year)

    def _get_sample_data(self, company_name: str, year: str) -> dict:
        """샘플 데이터 (데모용)"""
        samples = {
            "삼성전자": {
                "회사명": "삼성전자",
                "연도": year,
                "산업": "전자/반도체",
                "자산총계": 455000000000000,
                "유동자산": 215000000000000,
                "현금및현금성자산": 65000000000000,
                "매출채권": 40000000000000,
                "재고자산": 55000000000000,
                "비유동자산": 240000000000000,
                "유형자산": 170000000000000,
                "부채총계": 95000000000000,
                "유동부채": 70000000000000,
                "비유동부채": 25000000000000,
                "자본총계": 360000000000000,
                "매출액": 300000000000000,
                "매출원가": 195000000000000,
                "매출총이익": 105000000000000,
                "판매비와관리비": 55000000000000,
                "영업이익": 50000000000000,
                "당기순이익": 40000000000000,
            },
            "SK하이닉스": {
                "회사명": "SK하이닉스",
                "연도": year,
                "산업": "전자/반도체",
                "자산총계": 80000000000000,
                "유동자산": 30000000000000,
                "현금및현금성자산": 8000000000000,
                "매출채권": 8000000000000,
                "재고자산": 10000000000000,
                "비유동자산": 50000000000000,
                "유형자산": 42000000000000,
                "부채총계": 30000000000000,
                "유동부채": 18000000000000,
                "비유동부채": 12000000000000,
                "자본총계": 50000000000000,
                "매출액": 66000000000000,
                "매출원가": 40000000000000,
                "매출총이익": 26000000000000,
                "판매비와관리비": 8000000000000,
                "영업이익": 18000000000000,
                "당기순이익": 14000000000000,
            },
            "LG전자": {
                "회사명": "LG전자",
                "연도": year,
                "산업": "전자/반도체",
                "자산총계": 55000000000000,
                "유동자산": 22000000000000,
                "현금및현금성자산": 5000000000000,
                "매출채권": 7000000000000,
                "재고자산": 8000000000000,
                "비유동자산": 33000000000000,
                "유형자산": 18000000000000,
                "부채총계": 32000000000000,
                "유동부채": 22000000000000,
                "비유동부채": 10000000000000,
                "자본총계": 23000000000000,
                "매출액": 85000000000000,
                "매출원가": 65000000000000,
                "매출총이익": 20000000000000,
                "판매비와관리비": 15000000000000,
                "영업이익": 5000000000000,
                "당기순이익": 2000000000000,
            },
        }

        data = samples.get(company_name)
        if not data:
            logger.warning(f"샘플 데이터 없음: {company_name} → 기본 데이터 사용")
            data = {
                "회사명": company_name,
                "연도": year,
                "산업": "기타",
                "자산총계": 1000000000000,
                "유동자산": 400000000000,
                "비유동자산": 600000000000,
                "부채총계": 400000000000,
                "유동부채": 250000000000,
                "비유동부채": 150000000000,
                "자본총계": 600000000000,
                "매출액": 800000000000,
                "매출원가": 600000000000,
                "매출총이익": 200000000000,
                "영업이익": 80000000000,
                "당기순이익": 50000000000,
            }
        return data

    def analyze_company(self, company_name: str, year: str = "2024") -> dict:
        """단일 기업 종합 분석"""
        data = self.get_financial_data(company_name, year)
        ratios = self.ratio_calc.calculate(data)

        analysis = {
            "company": company_name,
            "year": year,
            "financial_data": data,
            "ratios": ratios,
            "formatted_ratios": {k: self.ratio_calc.format_ratio(k, v) for k, v in ratios.items()},
        }

        return analysis

    def compare_companies(self, company_names: list[str], year: str = "2024") -> dict:
        """복수 기업 비교 분석"""
        analyses = []
        for name in company_names:
            analysis = self.analyze_company(name, year)
            analyses.append(analysis)

        # 비교 테이블 구성
        ratio_names = list(analyses[0]['ratios'].keys())
        comparison = {
            "companies": company_names,
            "year": year,
            "analyses": analyses,
            "comparison_table": {},
        }

        for ratio_name in ratio_names:
            values = {}
            for a in analyses:
                values[a['company']] = {
                    "value": a['ratios'].get(ratio_name),
                    "formatted": a['formatted_ratios'].get(ratio_name, "N/A"),
                }
            comparison["comparison_table"][ratio_name] = values

        return comparison

    def export_dashboard(self, comparison: dict, output_path: str | Path = None) -> Path:
        """HTML 대시보드 생성"""
        output_path = output_path or OUTPUT_DIR / f"dashboard_{datetime.now():%Y%m%d_%H%M%S}.html"

        companies = comparison['companies']
        table = comparison['comparison_table']

        # 비율 테이블 HTML
        header_html = ''.join(f'<th>{c}</th>' for c in companies)
        rows_html = []

        ratio_categories = {
            "안정성": ["부채비율", "유동비율", "자기자본비율"],
            "수익성": ["매출총이익률", "영업이익률", "순이익률", "ROA", "ROE"],
            "활동성": ["총자산회전율", "재고자산회전율", "매출채권회전율"],
        }

        for cat_name, ratio_names in ratio_categories.items():
            rows_html.append(f'<tr class="category"><td colspan="{len(companies)+1}">{cat_name} 비율</td></tr>')
            for rn in ratio_names:
                vals = table.get(rn, {})
                cells = []
                raw_values = []
                for c in companies:
                    v = vals.get(c, {})
                    cells.append(v.get('formatted', 'N/A'))
                    raw_values.append(v.get('value'))

                # 최우량값 하이라이트 — 부채비율은 낮을수록 양호하므로 최소값을 강조
                LOWER_IS_BETTER = {"부채비율"}
                valid_vals = [(i, v) for i, v in enumerate(raw_values) if v is not None]
                if not valid_vals:
                    best_idx = -1
                elif rn in LOWER_IS_BETTER:
                    best_idx = min(valid_vals, key=lambda x: x[1])[0]
                else:
                    best_idx = max(valid_vals, key=lambda x: x[1])[0]

                cells_html = ''
                for i, cell in enumerate(cells):
                    cls = ' class="best"' if i == best_idx else ''
                    cells_html += f'<td{cls}>{cell}</td>'

                rows_html.append(f'<tr><td class="ratio-name">{rn}</td>{cells_html}</tr>')

        # 재무 규모 비교
        scale_rows = []
        for metric in ["자산총계", "매출액", "영업이익", "당기순이익"]:
            cells = []
            for a in comparison['analyses']:
                val = a['financial_data'].get(metric, 0)
                cells.append(f'<td>{val/1e12:,.1f}조</td>')
            scale_rows.append(f'<tr><td class="ratio-name">{metric}</td>{"".join(cells)}</tr>')

        html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>재무 비교 분석 대시보드</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Malgun Gothic', sans-serif; background: #f5f7fa; padding: 20px; }}
  .dashboard {{ max-width: 1000px; margin: 0 auto; }}
  .header {{ background: linear-gradient(135deg, #1a3a5c, #2c6faa); color: white; padding: 30px; border-radius: 12px 12px 0 0; }}
  .header h1 {{ font-size: 1.5em; margin-bottom: 5px; }}
  .header .meta {{ font-size: 0.85em; opacity: 0.8; }}
  .card {{ background: white; border-radius: 8px; padding: 20px; margin: 15px 0; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
  .card h2 {{ color: #1a3a5c; font-size: 1.1em; margin-bottom: 12px; border-left: 4px solid #2c6faa; padding-left: 10px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.9em; }}
  th {{ background: #1a3a5c; color: white; padding: 10px 12px; text-align: right; }}
  th:first-child {{ text-align: left; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #eee; text-align: right; }}
  td:first-child {{ text-align: left; }}
  .ratio-name {{ font-weight: 500; color: #333; }}
  .category td {{ background: #f0f4f8; font-weight: bold; color: #1a3a5c; font-size: 0.85em; letter-spacing: 1px; }}
  .best {{ color: #1e6f5c; font-weight: bold; }}
  .summary {{ background: #f0f4f8; padding: 15px; border-radius: 6px; margin-top: 15px; font-size: 0.9em; line-height: 1.6; }}
  .footer {{ text-align: center; color: #999; font-size: 0.8em; margin-top: 20px; }}
</style>
</head>
<body>
<div class="dashboard">
  <div class="header">
    <h1>재무 비교 분석 대시보드</h1>
    <div class="meta">
      {comparison['year']}년 기준 | {', '.join(companies)} |
      Generated by XBRL AI Platform M5.Analytics | {datetime.now():%Y-%m-%d %H:%M}
    </div>
  </div>

  <div class="card">
    <h2>재무 규모 비교</h2>
    <table>
      <thead><tr><th>항목</th>{header_html}</tr></thead>
      <tbody>{''.join(scale_rows)}</tbody>
    </table>
  </div>

  <div class="card">
    <h2>주요 재무비율 비교</h2>
    <table>
      <thead><tr><th>비율</th>{header_html}</tr></thead>
      <tbody>{''.join(rows_html)}</tbody>
    </table>
    <div class="summary">
      <b>분석 요약:</b> {companies[0]}이 자산 규모에서 가장 크며,
      수익성 지표(ROE, 영업이익률) 기준으로 비교 분석한 결과입니다.
      녹색 굵은 글씨가 각 비율의 최고 성과 기업입니다.
    </div>
  </div>

  <div class="footer">
    XBRL AI 자동화 플랫폼 M5.Analytics Module v0.1<br/>
    데이터 출처: DART Open API (샘플 데이터)
  </div>
</div>
</body>
</html>"""

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)

        logger.info(f"대시보드 생성: {output_path}")
        return Path(output_path)


# ── 데모 실행 ──
def demo():
    """M5 Analytics 데모"""
    print("\n" + "="*70)
    print("  M5. Analytics - 재무 비교 분석 데모")
    print("="*70)

    analytics = DARTAnalytics()  # API 키 없이 샘플 모드

    # 단일 기업 분석
    print("\n[ 삼성전자 재무비율 ]")
    analysis = analytics.analyze_company("삼성전자", "2024")
    for name, formatted in analysis['formatted_ratios'].items():
        print(f"  {name}: {formatted}")

    # 기업 비교 분석
    print("\n[ 기업 비교 분석 ]")
    companies = ["삼성전자", "SK하이닉스", "LG전자"]
    comparison = analytics.compare_companies(companies, "2024")

    # 대시보드 생성
    output_path = analytics.export_dashboard(comparison)
    print(f"\n대시보드 파일: {output_path}")

    # 비교 결과 JSON 저장
    json_path = OUTPUT_DIR / "comparison_result.json"
    save_json({
        "companies": companies,
        "year": "2024",
        "ratios": {c: comparison['analyses'][i]['formatted_ratios']
                   for i, c in enumerate(companies)}
    }, json_path)
    print(f"비교 결과 JSON: {json_path}")

    return comparison


if __name__ == "__main__":
    demo()
