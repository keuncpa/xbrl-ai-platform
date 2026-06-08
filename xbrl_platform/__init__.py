"""
XBRL 공시 AI 자동화 플랫폼
End-to-End Pipeline: 재무제표 입력 → Taxonomy 매핑 → iXBRL 태깅 → 검증 → 변경추적 → 분석

Modules:
    M1. Taxonomy Mapper  - 계정과목 → 표준 Taxonomy 자동 매핑
    M2. Auto Tagger      - 재무제표 → iXBRL 태그 자동 부착
    M3. Validator         - XBRL 파일 검증 및 오류 탐지
    M4. Change Tracker    - 공시 파일 변경사항 자동 추적
    M5. Analytics         - DART 데이터 기반 재무 분석
    M6. Extension Manager - 확장항목 표준화 제안
"""

__version__ = "0.1.0"
__author__ = "XBRL AI Platform"
