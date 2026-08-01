/**
 * 设置页字段渲染与保存工具
 */
import { Input, Select, Switch } from 'antd'

const { TextArea } = Input

export function flattenValues(settings) {
  const v = {}
  Object.entries(settings || {}).forEach(([cat, items]) => {
    ;(items || []).forEach(item => {
      v[`${item.category}.${item.key}`] = item.value
    })
  })
  return v
}

export function groupValues(values) {
  const grouped = {}
  Object.entries(values).forEach(([key, val]) => {
    const dot = key.indexOf('.')
    if (dot < 0) return
    const cat = key.slice(0, dot)
    const k = key.slice(dot + 1)
    if (!grouped[cat]) grouped[cat] = {}
    grouped[cat][k] = val
  })
  return grouped
}

export function renderSettingField(item, values, setValues) {
  const fieldKey = `${item.category}.${item.key}`
  const val = values[fieldKey] ?? item.value
  const onChange = (v) => setValues(prev => ({ ...prev, [fieldKey]: v }))

  if (item.key === 'enabled' && item.field_type === 'select') {
    const checked = String(val) === 'true'
    return (
      <Switch
        checked={checked}
        checkedChildren="启用"
        unCheckedChildren="关闭"
        onChange={c => onChange(c ? 'true' : 'false')}
      />
    )
  }
  if (item.field_type === 'password') {
    return <Input.Password value={val} onChange={e => onChange(e.target.value)} placeholder={item.description} />
  }
  if (item.field_type === 'textarea') {
    return <TextArea value={val} onChange={e => onChange(e.target.value)} rows={4} placeholder={item.description} />
  }
  if (item.field_type === 'select' && item.options) {
    const opts = typeof item.options === 'string' ? JSON.parse(item.options) : item.options
    return (
      <Select
        value={val}
        onChange={onChange}
        style={{ width: '100%' }}
        options={(opts || []).map(o => ({ label: String(o), value: String(o) }))}
      />
    )
  }
  return <Input value={val} onChange={e => onChange(e.target.value)} placeholder={item.description} />
}
