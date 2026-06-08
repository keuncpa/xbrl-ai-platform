---
name: ixbrl-auto-tagging
description: |
  재무제표 데이터를 KOR-IFRS XBRL Taxonomy에 자동 매핑하고 iXBRL(Inline XBRL) 파일을 생성하는 스킬.
  계정과목명 → Taxonomy 요소 자동 매핑(M1), iXBRL 태그 부착(M2), Calculation Linkbase 검증(M3)까지 원스톱 수행.
  MANDATORY TRIGGERS: XBRL 태깅, iXBRL, Inline XBRL, Taxonomy 매핑, 계정과목 매핑, XBRL 변환, xbrl tagging, 재무제표 태깅, 공시 태깅, Taxonomy mapping, XBRL 파일 생성, 자동 태깅, auto tagging, XBRL 자동화.
  사용자가 "XBRL 태깅해줘", "iXBRL 만들어줘", "계정과목 매핑", "Taxonomy에 매핑", "재무제표를 XBRL로 변환" 등을 말하면 반드시 이 스킬을 사용할 것.
  한국어로 작업한다.
---

# iXBRL 자동 태깅 스킬

## 개요

재무제표 데이터(엑셀, DART API, 또는 직접 입력)를 입력받아 KOR-IFRS XBRL Taxonomy에 자동 매핑하고, 검증을 거쳐 공시 가능한 iXBRL HTML 파일을 생성하는 종합 태깅 스킬이다.

## 전체 파이프라인

```
[재무제표 데이터 입력]
    ↓
[M1] Taxonomy Mapper — 계정과목 → XBRL 요소 매핑
    ↓
[M2] Auto Tagger — iXBRL 태그 생성 + HTML 출력
    ↓
[M3] Validator — Calculation Linkbase 검증
    ↓
[iXBRL HTML 파일 출력]
```

---

## STEP 1: 입력 데이터 준비

### 지원 입력 형식
1. **엑셀 파일**: 계정과목 + 금액 컬럼이 있는 .xlsx
2. **DART API 데이터**: dart-financial-analysis 스킬로 조회한 데이터
3. **직접 입력**: 사용자가 대화에서 제공하는 재무 데이터

### 필수 데이터 구조
```python
[
    {"계정과목": "자산총계", "금액": 514531948000000, "수준": 0},
    {"계정과목": "유동자산", "금액": 227062266000000, "수준": 1},
    {"계정과목": "현금및현금성자산", "금액": 53705579000000, "수준": 2},
    ...
]
```
- `계정과목`: 한글 계정과목명 (필수)
- `금액`: 원화 금액 (필수)
- `수준`: 계층 수준 0=총계, 1=중분류, 2=세분류 (선택, 자동 추정 가능)

---

## STEP 2: M1 — Taxonomy 자동 매핑

### 매핑 전략 (우선순위 순)
1. **학습 이력 매핑**: 이전에 사용자가 확인한 매핑 기록이 있으면 재사용 (신뢰도 1.0)
2. **정확 일치**: Taxonomy의 `label_ko`와 계정과목명이 정확히 일치 (신뢰도 1.0)
3. **유사도 매핑**: SequenceMatcher(60%) + Jaccard(40%) 가중 유사도 (신뢰도 0~1)

### KOR-IFRS Taxonomy 주요 요소
| 계정과목 | Taxonomy ID | 분류 |
|---------|-------------|------|
| 자산총계 | ifrs-full:Assets | BS |
| 유동자산 | ifrs-full:CurrentAssets | BS |
| 비유동자산 | ifrs-full:NoncurrentAssets | BS |
| 부채총계 | ifrs-full:Liabilities | BS |
| 자본총계 | ifrs-full:Equity | BS |
| 매출액 | ifrs-full:Revenue | IS |
| 영업이익 | ifrs-full:OperatingIncome | IS |
| 당기순이익 | ifrs-full:ProfitLoss | IS |

Taxonomy 데이터: `xbrl_platform/data/kor_ifrs_taxonomy.json` (87개 요소)

### 확장항목(Extension) 처리
- 신뢰도 < 0.5이면 확장항목(Extension)으로 분류
- 확장항목 ID 형식: `ext:계정과목명` (공백 제거)
- 가장 가까운 부모 요소를 자동 제안

### 매핑 결과 확인
매핑 완료 후 사용자에게 결과를 보여주고 검토 요청:
- 고신뢰(>=0.8): 자동 확정
- 중신뢰(0.5~0.8): 사용자 확인 권고
- 저신뢰(<0.5): 확장항목 검토 필요

---

## STEP 3: M2 — iXBRL 태그 생성

### Context 생성
```xml
<xbrli:context id="ctx_20241231_연결">
  <xbrli:entity>
    <xbrli:identifier scheme="http://dart.fss.or.kr">회사명</xbrli:identifier>
  </xbrli:entity>
  <xbrli:period>
    <xbrli:instant>2024-12-31</xbrli:instant>
  </xbrli:period>
</xbrli:context>
```

### 태그 형식
- **monetary**: `<ix:nonFraction name="ifrs-full:Assets" contextRef="..." unitRef="KRW" decimals="0" format="ixt:num-dot-decimal">514,531,948,000,000</ix:nonFraction>`
- **perShare**: `<ix:nonFraction>` (unitRef 없이)
- **text**: `<ix:nonNumeric>`

### iXBRL HTML 출력
- 재무제표 형태의 HTML 테이블
- 각 금액에 ix:nonFraction 태그 인라인 삽입
- 계층별 들여쓰기 + 색상 구분 (tagged=녹색, untagged=적색, extension=주황)
- 태깅 통계 표시

---

## STEP 4: M3 — 자동 검증

### 검증 항목
1. **필수 항목 존재 검사**: Assets, Liabilities, Equity, CurrentAssets, NoncurrentAssets
2. **Calculation Linkbase 합산**: 자산 = 유동자산 + 비유동자산, 부채 = 유동부채 + 비유동부채
3. **BS 균형 검증**: 자산총계 = 부채총계 + 자본총계
4. **부채와자본총계 교차검증**: 부채와자본총계 = 자산총계
5. **음수 값 검사**: 자산/현금 등 양수 예상 항목의 음수 여부
6. **태깅 완성도**: 미태깅 항목, 확장항목 필요 수

### 검증 결과
- **PASS**: ERROR 0개 (WARNING은 허용)
- **FAIL**: ERROR 1개 이상 → 원인 분석 및 수정 제안

---

## 출력 파일

1. **iXBRL HTML**: `ixbrl_{회사명}_{연도}.html` — 태깅된 재무제표
2. **매핑 결과 JSON**: `mapping_result_{timestamp}.json` — M1 매핑 상세
3. **검증 리포트 JSON**: `validation_{회사명}_{연도}.json` — M3 검증 결과

---

## 기존 코드 활용

프로젝트 디렉토리에 `xbrl_platform/` 폴더가 있으면 다음 모듈을 import하여 사용:
```python
from m1_taxonomy_mapper import TaxonomyMapper
from m2_auto_tagger import AutoTagger
from m3_validator import Validator

m1 = TaxonomyMapper()
m2 = AutoTagger(taxonomy_mapper=m1)
m3 = Validator()

# 매핑 → 태깅 → 검증
mapping_results = m1.map_accounts(account_names)
tagged = m2.tag_financial_statement(data, period_end="2024-12-31", entity="삼성전자")
ixbrl_path = m2.export_ixbrl(tagged, title="삼성전자 재무상태표")
validation = m3.validate(tagged)
```
