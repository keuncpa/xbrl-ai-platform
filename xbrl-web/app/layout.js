import './globals.css'

export const metadata = {
  title: 'XBRL 공시 AI 자동화 플랫폼',
  description: 'KOR-IFRS XBRL Taxonomy 매핑, iXBRL 태깅, 검증, 변경추적 자동화',
}
export default function RootLayout({ children }) {
  return (
    <html lang="ko">
      <head>
        <link href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css" rel="stylesheet" />
      </head>
      <body>{children}</body>
    </html>
  )
}
