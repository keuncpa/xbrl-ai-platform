'use client'

import { useState, useEffect, useRef, useCallback } from 'react'

// ============================================================
// 금액 포맷 (억원)
// ============================================================
function formatOk(n) {
  if (n === null || n === undefined || n === 0) return '-'
  const eok = n / 100000000
  return eok.toLocaleString('ko-KR', { maximumFractionDigits: 1 }) + '억'
}

function levelOf(name) {
  if (/총계$/.test(name) || name === '부채와자본총계') return 0
  if (['유동자산', '비유동자산', '유동부채', '비유동부채', '지배기업 소유주지분', '비지배지분'].some(k => name.includes(k))) return 1
  return 2
}

// ============================================================
// DART 응답 파서 — 당기(thstrm) + 전기(frmtrm) 동시 추출
// ============================================================
function parseDartData(dartResponse) {
  if (!dartResponse || dartResponse.status !== '000' || !dartResponse.list) {
    return { accounts: [], priorAccounts: [], error: dartResponse?.message || 'DART API 응답 오류' }
  }

  const bsItems = dartResponse.list.filter(item => item.sj_nm === '재무상태표')
  const accounts = []
  const priorAccounts = []
  const seen = new Set()

  const toNum = (raw) => {
    if (raw === null || raw === undefined) return null
    let s = typeof raw === 'string' ? raw.replace(/,/g, '') : raw
    const n = parseInt(s, 10)
    return Number.isNaN(n) ? null : n
  }

  for (const item of bsItems) {
    const name = item.account_nm?.trim()
    if (!name || seen.has(name)) continue
    seen.add(name)
    const level = levelOf(name)

    const cur = toNum(item.thstrm_amount)
    accounts.push({ name, amount: cur ?? 0, level })

    const prior = toNum(item.frmtrm_amount)
    if (prior !== null) priorAccounts.push({ name, amount: prior, level })
  }

  return { accounts, priorAccounts, error: null }
}

// ============================================================
// CSV / 엑셀 파서 (입력 추출만 담당 — 매핑/검증은 엔진이 수행)
// ============================================================
function parseCsvText(text) {
  const lines = text.trim().split('\n')
  if (lines.length < 2) return []
  const accounts = []
  for (let i = 1; i < lines.length; i++) {
    const parts = lines[i].split(',').map(s => s.trim().replace(/^"|"$/g, ''))
    if (parts.length >= 2) {
      const name = parts[0]
      const amount = parseInt(parts[1].replace(/,/g, ''), 10) || 0
      accounts.push({ name, amount, level: levelOf(name) })
    }
  }
  return accounts
}

function loadXlsxLib() {
  return new Promise((resolve, reject) => {
    if (typeof window !== 'undefined' && window.XLSX) { resolve(window.XLSX); return }
    const script = document.createElement('script')
    script.src = 'https://cdn.sheetjs.com/xlsx-0.20.0/package/dist/xlsx.full.min.js'
    script.onload = () => resolve(window.XLSX)
    script.onerror = () => reject(new Error('SheetJS CDN 로드 실패'))
    document.head.appendChild(script)
  })
}

async function parseXlsx(file) {
  const XLSX = await loadXlsxLib()
  const buf = await file.arrayBuffer()
  const wb = XLSX.read(buf, { type: 'array' })
  const ws = wb.Sheets[wb.SheetNames[0]]
  const rows = XLSX.utils.sheet_to_json(ws, { header: 1 })
  if (rows.length < 2) return []

  const header = rows[0].map(h => String(h || '').trim())
  let nameCol = header.findIndex(h => /계정|과목|항목|account/i.test(h))
  let amountCol = header.findIndex(h => /금액|당기|잔액|amount|thstrm/i.test(h))
  if (nameCol === -1) nameCol = 0
  if (amountCol === -1) amountCol = 1

  const accounts = []
  for (let i = 1; i < rows.length; i++) {
    const row = rows[i]
    if (!row || !row[nameCol]) continue
    const name = String(row[nameCol]).trim()
    if (!name) continue
    let rawAmount = row[amountCol]
    if (typeof rawAmount === 'string') rawAmount = rawAmount.replace(/,/g, '')
    const amount = parseInt(rawAmount, 10) || 0
    accounts.push({ name, amount, level: levelOf(name) })
  }
  return accounts
}

