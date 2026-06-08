import { NextResponse } from 'next/server'

const DART_API_KEY = process.env.DART_API_KEY
const DART_BASE_URL = 'https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json'

export async function GET(request) {
  const { searchParams } = new URL(request.url)
  const corp_code = searchParams.get('corp_code')
  const bsns_year = searchParams.get('bsns_year') || '2024'
  const reprt_code = searchParams.get('reprt_code') || '11011'
  const fs_div = searchParams.get('fs_div') || 'CFS'

  if (!corp_code) {
    return NextResponse.json({ error: 'corp_code is required' }, { status: 400 })
  }

  try {
    const url = new URL(DART_BASE_URL)
    url.searchParams.set('crtfc_key', DART_API_KEY)
    url.searchParams.set('corp_code', corp_code)
    url.searchParams.set('bsns_year', bsns_year)
    url.searchParams.set('reprt_code', reprt_code)
    url.searchParams.set('fs_div', fs_div)

    const res = await fetch(url.toString(), { cache: 'no-store' })
    const data = await res.json()

    return NextResponse.json(data)
  } catch (err) {
    return NextResponse.json(
      { error: 'Failed to fetch from DART API', detail: err.message },
      { status: 500 }
    )
  }
}
