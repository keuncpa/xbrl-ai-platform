---
name: xbrl-validator
description: |
  XBRL 태깅 데이터의 품질을 종합 검증하는 스킬. Calculation Linkbase 합산 검증, 대차대조표 균형(자산=부채+자본) 검증, 필수 항목 존재 검사, 음수 값 검사, 태깅 완성도 검사, 전기 대비 이상치 탐지를 수행한다.
  검증 결과를 PASS/FAIL로 판정하고, ERROR/WARNING/INFO 등급별 상세 리포트를 생성한다.
  MANDATORY TRIGGERS: XBRL 검증, XBRL validation, 태깅 검증, 공시 검증, Calculation Linkbase, BS 균형, 대차대조표 검증, 재무제표 검증, XBRL 품질, 오류 검사, 합산 검증, balance sheet equation, 필수항목 검사.
  사용자가 "XBRL 검증해줘", "태깅 맞는지 확인", "BS 균형 검사", "공시 오류 찾아줘", "Calculation 검증", "재무제표 합계 확인" 등을 말하면 반드시 이 스킬을 사용할 것.
  한국어로 작업한다.
---

# XBRL 검증 및 품질검사 스킬

## 개요

XBRL 태깅 데이터의 정확성과 완전성을 6가지 검증 규칙으로 자동 점검하는 스킬이다. 공시 전 최종 품질 게이트 역할을 하며, 오류 발견 시 원인 분석과 수정 방안을 함께 제시한다.

## 검증 체계

```
[태깅 데이터 입력]
    ↓
[CHECK 1] 필수 항목 존재 검사
    ↓
[CHECK 2] Calculation Linkbase 합산 검증
    ↓
[CHECK 3] 대차대조표 균형 검증
    ↓
[CHECK 4] 음수 값 검사
    ↓
[CHECK 5] 태깅 완성도 검사
    ↓
[CHECK 6] 전기 대비 이상치 탐지 (선택)
    ↓
[PASS / FAIL 판정 + 상세 리포트]
```

---

## CHECK 1: 필수 항목 존재 검사

재무상태표 공시에 반드시 포함되어야 하는 핵심 요소:

| 필수 요소 | Taxonomy ID |
|-----------|-------------|
| 자산총계 | ifrs-full:Assets |
| 부채총계 | ifrs-full:Liabilities |
| 자본총계 | ifrs-full:Equity |
| 유동자산 | ifrs-full:CurrentAssets |
| 비유동자산 | ifrs-full:NoncurrentAssets |

누락 시 **ERROR** 등급 발생.

---

## CHECK 2: Calculation Linkbase 합산 검증

### 검증 규칙
| 부모 요소 | = | 하위 합계 |
|-----------|---|-----------|
| 자산총계 | = | 유동자산 + 비유동자산 |
| 부채총계 | = | 유동부채 + 비유동부채 |
| 자본총계 | = | 지배기업소유주지분 + 비지배지분 |

### 검증 로직
- **모든 하위 항목 존재**: 엄격 검증 (1원 이상 차이 → ERROR)
- **일부 하위 항목만 존재**: 관대 검증 (합계 초과 시 WARNING)
- **하위 항목 없음**: 검증 건너뜀

---

## CHECK 3: 대차대조표 균형 검증

### 검증 방정식
1. **자산 = 부채 + 자본**: `Assets = Liabilities + Equity`
2. **부채와자본총계 = 자산총계**: `LiabilitiesAndEquity = Assets` (교차검증)

1원 이상 차이 시 **ERROR**.

---

## CHECK 4: 음수 값 검사

양수만 허용되는 항목에 음수가 있으면 **WARNING**:
- Assets, CurrentAssets, NoncurrentAssets
- CashAndCashEquivalents, Inventories
- IssuedCapital

---

## CHECK 5: 태깅 완성도 검사

- **미태깅 항목**: 금액이 있으나 iXBRL 태그가 없는 항목 → WARNING
- **확장항목**: 표준 Taxonomy에 없어 확장이 필요한 항목 → INFO

---

## CHECK 6: 전기 대비 이상치 탐지

전기 데이터가 제공된 경우, 각 Taxonomy 요소의 금액 변동률을 검사:

| 변동률 | 등급 | 설명 |
|--------|------|------|
| 100~500% | WARNING | 대폭 변동 — 검토 필요 |
| 500%+ | WARNING | 극심 변동 — 중점 검토 |

이상치는 "오류"가 아닌 "검토 항목"이므로 WARNING으로 분류한다. 실제 사업 환경 변화로 인한 정당한 변동일 수 있기 때문이다.

---

## 판정 기준

| 결과 | 조건 |
|------|------|
| **PASS** | ERROR 0개 (WARNING은 허용) |
| **FAIL** | ERROR 1개 이상 |

---

## 기존 코드 활용

```python
from m3_validator import Validator

validator = Validator()

# 당기만 검증
report = validator.validate(tagged_items)

# 전기 대비 검증 (이상치 탐지 포함)
report = validator.validate(tagged_items, prior_items=prior_tagged)

# 결과 확인
print(f"Status: {report['status']}")  # PASS or FAIL
print(f"Errors: {report['summary']['errors']}")
print(f"Warnings: {report['summary']['warnings']}")

# 리포트 저장
validator.export_report(report, "validation_report.json")
```

---

## 검증 실패 시 대응

ERROR가 발생하면 다음 순서로 대응:

1. **필수 항목 누락** → M1 Taxonomy 매핑 재확인, 입력 데이터에 해당 항목 존재 여부 확인
2. **합산 불일치** → 부모-자식 관계가 맞는지 확인, 누락된 하위 항목이 있는지 확인
3. **BS 불균형** → 부채총계 또는 자본총계 누락 여부 확인, 금액 단위 일관성 확인
4. **수정 후 재검증** → M2로 재태깅 후 M3 재실행
