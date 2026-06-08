---
name: xbrl-change-tracker
description: |
  전기/당기 재무제표의 XBRL 태깅 데이터를 비교하여 변경사항을 자동 추적하고 중요성(Materiality) 기준으로 필터링하여 자연어 요약 리포트를 생성하는 스킬.
  신규 추가, 삭제, 금액 변동, Taxonomy 변경 등 모든 유형의 변경을 감지하고, 전기 대비 변동률과 중요성 분석을 수행한다.
  MANDATORY TRIGGERS: XBRL 변경추적, 전기 대비 비교, 재무제표 비교, 공시 변경, 변동 분석, change tracking, period comparison, 전기당기 비교, 재무데이터 변경, 중요성 분석, materiality, 계정과목 변동, 재무제표 diff.
  사용자가 "전기 대비 뭐가 바뀌었어", "재무제표 변경사항 추적", "변동 분석해줘", "전기당기 비교", "중요한 변동 찾아줘" 등을 말하면 반드시 이 스킬을 사용할 것.
  한국어로 작업한다.
---

# XBRL 공시 변경추적 및 비교분석 스킬

## 개요

전기와 당기의 XBRL 태깅 데이터를 비교하여 모든 변경사항을 자동 감지하고, 중요성(Materiality) 기준에 따라 필터링한 자연어 요약 리포트를 생성한다. 공시 담당자가 전기 대비 변동 내역을 빠르게 파악하고 감사인 검토에 대비할 수 있도록 돕는다.

## 전체 프로세스

```
[전기 태깅 데이터] + [당기 태깅 데이터]
    ↓
[STEP 1] 계정과목 기준 매칭
    ↓
[STEP 2] 변경 유형 분류 (신규/삭제/금액변동/Taxonomy변경)
    ↓
[STEP 3] 중요성(Materiality) 판단
    ↓
[STEP 4] 자연어 요약 리포트 생성
    ↓
[변경추적 리포트 출력]
```

---

## 변경 유형 분류

| 유형 | 설명 | 심각도 |
|------|------|--------|
| 신규 추가 | 당기에 새로 등장한 계정과목 | 금액에 따라 |
| 삭제 | 전기에 있었으나 당기에 없는 항목 | 금액에 따라 |
| 금액 변동 | 동일 계정과목의 금액 변화 | 변동률에 따라 |
| Taxonomy 변경 | 동일 계정과목의 Taxonomy 요소 변경 | 항상 중요 |

---

## 중요성(Materiality) 기준

### 기본 설정
- **기준 금액**: 자산총계 (ifrs-full:Assets)
- **중요성 비율**: 5% (기본값, 사용자 조정 가능)
- **중요 변동 판단**: |변동금액| / 자산총계 >= 5%

### 이상치 탐지 기준
- **대폭 변동**: 전기 대비 100% 이상 변동 → WARNING
- **극심 변동**: 전기 대비 500% 이상 변동 → WARNING (검토 필요)

---

## 자연어 요약 생성

리포트에 포함되는 자동 요약 항목:
1. 전체 변경건수 및 중요 변동건수
2. 가장 큰 증가 항목 (금액, 변동률)
3. 가장 큰 감소 항목 (금액, 변동률)
4. 신규 추가된 항목 목록
5. 삭제된 항목 목록

### 요약 예시
```
당기 재무제표에서 총 48건의 변경이 감지되었으며, 이 중 7건이 중요한 변동입니다.
가장 큰 증가 항목은 '현금및현금성자산'으로, 전기 대비 12,500,000,000원(25%) 증가했습니다.
가장 큰 감소 항목은 '재고자산'으로, 전기 대비 5,000,000,000원(-15%) 감소했습니다.
신규 추가된 항목: 단기금융상품, 투자부동산
```

---

## 기존 코드 활용

```python
from m1_taxonomy_mapper import TaxonomyMapper
from m2_auto_tagger import AutoTagger
from m4_change_tracker import ChangeTracker

m1 = TaxonomyMapper()
m2 = AutoTagger(taxonomy_mapper=m1)
m4 = ChangeTracker(materiality_threshold=0.05)

# 전기/당기 태깅
prior_tagged = m2.tag_financial_statement(prior_data, period_end="2023-12-31", entity="삼성전자")
current_tagged = m2.tag_financial_statement(current_data, period_end="2024-12-31", entity="삼성전자")

# 변경 추적
changes = m4.compare(prior_tagged, current_tagged)
report = m4.generate_report(changes)
m4.export_report(report, "changes_삼성전자_2024.json")
```

---

## 출력 형식

### JSON 리포트
```json
{
  "materiality_threshold": "5%",
  "total_changes": 48,
  "material_changes": 7,
  "by_type": {"금액 변동": 35, "신규 추가": 8, "삭제": 5},
  "summary": ["당기 재무제표에서 총 48건의 변경이 감지..."],
  "changes": [...]
}
```

### 엑셀 출력 (xlsx 스킬 연계)
- 변경사항 시트: 계정과목, 전기금액, 당기금액, 차이, 변동률, 중요성 여부
- 요약 시트: 유형별 집계, 자연어 요약

---

## DART 실데이터 연계

DART API에서 전기(`frmtrm_amount`)와 당기(`thstrm_amount`)를 모두 제공하므로, dart-financial-analysis 스킬과 연계하면 별도 입력 없이 자동 비교가 가능하다.
