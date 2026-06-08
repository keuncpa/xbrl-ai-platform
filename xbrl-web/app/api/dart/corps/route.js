import { NextResponse } from 'next/server'

/**
 * Legacy endpoint — 기존 호환용.
 * 새 검색 기능은 /api/dart/search?q=기업명 을 사용합니다.
 * 이 엔드포인트는 주요 기업 샘플 목록만 반환합니다.
 */
const SAMPLE_COMPANIES = [
  { corp_code: '00126380', name: '삼성전자', stock_code: '005930' },
  { corp_code: '00164779', name: 'SK하이닉스', stock_code: '000660' },
  { corp_code: '00401731', name: 'LG전자', stock_code: '066570' },
  { corp_code: '00164742', name: '현대자동차', stock_code: '005380' },
  { corp_code: '00266961', name: 'NAVER', stock_code: '035420' },
  { corp_code: '00258801', name: '카카오', stock_code: '035720' },
]

export async function GET() {
  return NextResponse.json({
    companies: SAMPLE_COMPANIES,
    note: '전체 상장사 검색은 /api/dart/search?q=기업명 을 사용하세요.',
  })
}
