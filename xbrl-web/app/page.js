import './globals.css'

const companies = [
  {
    name: '삼성전자',
    assets: '514.5조',
    revenue: '300.9조',
    op_income: '32.7조',
    mapping: '100%',
    coverage: '100%',
    changes: 43,
    material: 4,
  },
  {
    name: 'SK하이닉스',
    assets: '119.9조',
    revenue: '66.2조',
    op_income: '23.5조',
    mapping: '100%',
    coverage: '100%',
    changes: 49,
    material: 9,
  },
  {
    name: 'LG전자',
    assets: '65.6조',
    revenue: '87.7조',
    op_income: '3.4조',
    mapping: '100%',
    coverage: '100%',
    changes: 47,
    material: 7,
  },
  {
    name: '현대자동차',
    assets: '339.8조',
    revenue: '175.2조',
    op_income: '14.2조',
    mapping: '100%',
    coverage: '100%',
    changes: 45,
    material: 5,
  },
]

const modules = [
  {
    id: 'M1',
    name: 'Taxonomy Mapper',
    desc: '계정과목 → KOR-IFRS XBRL 요소 자동 매핑 (유사도 알고리즘)',
  },
  {
    id: 'M2',
    name: 'Auto Tagger',
    desc: 'iXBRL(Inline XBRL) 태그 생성 + HTML 파일 출력',
  },
  {
    id: 'M3',
    name: 'Validator',
    desc: 'Calculation Linkbase 합산, BS 균형, 필수항목 6종 검증',
  },
  {
    id: 'M4',
    name: 'Change Tracker',
    desc: '전기/당기 비교, 중요성(Materiality) 기준 변동 분석',
  },
  {
    id: 'M5',
    name: 'Analytics',
    desc: '재무비율 산출, 기업 간 비교, 대시보드 생성',
  },
  {
    id: 'M6',
    name: 'Extension Mgr',
    desc: '확장항목 클러스터링, 표준화 후보 추천, M1 피드백 루프',
  },
]

const features = [
  {
    icon: '🔗',
    color: 'blue',
    title: 'DART API 실데이터 연동',
    desc: '전자공시시스템(DART) Open API에서 실제 상장사 연결재무제표를 자동 조회하여 처리합니다.',
  },
  {
    icon: '🏷️',
    color: 'cyan',
    title: 'KOR-IFRS Taxonomy 87개 요소',
    desc: '한국채택국제회계기준 Taxonomy 87개 표준 요소를 지원하며, 확장항목 자동 분류를 수행합니다.',
  },
  {
    icon: '✅',
    color: 'green',
    title: '6종 자동 검증',
    desc: '필수항목 존재, Calculation Linkbase 합산, BS 균형(자산=부채+자본), 음수값, 완성도, 이상치를 자동 검증합니다.',
  },
  {
    icon: '📊',
    color: 'amber',
    title: '변경추적 & 중요성 분석',
    desc: '전기 대비 변동사항을 자동 감지하고, 자산총계 5% 기준 중요성(Materiality) 판단을 수행합니다.',
  },
]

const techStack = [
  'Python', 'XBRL 2.1', 'iXBRL (Inline XBRL)', 'KOR-IFRS Taxonomy',
  'DART Open API', 'SequenceMatcher', 'Jaccard Similarity',
  'Calculation Linkbase', 'Next.js', 'Vercel',
]

