import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'

dayjs.locale('zh-cn')

/**
 * 解析后端时间。
 * Flask 默认会把无时区 datetime 序列化成 "... GMT"，但库里实际存的是北京时间，
 * 若按 GMT/UTC 再转本地会多出 8 小时。这里统一按「墙钟北京时间」展示。
 */
function parseAppTime(value) {
  if (value == null || value === '') return null
  if (dayjs.isDayjs?.(value)) return value.isValid() ? value : null
  if (value instanceof Date) {
    const d = dayjs(value)
    return d.isValid() ? d : null
  }

  const raw = String(value).trim()
  if (!raw) return null

  // "Wed, 05 Aug 2026 14:18:59 GMT" —— 去掉 GMT，按本地墙钟解析
  const rfcGmt = raw.match(
    /^[A-Za-z]{3},\s+(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})\s+(\d{2}):(\d{2}):(\d{2})\s+GMT$/i,
  )
  if (rfcGmt) {
    const months = {
      jan: 0, feb: 1, mar: 2, apr: 3, may: 4, jun: 5,
      jul: 6, aug: 7, sep: 8, oct: 9, nov: 10, dec: 11,
    }
    const mon = months[rfcGmt[2].toLowerCase()]
    if (mon != null) {
      const d = dayjs(new Date(
        Number(rfcGmt[3]),
        mon,
        Number(rfcGmt[1]),
        Number(rfcGmt[4]),
        Number(rfcGmt[5]),
        Number(rfcGmt[6]),
      ))
      return d.isValid() ? d : null
    }
  }

  // ISO 带 Z：若时间看起来像「被误标的本地时间」，去掉 Z 再按本地解析
  // 例：2026-08-05T14:18:59.000Z（实际是北京 14:18）
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/i.test(raw)) {
    const d = dayjs(raw.replace(/Z$/i, ''))
    return d.isValid() ? d : null
  }

  const d = dayjs(raw)
  return d.isValid() ? d : null
}

/** 日期时间：2026-08-04 10:37 */
export function formatDateTime(value) {
  const d = parseAppTime(value)
  if (!d) {
    const s = value == null ? '' : String(value).trim()
    return s || '-'
  }
  return d.format('YYYY-MM-DD HH:mm')
}

/** 仅日期：2026-08-04 */
export function formatDate(value) {
  const d = parseAppTime(value)
  if (!d) {
    const s = value == null ? '' : String(value).trim()
    return s ? s.slice(0, 10) : '-'
  }
  return d.format('YYYY-MM-DD')
}

/** 表格列快捷渲染 */
export const dateTimeColumn = (title = '时间', dataIndex = 'created_at', width = 160) => ({
  title,
  dataIndex,
  width,
  render: (v) => formatDateTime(v),
})

export const dateColumn = (title = '日期', dataIndex = 'remind_date', width = 120) => ({
  title,
  dataIndex,
  width,
  render: (v) => formatDate(v),
})

export default { formatDateTime, formatDate, dateTimeColumn, dateColumn }
