import { NextResponse } from 'next/server'

const DART_API_KEY = process.env.DART_API_KEY
const DART_BASE_URL = 'https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json'

export async function GET(request) {
  const { searchParams } = new URL(request.url)
  const corp_code = searchParams.get('corp_code')
  const bsns_year = searchParams.get('bsns_year') || '2024'
  const reprt_code = searchParams.get('reprt_code') || '11011'
  const fs_div = searchParams.get('fs_div') || 'CFS'

  if (!DART_API_KEY) {
    return NextResponse.json(
      { error: 'DART_API_KEY 환경변수가 설정되지 않았습니다. Vercel 프로젝트 설정에서 등록하세요.' },
      { status: 500 }
    )
  }
  if (!corp_code || !/^\d{8}$/.test(corp_code)) {
    return NextResponse.json({ error: 'corp_code는 8자리 숫자여야 합니다.' }, { status: 400 })
  }
  if (!/^\d{4}$/.test(bsns_year)) {
    return NextResponse.json({ error: 'bsns_year는 4자리 연도여야 합니다.' }, { status: 400 })
  }

  try {
    const url = new URL(DART_BASE_URL)
    url.searchParams.set('crtfc_key', DART_API_KEY)
    url.searchParams.set('corp_code', corp_code)
    url.searchParams.set('bsns_year', bsns_year)
    url.searchParams.set('reprt_code', reprt_code)
    url.searchParams.set('fs_div', fs_div)

    const res = await fetch(url.toString(), {
      cache: 'no-store',
      signal: AbortSignal.timeout(15000), // DART 응답 지연 대비 15초 타임아웃
    })
    const data = await res.json()

    return NextResponse.json(data)
  } catch (err) {
    return NextResponse.json(
      { error: 'Failed to fetch from DART API', detail: err.message },
      { status: 500 }
    )
  }
}