export default function Home() {
  return (
    <main>
      {/* ===== FLOATING NAV ===== */}
      <nav className="floating-nav">
        <div className="nav-inner">
          <a href="/" className="nav-logo">XBRL Platform</a>
          <div className="nav-links">
            <a href="/" className="active">Home</a>
            <a href="/demo">Demo</a>
            <a href="#architecture">Architecture</a>
            <a href="#results">Results</a>
          </div>
        </div>
      </nav>

      {/* ===== HERO ===== */}
      <section className="hero">
        <div className="container">
          <div className="hero-badge">
            <span className="dot" />
            DART 실데이터 검증 완료
          </div>
          <h1>
            <span className="highlight">XBRL 공시</span> AI 자동화
            <br />플랫폼
          </h1>
          <p className="hero-sub">
            DART API 실제 상장사 재무데이터 기반으로 KOR-IFRS Taxonomy 매핑부터
            iXBRL 태깅, Calculation Linkbase 검증, 변경추적까지 — 공시 업무 전 과정을
            6개 모듈 파이프라인으로 자동화합니다.
          </p>
          <a href="/demo" className="hero-cta">지금 체험하기 &rarr;</a>
          <div className="hero-stats">
            <div className="hero-stat">
              <div className="num">4사</div>
              <div className="label">KOSPI 대형주 검증</div>
            </div>
            <div className="hero-stat">
              <div className="num">100%</div>
              <div className="label">Taxonomy 매핑률</div>
            </div>
            <div className="hero-stat">
              <div className="num">ALL PASS</div>
              <div className="label">M3 Validation</div>
            </div>
            <div className="hero-stat">
              <div className="num">87</div>
              <div className="label">Taxonomy 요소</div>
            </div>
          </div>
        </div>
      </section>

      <div className="divider" />

      {/* ===== ARCHITECTURE ===== */}
      <section id="architecture">
        <div className="container">
          <div className="section-label">Architecture</div>
          <h2 className="section-title">6-Module Pipeline</h2>
          <p className="section-desc">
            M1 Taxonomy 매핑에서 M6 확장항목 관리까지, 각 모듈이 독립적으로 동작하면서도
            M6→M1 피드백 루프를 통해 지속적으로 매핑 정확도를 개선합니다.
          </p>
          <div className="pipeline-flow">
            {modules.map((m) => (
              <div key={m.id} className="pipe-node">
                <div className="pipe-id">{m.id}</div>
                <div className="pipe-name">{m.name}</div>
                <div className="pipe-desc">{m.desc}</div>
              </div>
            ))}
          </div>

          {/* Code sample */}
          <div className="code-block">
            <span className="cm"># Pipeline 실행 예시 (Python)</span><br />
            <span className="kw">from</span> m1_taxonomy_mapper <span className="kw">import</span> <span className="fn">TaxonomyMapper</span><br />
            <span className="kw">from</span> m2_auto_tagger <span className="kw">import</span> <span className="fn">AutoTagger</span><br />
            <span className="kw">from</span> m3_validator <span className="kw">import</span> <span className="fn">Validator</span><br />
            <br />
            m1 = <span className="fn">TaxonomyMapper</span>()<br />
            m2 = <span className="fn">AutoTagger</span>(taxonomy_mapper=m1)<br />
            m3 = <span className="fn">Validator</span>()<br />
            <br />
            <span className="cm"># DART API → M1 매핑 → M2 iXBRL 태깅 → M3 검증</span><br />
            tagged = m2.<span className="fn">tag_financial_statement</span>(data, period_end=<span className="str">"2024-12-31"</span>)<br />
            report = m3.<span className="fn">validate</span>(tagged)<br />
            <span className="kw">print</span>(report[<span className="str">'status'</span>])  <span className="cm"># → PASS</span>
          </div>
        </div>
      </section>

      <div className="divider" />

      {/* ===== FEATURES ===== */}
      <section>
        <div className="container">
          <div className="section-label">Features</div>
          <h2 className="section-title">핵심 기능</h2>
          <p className="section-desc">
            공시 담당자가 수작업으로 수행하던 XBRL 태깅, 검증, 변경추적 업무를
            자동화하여 정확도와 효율을 극대화합니다.
          </p>
          <div className="cards-grid">
            {features.map((f, i) => (
              <div key={i} className="card">
                <div className={`card-icon ${f.color}`}>{f.icon}</div>
                <h3>{f.title}</h3>
                <p>{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <div className="divider" />

      {/* ===== RESULTS ===== */}
      <section id="results">
        <div className="container">
          <div className="section-label">Validation Results</div>
          <h2 className="section-title">실데이터 검증 결과</h2>
          <p className="section-desc">
            DART API에서 조회한 2024년 사업보고서 기준 실제 연결재무제표 데이터로
            파이프라인 전체를 실행한 결과입니다.
          </p>
          <div className="company-grid">
            {companies.map((c) => (
              <div key={c.name} className="company-card">
                <div className="company-header">
                  <span className="company-name">{c.name}</span>
                  <span className="pass-badge">PASS</span>
                </div>
                <div className="metric-row">
                  <span className="metric-label">자산총계</span>
                  <span className="metric-value">{c.assets}</span>
                </div>
                <div className="metric-row">
                  <span className="metric-label">매출액</span>
                  <span className="metric-value">{c.revenue}</span>
                </div>
                <div className="metric-row">
                  <span className="metric-label">영업이익</span>
                  <span className="metric-value">{c.op_income}</span>
                </div>
                <div className="metric-row">
                  <span className="metric-label">M1 매핑률</span>
                  <span className="metric-value green">{c.mapping}</span>
                </div>
                <div className="metric-row">
                  <span className="metric-label">M2 태깅률</span>
                  <span className="metric-value green">{c.coverage}</span>
                </div>
                <div className="metric-row">
                  <span className="metric-label">변경사항</span>
                  <span className="metric-value accent">{c.changes}건 (중요 {c.material}건)</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <div className="divider" />

      {/* ===== VALIDATION DETAIL ===== */}
      <section>
        <div className="container">
          <div className="section-label">Validation Rules</div>
          <h2 className="section-title">M3 검증 체계 상세</h2>
          <p className="section-desc">
            6가지 검증 규칙으로 XBRL 태깅 데이터의 정확성과 완전성을 보장합니다.
            ERROR 0개를 달성해야 PASS로 판정됩니다.
          </p>
          <div className="cards-grid">
            <div className="card">
              <h3>CHECK 1 — 필수 항목 존재</h3>
              <p>Assets, Liabilities, Equity, CurrentAssets, NoncurrentAssets 등 재무상태표 핵심 요소의 존재 여부를 검사합니다.</p>
            </div>
            <div className="card">
              <h3>CHECK 2 — Calculation Linkbase</h3>
              <p>자산총계=유동자산+비유동자산, 부채총계=유동부채+비유동부채 등 부모-자식 합산 관계를 검증합니다.</p>
            </div>
            <div className="card">
              <h3>CHECK 3 — BS 균형 검증</h3>
              <p>자산=부채+자본 등식과 부채와자본총계=자산총계 교차검증을 수행합니다. 1원 차이도 ERROR로 판정합니다.</p>
            </div>
            <div className="card">
              <h3>CHECK 4 — 음수 값 검사</h3>
              <p>자산, 현금성자산, 재고자산 등 양수만 허용되는 항목의 음수 여부를 검사합니다.</p>
            </div>
            <div className="card">
              <h3>CHECK 5 — 태깅 완성도</h3>
              <p>금액이 있으나 iXBRL 태그가 없는 미태깅 항목과, 표준 Taxonomy에 없는 확장항목을 식별합니다.</p>
            </div>
            <div className="card">
              <h3>CHECK 6 — 이상치 탐지</h3>
              <p>전기 대비 100% 이상 변동을 WARNING으로 감지합니다. 실제 사업 변화로 인한 정당한 변동일 수 있으므로 검토 항목으로 분류합니다.</p>
            </div>
          </div>
        </div>
      </section>

      <div className="divider" />

      {/* ===== TECH STACK ===== */}
      <section>
        <div className="container">
          <div className="section-label">Tech Stack</div>
          <h2 className="section-title">기술 스택</h2>
          <div className="tech-pills">
            {techStack.map((t) => (
              <span key={t} className="tech-pill">{t}</span>
            ))}
          </div>
        </div>
      </section>

      {/* ===== FOOTER ===== */}
      <footer>
        <div className="container">
          XBRL 공시 AI 자동화 플랫폼 &middot; Portfolio Project
          <br />
          <span style={{ marginTop: 8, display: 'inline-block' }}>
            Built by <a href="mailto:jkcpakim@gmail.com">JK Kim, CPA</a>
          </span>
        </div>
      </footer>
    </main>
  )
}
