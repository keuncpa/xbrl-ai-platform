import { NextResponse } from 'next/server'

const DART_API_KEY = process.env.DART_API_KEY

/**
 * DART 기업 검색 API 프록시
 * GET /api/dart/search?q=삼성
 *
 * DART company.json API를 사용하여 기업명으로 검색합니다.
 * 상장법인(Y)만 필터링하여 반환합니다.
 */
export async function GET(request) {
  const { searchParams } = new URL(request.url)
  const query = searchParams.get('q')

  if (!query || query.trim().length < 1) {
    return NextResponse.json(
      { error: '검색어를 입력하세요 (q 파라미터 필수)', companies: [] },
      { status: 400 }
    )
  }

  try {
    const url = new URL('https://opendart.fss.or.kr/api/company.json')
    url.searchParams.set('crtfc_key', DART_API_KEY)
    url.searchParams.set('corp_name', query.trim())

    const res = await fetch(url.toString(), { cache: 'no-store' })
    const data = await res.json()

    if (data.status === '013') {
      // 조회 결과 없음
      return NextResponse.json({ companies: [], total: 0 })
    }

    if (data.status !== '000' || !data.list) {
      return NextResponse.json(
        { error: data.message || 'DART API 오류', companies: [] },
        { status: 502 }
      )
    }

    // 상장법인(Y)만 필터 + 필요한 필드만 반환
    const companies = data.list
      .filter(item => item.stock_code && item.stock_code.trim() !== '')
      .map(item => ({
        corp_code: item.corp_code,
        name: item.corp_name,
        stock_code: item.stock_code,
        modify_date: item.modify_date,
      }))
      .slice(0, 50) // 최대 50개

    return NextResponse.json({ companies, total: companies.length })
  } catch (err) {
    return NextResponse.json(
      { error: 'DART API 요청 실패: ' + err.message, companies: [] },
      { status: 500 }
    )
  }
}
