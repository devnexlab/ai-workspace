import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Tag, Empty, Typography } from 'antd'
import './StockBrief.css'

const { Text } = Typography

const SECTION_META = {
  要点速览: { tone: 'points', label: '要点速览' },
  市场情绪判断: { tone: 'mood', label: '市场情绪' },
  市场情绪: { tone: 'mood', label: '市场情绪' },
  主线题材: { tone: 'theme', label: '主线题材' },
  '主线题材 / 板块观察': { tone: 'theme', label: '主线题材' },
  板块观察: { tone: 'theme', label: '板块观察' },
  风险提示: { tone: 'risk', label: '风险提示' },
  可跟进关注点: { tone: 'watch', label: '可跟进关注点' },
  板块与题材: { tone: 'theme', label: '板块与题材' },
  公司与个股动态: { tone: 'theme', label: '公司动态' },
  说明: { tone: 'note', label: '说明' },
}

function splitSections(md) {
  const text = (md || '').trim()
  if (!text) return { title: '', source: '', sections: [] }

  const lines = text.split(/\r?\n/)
  let title = ''
  let source = ''
  const sections = []
  let cur = null

  const push = () => {
    if (cur) {
      cur.body = cur.lines.join('\n').trim()
      sections.push(cur)
    }
  }

  for (const line of lines) {
    const h1 = line.match(/^#\s+(.+)/)
    if (h1 && !title) {
      title = h1[1].trim()
      continue
    }
    if (/^>\s*/.test(line) && !source) {
      source = line.replace(/^>\s*/, '').trim()
      continue
    }
    const h2 = line.match(/^##\s+(.+)/)
    if (h2) {
      push()
      const name = h2[1].trim()
      const meta = SECTION_META[name] || Object.entries(SECTION_META).find(([k]) => name.includes(k))?.[1]
      cur = {
        name,
        tone: meta?.tone || 'default',
        label: meta?.label || name,
        lines: [],
      }
      continue
    }
    if (!cur) {
      // preamble before first ##
      continue
    }
    cur.lines.push(line)
  }
  push()
  return { title, source, sections }
}

function moodTag(body) {
  const t = body || ''
  if (/谨慎|偏空|弱势|回落/.test(t)) return { color: 'orange', text: '谨慎' }
  if (/偏多|强势|乐观|积极/.test(t)) return { color: 'red', text: '偏多' }
  if (/中性/.test(t)) return { color: 'blue', text: '中性' }
  return { color: 'default', text: '情绪解读' }
}

function PointsList({ body }) {
  // 解析 "1. **标题**（来源）" + 可选 "- 摘要"
  const blocks = []
  let current = null
  for (const raw of (body || '').split(/\n/)) {
    const line = raw.trim()
    if (!line) continue
    const m = line.match(/^\d+\.\s+\*\*(.+?)\*\*(?:（(.+?)）)?/)
      || line.match(/^\d+\.\s+(.+?)(?:（(.+?)）)?$/)
    if (m) {
      if (current) blocks.push(current)
      current = { title: m[1].trim(), source: (m[2] || '').trim(), summary: '' }
      continue
    }
    if (current && /^[-*•]\s+/.test(line)) {
      current.summary = line.replace(/^[-*•]\s+/, '').trim()
      continue
    }
    if (current && !current.summary) {
      current.summary = line.replace(/^\*\*|\*\*$/g, '')
    }
  }
  if (current) blocks.push(current)

  if (!blocks.length) {
    return <ReactMarkdown remarkPlugins={[remarkGfm]}>{body}</ReactMarkdown>
  }

  return (
    <ol className="stock-brief-points">
      {blocks.map((b, i) => (
        <li key={i}>
          <div className="stock-brief-point-title">
            <span>{b.title}</span>
            {b.source ? <Tag className="stock-brief-source-tag">{b.source}</Tag> : null}
          </div>
          {b.summary ? <div className="stock-brief-point-summary">{b.summary}</div> : null}
        </li>
      ))}
    </ol>
  )
}

export default function BriefMarkdown({ text, placeholder, variant = 'brief' }) {
  if (!text) {
    return (
      <div className="stock-intel-empty">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={placeholder || '暂无内容'} />
      </div>
    )
  }

  const { title, source, sections } = splitSections(text)

  // 无法分段时，整篇 Markdown 渲染
  if (!sections.length) {
    return (
      <div className={`stock-brief-doc stock-brief-doc--${variant}`}>
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
      </div>
    )
  }

  return (
    <div className={`stock-brief-doc stock-brief-doc--${variant}`}>
      {(title || source) && (
        <header className="stock-brief-header">
          {title ? <h2 className="stock-brief-title">{title.replace(/^#\s*/, '')}</h2> : null}
          {source ? <Text type="secondary" className="stock-brief-meta">{source}</Text> : null}
        </header>
      )}

      <div className="stock-brief-sections">
        {sections.map((sec) => {
          const mood = sec.tone === 'mood' ? moodTag(sec.body) : null
          return (
            <section key={sec.name} className={`stock-brief-section stock-brief-section--${sec.tone}`}>
              <div className="stock-brief-section-head">
                <span className="stock-brief-section-label">{sec.label}</span>
                {mood ? <Tag color={mood.color}>{mood.text}</Tag> : null}
              </div>
              <div className="stock-brief-section-body">
                {sec.tone === 'points'
                  ? <PointsList body={sec.body} />
                  : <ReactMarkdown remarkPlugins={[remarkGfm]}>{sec.body}</ReactMarkdown>}
              </div>
            </section>
          )
        })}
      </div>
    </div>
  )
}