// ============================================================
// COMPONENT
// ============================================================
export default function DemoPage() {
  const [activeTab, setActiveTab] = useState('dart')

  // 기업 검색 상태
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState([])
  const [selectedCorp, setSelectedCorp] = useState(null)
  const [showDropdown, setShowDropdown] = useState(false)
  const searchBoxRef = useRef(null)

  const [year, setYear] = useState('2024')
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState(null)
  const [error, setError] = useState(null)
  const [csvText, setCsvText] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const fileRef = useRef(null)

  const [allCorps, setAllCorps] = useState([])

  useEffect(() => {
    fetch('/corps_listed.json').then(r => r.json()).then(setAllCorps).catch(() => {})
  }, [])

  useEffect(() => {
    const handleClick = (e) => {
      if (searchBoxRef.current && !searchBoxRef.current.contains(e.target)) setShowDropdown(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  const handleSearchChange = (value) => {
    setSearchQuery(value)
    setSelectedCorp(null)
    if (value.trim().length < 1) { setSearchResults([]); setShowDropdown(false); return }
    const q = value.trim().toLowerCase()
    const matches = allCorps
      .filter(c => c.n.toLowerCase().includes(q) || c.s.includes(q))
      .slice(0, 30)
      .map(c => ({ corp_code: c.c, name: c.n, stock_code: c.s }))
    setSearchResults(matches)
    setShowDropdown(matches.length > 0)
  }

  const handleSelectCorp = (corp) => {
    setSelectedCorp(corp)
    setSearchQuery(corp.name)
    setShowDropdown(false)
  }

  // ── 코어 엔진 호출 (M1~M4) ──
  const callEngine = useCallback(async (accounts, priorAccounts, meta) => {
    setLoading(true); setError(null); setResults(null)
    try {
      const res = await fetch('/api/process', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          accounts,
          prior_accounts: priorAccounts || [],
          period_end: `${meta.year}-12-31`,
          entity: meta.entity || '업로드기업',
        }),
      })
      const data = await res.json()
      if (!res.ok || !data.ok) {
        setError(data.error || `엔진 처리 실패 (HTTP ${res.status})`)
        setLoading(false)
        return
      }
      setResults({ ...data, _meta: meta })
    } catch (e) {
      setError('엔진 호출 실패: ' + e.message + ' — 로컬에서는 `vercel dev` 또는 배포 환경에서 동작합니다.')
    }
    setLoading(false)
  }, [])

  // DART 조회 → 엔진
  const handleDartFetch = async () => {
    if (!selectedCorp?.corp_code) return
    setLoading(true); setError(null); setResults(null)
    try {
      const res = await fetch(`/api/dart?corp_code=${selectedCorp.corp_code}&bsns_year=${year}`)
      const data = await res.json()
      const { accounts, priorAccounts, error: parseErr } = parseDartData(data)
      if (parseErr) { setError(parseErr); setLoading(false); return }
      if (accounts.length === 0) {
        setError('재무상태표 데이터가 없습니다. 해당 연도에 사업보고서가 없을 수 있습니다.')
        setLoading(false); return
      }
      await callEngine(accounts, priorAccounts, { entity: selectedCorp.name, year })
    } catch (e) {
      setError('API 요청 실패: ' + e.message)
      setLoading(false)
    }
  }

  const handleFileUpload = async (file) => {
    setLoading(true); setError(null); setResults(null)
    try {
      const ext = file.name.split('.').pop().toLowerCase()
      let accounts = []
      if (ext === 'csv' || ext === 'txt') accounts = parseCsvText(await file.text())
      else if (ext === 'xlsx' || ext === 'xls') accounts = await parseXlsx(file)
      else { setError('지원하지 않는 파일 형식입니다. (.xlsx, .csv 지원)'); setLoading(false); return }
      if (accounts.length === 0) { setError('파싱된 계정과목이 없습니다. 파일 형식을 확인하세요.'); setLoading(false); return }
      await callEngine(accounts, [], { entity: file.name.replace(/\.[^.]+$/, ''), year })
    } catch (e) {
      setError('파일 처리 실패: ' + e.message); setLoading(false)
    }
  }

  const handleCsvSubmit = async () => {
    if (!csvText.trim()) return
    const accounts = parseCsvText(csvText)
    if (accounts.length === 0) { setError('파싱된 계정과목이 없습니다. CSV 형식을 확인하세요.'); return }
    await callEngine(accounts, [], { entity: '직접입력', year })
  }

  const handleDrop = (e) => {
    e.preventDefault(); setDragOver(false)
    const file = e.dataTransfer?.files?.[0]
    if (file) handleFileUpload(file)
  }

  // iXBRL 다운로드 / 새 탭 보기
  const downloadIxbrl = () => {
    if (!results?.ixbrl_html) return
    const blob = new Blob([results.ixbrl_html], { type: 'text/html;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${results._meta?.entity || 'company'}_${results._meta?.year || ''}_iXBRL.html`
    document.body.appendChild(a); a.click(); a.remove()
    URL.revokeObjectURL(url)
  }
  const viewIxbrl = () => {
    if (!results?.ixbrl_html) return
    const w = window.open('', '_blank')
    if (w) { w.document.write(results.ixbrl_html); w.document.close() }
  }

  const meta = results?._meta || {}
  const v = results?.validation
  const cov = results?.coverage
  const chg = results?.change_report

  return (
    <main className="demo-page">
      <nav className="floating-nav">
        <div className="nav-inner">
          <a href="/" className="nav-logo">XBRL Platform</a>
          <div className="nav-links">
            <a href="/">Home</a>
            <a href="/demo" className="active">Demo</a>
            <a href="/#architecture">Architecture</a>
            <a href="/#results">Results</a>
          </div>
        </div>
      </nav>

      <div className="demo-container">
        <div className="demo-header">
          <h1>XBRL 생성·검증 데모</h1>
          <p>기업을 검색해 DART 재무데이터를 불러오거나 엑셀/CSV를 업로드하면, 코어 엔진(M1~M4)이 <b>Taxonomy 매핑 → iXBRL 생성 → 품질검증 → 전기 대비 변경추적</b>까지 한 번에 처리합니다.</p>
        </div>

        {/* Tabs */}
        <div className="tab-bar">
          <button className={`tab-btn ${activeTab === 'dart' ? 'active' : ''}`} onClick={() => setActiveTab('dart')}>DART API 조회</button>
          <button className={`tab-btn ${activeTab === 'upload' ? 'active' : ''}`} onClick={() => setActiveTab('upload')}>엑셀 업로드</button>
        </div>

        <div className="tab-content">
          {activeTab === 'dart' && (
            <div className="input-panel">
              <div className="input-row">
                <div className="input-group search-group" ref={searchBoxRef}>
                  <label>기업 검색</label>
                  <div className="search-input-wrapper">
                    <input
                      type="text"
                      value={searchQuery}
                      onChange={e => handleSearchChange(e.target.value)}
                      onFocus={() => { if (searchResults.length > 0) setShowDropdown(true) }}
                      placeholder="기업명을 입력하세요 (예: 삼성, 현대, LG...)"
                      className="search-input"
                      autoComplete="off"
                    />
                    {selectedCorp && <span className="selected-badge">{selectedCorp.stock_code}</span>}
                  </div>
                  {showDropdown && searchResults.length > 0 && (
                    <div className="search-dropdown">
                      {searchResults.map(c => (
                        <button key={c.corp_code} className={`search-item ${selectedCorp?.corp_code === c.corp_code ? 'selected' : ''}`} onClick={() => handleSelectCorp(c)}>
                          <span className="si-name">{c.name}</span>
                          <span className="si-code">{c.stock_code}</span>
                        </button>
                      ))}
                    </div>
                  )}
                  {showDropdown && searchResults.length === 0 && searchQuery.trim().length >= 1 && (
                    <div className="search-dropdown"><div className="search-empty">검색 결과가 없습니다</div></div>
                  )}
                </div>
                <div className="input-group">
                  <label>사업연도</label>
                  <input type="number" value={year} onChange={e => setYear(e.target.value)} min="2015" max="2025" />
                </div>
                <button className="btn-primary" onClick={handleDartFetch} disabled={loading || !selectedCorp}>
                  {loading ? '처리 중...' : '조회 및 XBRL 생성'}
                </button>
              </div>
            </div>
          )}

          {activeTab === 'upload' && (
            <div className="input-panel">
              <div
                className={`upload-zone ${dragOver ? 'drag-over' : ''}`}
                onDragOver={e => { e.preventDefault(); setDragOver(true) }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleDrop}
                onClick={() => fileRef.current?.click()}
              >
                <input ref={fileRef} type="file" accept=".xlsx,.xls,.csv,.txt" style={{ display: 'none' }}
                  onChange={e => { const f = e.target.files?.[0]; if (f) handleFileUpload(f) }} />
                <div className="upload-icon">+</div>
                <p className="upload-text">파일을 드래그하거나 클릭하여 업로드</p>
                <p className="upload-hint">.xlsx, .csv 파일 지원</p>
              </div>

              <div className="csv-fallback">
                <label>또는 CSV 텍스트 직접 입력</label>
                <textarea
                  value={csvText}
                  onChange={e => setCsvText(e.target.value)}
                  placeholder={`계정과목,금액\n자산총계,51400000000000\n유동자산,21800000000000\n비유동자산,29600000000000\n부채총계,10200000000000\n유동부채,6500000000000\n비유동부채,3700000000000\n자본총계,41200000000000`}
                  rows={8}
                />
                <button className="btn-primary" onClick={handleCsvSubmit} disabled={loading || !csvText.trim()}>
                  {loading ? '처리 중...' : 'XBRL 생성·검증'}
                </button>
              </div>
            </div>
          )}
        </div>

        {error && <div className="error-box"><strong>오류:</strong> {error}</div>}

        {loading && (
          <div className="loading-box"><div className="spinner" /><span>엔진 처리 중...</span></div>
        )}

        {/* Results */}
        {results && v && (
          <div className="results-panel">
            {/* Summary Card */}
            <div className="summary-card">
              <div className="summary-header">
                <div>
                  <h2>결과 {meta.entity && `— ${meta.entity}`} {meta.year && `(${meta.year})`}</h2>
                  <p className="summary-sub">M1 매핑 · M2 iXBRL 생성 · M3 검증{chg ? ' · M4 변경추적' : ''} (코어 엔진 실행)</p>
                </div>
                <span className={`status-badge ${v.status === 'PASS' ? 'pass' : 'fail'}`}>{v.status}</span>
              </div>
              <div className="summary-stats">
                <div className="stat-item"><div className="stat-num">{cov?.total_items ?? 0}</div><div className="stat-label">전체 항목</div></div>
                <div className="stat-item"><div className="stat-num green">{cov?.tagged_count ?? 0}</div><div className="stat-label">태깅 성공</div></div>
                <div className="stat-item"><div className="stat-num amber">{cov?.extension_needed ?? 0}</div><div className="stat-label">확장항목</div></div>
                <div className="stat-item"><div className="stat-num red">{v.summary.errors}</div><div className="stat-label">ERROR</div></div>
                <div className="stat-item"><div className="stat-num amber">{v.summary.warnings}</div><div className="stat-label">WARNING</div></div>
                <div className="stat-item"><div className="stat-num">{cov?.avg_confidence ?? '-'}</div><div className="stat-label">평균 신뢰도</div></div>
              </div>

              {/* iXBRL 산출물 다운로드 */}
              <div className="download-bar">
                <span className="download-label">M2 iXBRL 산출물</span>
                <div className="download-actions">
                  <button className="btn-ghost" onClick={viewIxbrl}>새 탭에서 보기</button>
                  <button className="btn-download" onClick={downloadIxbrl}>iXBRL 다운로드 (.html)</button>
                </div>
              </div>
            </div>

            {/* M4 변경추적 (전기 데이터가 있을 때) */}
            {chg && (
              <div className="section-block">
                <h3>M4 전기 대비 변경 추적</h3>
                <div className="change-summary">
                  <span className="chg-stat">총 변경 <b>{chg.total_changes}</b>건</span>
                  <span className="chg-stat material">중요 변동 <b>{chg.material_changes}</b>건</span>
                  <span className="chg-stat">중요성 기준 {chg.materiality_threshold}</span>
                </div>
                <ul className="change-narrative">
                  {chg.summary.map((line, i) => <li key={i}>{line}</li>)}
                </ul>
                <div className="table-wrapper">
                  <table className="change-table">
                    <thead>
                      <tr><th>유형</th><th>계정과목</th><th className="text-right">전기</th><th className="text-right">당기</th><th className="text-right">증감</th><th className="text-right">변동률</th></tr>
                    </thead>
                    <tbody>
                      {chg.changes.slice(0, 20).map((c, i) => (
                        <tr key={i} className={c.is_material ? 'material-row' : ''}>
                          <td><span className="chg-type">{c.type}{c.is_material && ' ★'}</span></td>
                          <td>{c.account_name}</td>
                          <td className="text-right amount-cell">{formatOk(c.prior_amount)}</td>
                          <td className="text-right amount-cell">{formatOk(c.current_amount)}</td>
                          <td className={`text-right amount-cell ${(c.difference || 0) >= 0 ? 'pos' : 'neg'}`}>
                            {c.difference != null ? (c.difference >= 0 ? '+' : '') + formatOk(c.difference) : '-'}
                          </td>
                          <td className="text-right">{c.change_rate != null ? `${(c.change_rate * 100).toFixed(0)}%` : '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* M3 검증 상세 */}
            <div className="section-block">
              <h3>M3 검증 상세</h3>
              {v.summary.errors === 0 && v.summary.warnings === 0 && v.summary.info === 0 ? (
                <div className="validation-card pass">
                  <div className="vc-header"><span className="vc-badge pass">PASS</span><span className="vc-name">모든 검증 규칙 통과 (합산·대차균형·필수항목·음수·완성도)</span></div>
                </div>
              ) : (
                <div className="validation-list">
                  {v.errors.map((e, i) => (
                    <div key={`e${i}`} className="validation-card error">
                      <div className="vc-header"><span className="vc-badge error">ERROR</span><span className="vc-id">{e.rule}</span></div>
                      <div className="vc-detail">{e.message}</div>
                    </div>
                  ))}
                  {v.warnings.map((w, i) => (
                    <div key={`w${i}`} className="validation-card warning">
                      <div className="vc-header"><span className="vc-badge warning">WARNING</span><span className="vc-id">{w.rule}</span></div>
                      <div className="vc-detail">{w.message}</div>
                    </div>
                  ))}
                  {v.info.map((inf, i) => (
                    <div key={`i${i}`} className="validation-card pass">
                      <div className="vc-header"><span className="vc-badge">INFO</span><span className="vc-id">{inf.rule}</span></div>
                      <div className="vc-detail">{inf.message}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* M1 매핑 결과 */}
            <div className="section-block">
              <h3>M1 Taxonomy 매핑 결과</h3>
              <div className="table-wrapper">
                <table className="mapping-table">
                  <thead>
                    <tr><th>계정과목</th><th>매핑된 Taxonomy</th><th>신뢰도</th><th className="text-right">금액 (억원)</th></tr>
                  </thead>
                  <tbody>
                    {results.mapping.map((item, i) => (
                      <tr key={i} className={`level-${item.level}`}>
                        <td><span className="indent" style={{ paddingLeft: item.level * 20 }}>{item.name}</span></td>
                        <td>
                          <span className={`taxonomy-id ${item.is_extension ? 'ext' : ''}`}>{item.taxonomy_element}</span>
                          {item.is_extension && <span className="ext-badge">EXT</span>}
                        </td>
                        <td>
                          <div className="confidence-cell">
                            <div className="confidence-bar">
                              <div className="confidence-fill" style={{
                                width: `${Math.round(item.confidence * 100)}%`,
                                backgroundColor: item.confidence >= 0.8 ? 'var(--green)' : item.confidence >= 0.5 ? 'var(--amber)' : 'var(--red)',
                              }} />
                            </div>
                            <span className="confidence-val">{(item.confidence * 100).toFixed(0)}%</span>
                          </div>
                        </td>
                        <td className="text-right amount-cell">{item.amount !== 0 ? formatOk(item.amount) : '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </div>
    </main>
  )
}
