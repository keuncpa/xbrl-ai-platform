---
name: xbrl-extension-manager
description: |
  다수 기업의 XBRL 확장항목(Extension Element)을 수집, 클러스터링하여 유사 항목을 묶고, 표준 Taxonomy 추가 후보를 자동 추천하는 스킬.
  텍스트 유사도 기반으로 기업 간 표기 차이(예: "사용권자산" vs "사용권 자산" vs "사용권-자산")를 자동 감지하고 통합 제안한다.
  M1 Taxonomy Mapper에 대한 피드백 데이터를 생성하여 매핑 정확도를 지속적으로 향상시키는 학습 루프를 구현한다.
  MANDATORY TRIGGERS: 확장항목, Extension, XBRL 확장, Taxonomy 확장, 표준화, 확장요소 관리, extension element, 표준 Taxonomy 추가, 확장항목 클러스터링, 기업 간 확장항목 비교.
  사용자가 "확장항목 분석해줘", "Extension 정리", "표준화 후보 추천", "기업들 확장항목 비교", "Taxonomy에 뭐 추가해야 돼" 등을 말하면 반드시 이 스킬을 사용할 것.
  한국어로 작업한다.
---

# XBRL 확장항목 표준화 관리 스킬

## 개요

K-IFRS XBRL 표준 Taxonomy에 없어서 기업들이 자체적으로 만든 확장항목(Extension Element)을 기업 간 비교, 클러스터링, 표준화 추천하는 스킬이다. 공시 품질 향상과 Taxonomy 개선에 기여한다.

## 전체 프로세스

```
[다수 기업의 확장항목 수집]
    ↓
[STEP 1] 유사도 기반 클러스터링
    ↓
[STEP 2] 표준화 후보 추천
    ↓
[STEP 3] M1 피드백 데이터 생성
    ↓
[표준화 제안 리포트 출력]
```

---

## STEP 1: 확장항목 수집 및 클러스터링

### 확장항목 소스
- M1 Taxonomy Mapper에서 매핑 실패(confidence < 0.5)한 항목
- DART 공시 파일에서 `ext:` 또는 비표준 namespace를 사용하는 항목
- 사용자가 직접 제공하는 확장항목 목록

### 클러스터링 알고리즘
```python
from difflib import SequenceMatcher

# 유사도 기준: 0.6 이상이면 같은 클러스터
SIMILARITY_THRESHOLD = 0.6

# 정규화 후 비교 (공백, 하이픈, 괄호 제거)
# "사용권자산" ≈ "사용권 자산" ≈ "사용권-자산" → 같은 클러스터
```

### 클러스터 구조
```json
{
  "representative": "사용권자산",
  "labels": ["사용권자산", "사용권 자산", "사용권-자산"],
  "companies": ["삼성전자", "SK하이닉스", "LG전자", "현대자동차"],
  "company_count": 4,
  "parent": "ifrs-full:NoncurrentAssets"
}
```

---

## STEP 2: 표준화 후보 추천

### 추천 기준
- **높은 우선순위**: 3개 기업 이상에서 사용하는 확장항목
- **보통 우선순위**: 2개 기업에서 사용하는 확장항목
- **낮은 우선순위**: 1개 기업에서만 사용 (기업 고유 항목)

### 제안 형식
```
'사용권자산' - 4개 기업 사용 [우선순위: 높음]
  유사 레이블: 사용권자산, 사용권 자산, 사용권-자산
  부모 요소: ifrs-full:NoncurrentAssets
  제안: 표준 Taxonomy에 ifrs-full:RightOfUseAssets 추가 권고
```

---

## STEP 3: M1 피드백 데이터 생성

2개 이상의 기업에서 사용하는 확장항목에 대해, M1 Taxonomy Mapper의 `learn_mapping()` 함수에 전달할 피드백 데이터를 자동 생성한다.

```python
feedback = [
    {
        "account_name": "사용권자산",
        "suggested_parent": "ifrs-full:NoncurrentAssets",
        "is_extension": True,
        "frequency": 4,
        "representative_label": "사용권자산"
    }
]
# M1에 학습 적용
for fb in feedback:
    m1.learn_mapping(fb['account_name'], fb['suggested_parent'])
```

이를 통해 M1 → M6 → M1 피드백 루프가 완성된다.

---

## 기존 코드 활용

```python
from m6_extension_manager import ExtensionManager

m6 = ExtensionManager()

# 기업별 확장항목 등록
m6.add_extensions("삼성전자", [
    {"label": "사용권자산", "parent": "ifrs-full:NoncurrentAssets"},
    {"label": "리스부채", "parent": "ifrs-full:NoncurrentLiabilities"},
])

# 클러스터링 → 표준화 제안
clusters = m6.cluster_extensions()
suggestions = m6.suggest_standardization(min_companies=2)

# M1 피드백
feedback = m6.generate_m1_feedback()

# 리포트 출력
m6.print_summary()
m6.export_report(suggestions, "extension_report.json")
```

---

## 출력 형식

### JSON 리포트
- 전체 확장항목 수, 클러스터 수, 표준화 후보 수
- 기업별 확장항목 요약
- 표준화 제안 상세 (우선순위, 사용 기업, 유사 레이블)

### 엑셀 출력 (xlsx 스킬 연계)
- 확장항목 전체 목록 시트
- 클러스터 분석 시트
- 표준화 제안 시트
- M1 피드백 시트
