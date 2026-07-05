"""
M2. Auto Tagger - 재무제표 → iXBRL 태그 자동 부착

기능:
  - Excel/dict 형태의 재무제표 데이터 파싱
  - M1 매핑 결과 기반 iXBRL 태그 자동 생성
  - Context 정보 (기간, 단위, 연결/별도) 자동 추론
  - iXBRL (Inline XBRL) HTML 파일 출력

사용 예시:
    tagger = AutoTagger(mapper)
    tagged = tagger.tag_financial_statement(fs_data, period="2025-12-31")
    tagger.export_ixbrl(tagged, "output.html")
"""

import html as _html
import json
from pathlib import Path
from datetime import datetime
from utils import setup_logger, save_json, OUTPUT_DIR, normalize_text, parse_number

logger = setup_logger('M2.AutoTagger')


class AutoTagger:
    """재무제표 → iXBRL 자동 태깅 엔진"""

    def __init__(self, taxonomy_mapper=None):
        """
        Args:
            taxonomy_mapper: M1 TaxonomyMapper 인스턴스 (파이프라인 연결)
        """
        self.mapper = taxonomy_mapper
        self.tagged_items = []
        self.contexts = {}

    def _create_context(self, period_end: str, period_start: str = None,
                        entity: str = "SampleCorp", scope: str = "연결") -> dict:
        """XBRL Context 생성"""
        ctx_id = f"ctx_{period_end.replace('-', '')}_{scope}"

        context = {
            "id": ctx_id,
            "entity": entity,
            "scope": scope,  # 연결 / 별도
            "period": {
                "end": period_end,
            }
        }
        if period_start:
            context["period"]["start"] = period_start
            ctx_id += "_dur"
            context["id"] = ctx_id

        self.contexts[ctx_id] = context
        return context

    def tag_financial_statement(self, fs_data: list[dict], period_end: str,
                                period_start: str = None, entity: str = "SampleCorp",
                                unit: str = "KRW", scale: int = 1) -> list[dict]:
        """
        재무제표 데이터에 iXBRL 태그 부착

        Args:
            fs_data: [{"계정과목": "자산총계", "금액": 1000000}, ...]
            period_end: 기말일 (예: "2025-12-31")
            period_start: 기초일 (손익계산서용, 예: "2025-01-01")
            entity: 회사명
            unit: 통화 단위
            scale: 단위 스케일 (1=원, 1000=천원, 1000000=백만원)

        Returns:
            태깅된 항목 리스트
        """
        if not self.mapper:
            raise ValueError("TaxonomyMapper가 연결되지 않았습니다. M1 모듈을 먼저 초기화하세요.")

        # 회사(entity) 단위 실행마다 컨텍스트 초기화 —
        # 하나의 tagger 인스턴스로 여러 회사를 순회할 때 이전 회사의
        # 컨텍스트가 다음 회사 iXBRL에 섞여 출력되는 문제 방지
        self.contexts = {}

        context = self._create_context(period_end, period_start, entity)
        tagged_items = []

        logger.info(f"태깅 시작: {len(fs_data)}개 항목, 기간: {period_end}, 회사: {entity}")

        for item in fs_data:
            account_name = item.get('계정과목', item.get('account', ''))
            amount = item.get('금액', item.get('amount', None))
            level = item.get('수준', item.get('level', 0))  # 들여쓰기 수준

            if not account_name:
                continue

            # M1 매핑 호출
            mapping = self.mapper.map_account(account_name)

            tagged = {
                "account_name": account_name,
                "amount": amount,
                "level": level,
                "taxonomy_element": None,
                "confidence": mapping['confidence'],
                "needs_extension": mapping['needs_extension'],
                "context_ref": context['id'],
                "unit_ref": unit,
                "scale": scale,
                "ixbrl_tag": None,
            }

            if mapping['best_match']:
                elem = mapping['best_match']
                tagged["taxonomy_element"] = elem['id']
                tagged["data_type"] = elem.get('data_type', 'monetary')
                tagged["balance"] = elem.get('balance')

                # iXBRL 태그 생성
                if amount is not None:
                    tagged["ixbrl_tag"] = self._generate_ixbrl_tag(
                        elem_id=elem['id'],
                        value=amount,
                        context_ref=context['id'],
                        unit_ref=unit,
                        scale=scale,
                        data_type=elem.get('data_type', 'monetary'),
                        balance=elem.get('balance'),
                        is_negative=(amount < 0) if isinstance(amount, (int, float)) else False
                    )

            tagged_items.append(tagged)

        self.tagged_items = tagged_items
        success = sum(1 for t in tagged_items if t['ixbrl_tag'])
        logger.info(f"태깅 완료: {success}/{len(tagged_items)}개 성공")

        return tagged_items

    def _generate_ixbrl_tag(self, elem_id: str, value, context_ref: str,
                            unit_ref: str, scale: int, data_type: str,
                            balance: str = None, is_negative: bool = False) -> str:
        """iXBRL 태그 문자열 생성"""
        name = elem_id.replace(':', '_')
        prefix, local = elem_id.split(':') if ':' in elem_id else ('ifrs-full', elem_id)

        if data_type == 'monetary':
            sign_attr = f' sign="-"' if is_negative else ''
            scale_attr = f' scale="{len(str(scale))-1}"' if scale > 1 else ''
            formatted_value = f"{abs(value):,.0f}" if isinstance(value, (int, float)) else str(value)

            tag = (f'<ix:nonFraction name="{elem_id}" '
                   f'contextRef="{context_ref}" '
                   f'unitRef="{unit_ref}" '
                   f'decimals="0"'
                   f'{scale_attr}{sign_attr} '
                   f'format="ixt:num-dot-decimal">'
                   f'{formatted_value}'
                   f'</ix:nonFraction>')
        elif data_type == 'perShare':
            tag = (f'<ix:nonFraction name="{elem_id}" '
                   f'contextRef="{context_ref}" '
                   f'unitRef="{unit_ref}" '
                   f'decimals="0" '
                   f'format="ixt:num-dot-decimal">'
                   f'{value}'
                   f'</ix:nonFraction>')
        else:
            tag = (f'<ix:nonNumeric name="{elem_id}" '
                   f'contextRef="{context_ref}">'
                   f'{_html.escape(str(value))}'
                   f'</ix:nonNumeric>')

        return tag

    def export_ixbrl(self, tagged_items: list[dict] = None,
                     output_path: str | Path = None, title: str = "재무상태표") -> Path:
        """iXBRL HTML 파일 생성"""
        tagged_items = tagged_items or self.tagged_items
        output_path = output_path or OUTPUT_DIR / f"ixbrl_{datetime.now():%Y%m%d_%H%M%S}.html"
        title = _html.escape(str(title))

        # iXBRL HTML 템플릿
        rows_html = []
        for item in tagged_items:
            indent = "&nbsp;" * (item['level'] * 4)
            # 계정과목명에 &, <, > 등이 포함돼도 HTML이 깨지지 않도록 이스케이프
            name = _html.escape(str(item['account_name']))
            amount = item['amount']

            if item['ixbrl_tag']:
                amount_html = item['ixbrl_tag']
                status = "tagged"
            elif amount is not None:
                amount_str = f'{amount:,.0f}' if isinstance(amount, (int, float)) else _html.escape(str(amount))
                amount_html = f'<span class="untagged">{amount_str}</span>'
                status = "untagged"
            else:
                amount_html = ""
                status = "label"

            css_class = f"level-{item['level']} {status}"
            if item['needs_extension']:
                css_class += " extension"

            rows_html.append(
                f'<tr class="{css_class}">'
                f'<td class="account">{indent}{name}</td>'
                f'<td class="amount">{amount_html}</td>'
                f'<td class="tag-id">{item.get("taxonomy_element", "")}</td>'
                f'<td class="conf">{item["confidence"]:.0%}</td>'
                f'</tr>'
            )

        # Context XML
        ctx_xml_parts = []
        for ctx_id, ctx in self.contexts.items():
            period_xml = f'<xbrli:instant>{ctx["period"]["end"]}</xbrli:instant>'
            if 'start' in ctx['period']:
                period_xml = (f'<xbrli:startDate>{ctx["period"]["start"]}</xbrli:startDate>'
                              f'<xbrli:endDate>{ctx["period"]["end"]}</xbrli:endDate>')

            ctx_xml_parts.append(
                f'<xbrli:context id="{ctx_id}">'
                f'<xbrli:entity><xbrli:identifier scheme="http://dart.fss.or.kr">{_html.escape(str(ctx["entity"]))}</xbrli:identifier></xbrli:entity>'
                f'<xbrli:period>{period_xml}</xbrli:period>'
                f'</xbrli:context>'
            )

        html = f"""<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml"
      xmlns:ix="http://www.xbrl.org/2013/inlineXBRL"
      xmlns:xbrli="http://www.xbrl.org/2003/instance"
      xmlns:ifrs-full="http://xbrl.ifrs.org/taxonomy/2024-01-01/ifrs-full"
      xmlns:iso4217="http://www.xbrl.org/2003/iso4217"
      xmlns:ixt="http://www.xbrl.org/inlineXBRL/transformation/2022-02-01">
<head>
<meta charset="UTF-8"/>
<title>{title} - iXBRL</title>
<style>
  body {{ font-family: 'Malgun Gothic', sans-serif; margin: 20px; background: #f5f5f5; }}
  .container {{ max-width: 900px; margin: 0 auto; background: white; padding: 30px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
  h1 {{ color: #1a3a5c; border-bottom: 2px solid #2c6faa; padding-bottom: 10px; }}
  .meta {{ color: #666; font-size: 0.9em; margin-bottom: 20px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ background: #1a3a5c; color: white; padding: 8px 12px; text-align: left; font-size: 0.85em; }}
  th:nth-child(2), th:nth-child(4) {{ text-align: right; }}
  td {{ padding: 6px 12px; border-bottom: 1px solid #eee; font-size: 0.9em; }}
  td.amount {{ text-align: right; font-family: 'Consolas', monospace; }}
  td.conf {{ text-align: right; font-size: 0.8em; color: #888; }}
  td.tag-id {{ font-size: 0.75em; color: #2c6faa; }}
  .level-0 {{ font-weight: bold; background: #f0f4f8; }}
  .level-1 td {{ padding-left: 20px; }}
  .level-2 td {{ padding-left: 40px; }}
  .tagged td.amount {{ color: #1e6f5c; }}
  .untagged {{ color: #c0392b; }}
  .extension td.account {{ border-left: 3px solid #e8792f; }}
  .stats {{ margin-top: 20px; padding: 15px; background: #f0f4f8; border-radius: 6px; font-size: 0.9em; }}
  ix\\:nonFraction, ix\\:nonNumeric {{ color: inherit; }}
</style>
</head>
<body>
<div class="container">
  <h1>{title}</h1>
  <div class="meta">
    Generated by XBRL AI Platform M2.AutoTagger | {datetime.now():%Y-%m-%d %H:%M}
  </div>

  <ix:header>
    <ix:hidden>
      {''.join(ctx_xml_parts)}
      <xbrli:unit id="KRW"><xbrli:measure>iso4217:KRW</xbrli:measure></xbrli:unit>
    </ix:hidden>
  </ix:header>

  <table>
    <thead>
      <tr><th>계정과목</th><th>금액</th><th>Taxonomy ID</th><th>신뢰도</th></tr>
    </thead>
    <tbody>
      {''.join(rows_html)}
    </tbody>
  </table>

  <div class="stats">
    <b>태깅 통계:</b>
    전체 {len(tagged_items)}개 항목 |
    태깅 완료 <span style="color:#1e6f5c">{sum(1 for t in tagged_items if t['ixbrl_tag'])}개</span> |
    미태깅 <span style="color:#c0392b">{sum(1 for t in tagged_items if not t['ixbrl_tag'] and t['amount'] is not None)}개</span> |
    확장항목 필요 <span style="color:#e8792f">{sum(1 for t in tagged_items if t['needs_extension'])}개</span>
  </div>
</div>
</body>
</html>"""

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)

        logger.info(f"iXBRL 파일 생성: {output_path}")
        return Path(output_path)

    def get_coverage_report(self, tagged_items: list[dict] = None) -> dict:
        """태깅 커버리지 리포트"""
        items = tagged_items or self.tagged_items
        total = len(items)
        tagged = sum(1 for t in items if t['ixbrl_tag'])
        ext = sum(1 for t in items if t['needs_extension'])
        avg_conf = sum(t['confidence'] for t in items) / total if total else 0

        return {
            "total_items": total,
            "tagged_count": tagged,
            "untagged_count": total - tagged,
            "extension_needed": ext,
            "coverage_rate": f"{tagged/total*100:.1f}%" if total else "N/A",
            "avg_confidence": f"{avg_conf:.3f}",
        }


# ── 데모 실행 ──
def demo():
    """M2 Auto Tagger 데모"""
    from m1_taxonomy_mapper import TaxonomyMapper

    print("\n" + "="*70)
    print("  M2. Auto Tagger - iXBRL 자동 태깅 데모")
    print("="*70)

    # M1 연결
    mapper = TaxonomyMapper()
    tagger = AutoTagger(taxonomy_mapper=mapper)

    # 샘플 재무상태표 데이터
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

    # 태깅 실행
    tagged = tagger.tag_financial_statement(
        fs_data=bs_data,
        period_end="2025-12-31",
        entity="(주)삼플코퍼레이션"
    )

    # iXBRL 파일 생성
    output_path = tagger.export_ixbrl(tagged, title="재무상태표")

    # 커버리지 리포트
    coverage = tagger.get_coverage_report()
    print("\n[ 태깅 커버리지 ]")
    for k, v in coverage.items():
        print(f"  {k}: {v}")

    print(f"\niXBRL 파일: {output_path}")

    return tagged


if __name__ == "__main__":
    demo()
