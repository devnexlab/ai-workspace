import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'

dayjs.locale('zh-cn')

/** 日期时间：2026-08-04 10:37 */
export function formatDateTime(value) {
  if (value == null || value === '') return '-'
  const d = dayjs(value)
  if (!d.isValid()) {
    const s = String(value).trim()
    return s || '-'
  }
  return d.format('YYYY-MM-DD HH:mm')
}

/** 仅日期：2026-08-04 */
export function formatDate(value) {
  if (value == null || value === '') return '-'
  const d = dayjs(value)
  if (!d.isValid()) {
    const s = String(value).trim()
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
