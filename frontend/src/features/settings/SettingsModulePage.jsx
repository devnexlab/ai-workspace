import { useEffect, useState } from 'react'
import { useOutletContext, useParams } from 'react-router-dom'
import {
  Alert, Button, Card, Form, Space, Spin, Tag, message,
} from 'antd'
import {
  SaveOutlined, CheckCircleOutlined, ExclamationCircleOutlined,
} from '@ant-design/icons'
import { settingsApi } from '../../api'
import { flattenValues, groupValues, renderSettingField } from './settingUtils'

/**
 * 通用模块页：按 categories 渲染表单（AI / 配音视频 / 内容运营）
 */
export default function SettingsModulePage() {
  const { moduleKey } = useParams()
  const { modules } = useOutletContext() || {}
  const mod = (modules || []).find(m => m.path === moduleKey)

  const [settings, setSettings] = useState({})
  const [readiness, setReadiness] = useState({})
  const [values, setValues] = useState({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  const load = () => {
    setLoading(true)
    Promise.all([settingsApi.get(), settingsApi.check()])
      .then(([s, r]) => {
        setSettings(s)
        setReadiness(r)
        setValues(flattenValues(s))
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [moduleKey])

  if (!mod) {
    return <Alert type="warning" message="未知配置模块" />
  }

  // 平台型模块交给 PlatformsPage
  if (mod.type === 'collector_platforms' || mod.type === 'publish_platforms') {
    return <PlatformsPage mod={mod} />
  }

  const handleSave = () => {
    setSaving(true)
    const cats = mod.categories || []
    const all = groupValues(values)
    const payload = {}
    cats.forEach(c => {
      if (all[c]) payload[c] = all[c]
    })
    settingsApi.update(payload)
      .then(() => {
        message.success('已保存')
        load()
      })
      .catch(() => message.error('保存失败'))
      .finally(() => setSaving(false))
  }

  if (loading) {
    return <div style={{ textAlign: 'center', padding: 60 }}><Spin /></div>
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
        <div>
          <div style={{ fontSize: 18, fontWeight: 600 }}>{mod.label}</div>
          <div style={{ color: '#888', fontSize: 13, marginTop: 4 }}>{mod.desc}</div>
        </div>
        <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={handleSave}>
          保存
        </Button>
      </div>

      {(mod.categories || []).map(cat => {
        const items = settings[cat]
        if (!items?.length) return null
        const ready = readiness[cat] || readiness[mod.key]
        return (
          <Card
            key={cat}
            style={{ marginBottom: 16 }}
            title={cat === 'ai' ? '模型与 API' : cat === 'tts' ? '配音 (TTS)' : cat === 'video' ? '视频制作' : cat === 'system' ? '内容与采集策略' : cat}
            extra={ready && (
              ready.ready
                ? <Tag icon={<CheckCircleOutlined />} color="success">就绪</Tag>
                : <Tag icon={<ExclamationCircleOutlined />} color="warning">待配置</Tag>
            )}
          >
            <Form layout="vertical">
              {items.map(item => (
                <Form.Item key={item.key} label={item.label} extra={item.description}>
                  {renderSettingField(item, values, setValues)}
                </Form.Item>
              ))}
            </Form>
          </Card>
        )
      })}
    </div>
  )
}

function PlatformsPage({ mod }) {
  const [settings, setSettings] = useState({})
  const [readiness, setReadiness] = useState({})
  const [values, setValues] = useState({})
  const [loading, setLoading] = useState(true)
  const [savingKey, setSavingKey] = useState(null)
  const [activeKey, setActiveKey] = useState(null)

  const platforms = mod.platforms || []
  const isCollector = mod.type === 'collector_platforms'

  const load = () => {
    setLoading(true)
    Promise.all([settingsApi.get(), settingsApi.check()])
      .then(([s, r]) => {
        setSettings(s)
        setReadiness(r)
        setValues(flattenValues(s))
        if (!activeKey && platforms[0]) setActiveKey(platforms[0].key)
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [mod.key])

  const savePlatform = (platform) => {
    const cat = platform.category
    setSavingKey(platform.key)
    const all = groupValues(values)
    settingsApi.update({ [cat]: all[cat] || {} })
      .then(() => {
        message.success(`${platform.label} 配置已保存`)
        load()
      })
      .catch(() => message.error('保存失败'))
      .finally(() => setSavingKey(null))
  }

  if (loading) {
    return <div style={{ textAlign: 'center', padding: 60 }}><Spin /></div>
  }

  const moduleReady = readiness[mod.key]
  const current = platforms.find(p => p.key === activeKey) || platforms[0]

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 18, fontWeight: 600 }}>{mod.label}</div>
        <div style={{ color: '#888', fontSize: 13, marginTop: 4 }}>{mod.desc}</div>
        {moduleReady && (
          <Alert
            style={{ marginTop: 12 }}
            type={moduleReady.ready ? 'success' : 'info'}
            showIcon
            message={moduleReady.message}
            description={
              isCollector
                ? '一次只配置一个平台：点左侧平台卡片，填 Cookies / 关键词后单独保存。新增平台只需后端注册表登记即可出现。'
                : '一次只配置一个发布平台。启用并填写 Cookies 后，发布中心才能推送到对应账号。'
            }
          />
        )}
      </div>

      <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
        {/* 平台列表 */}
        <div style={{ width: 200, flexShrink: 0 }}>
          {platforms.map(p => {
            const ready = readiness[p.category]
            const selected = current?.key === p.key
            return (
              <Card
                key={p.key}
                size="small"
                hoverable
                onClick={() => setActiveKey(p.key)}
                style={{
                  marginBottom: 8,
                  borderColor: selected ? '#1677ff' : undefined,
                  background: selected ? '#f0f5ff' : undefined,
                  cursor: 'pointer',
                }}
              >
                <div style={{ fontWeight: 600 }}>{p.label}</div>
                <div style={{ fontSize: 12, color: '#888', marginTop: 4 }}>{p.desc}</div>
                <div style={{ marginTop: 8 }}>
                  {ready?.ready
                    ? <Tag color="success">Cookies 已填</Tag>
                    : <Tag color="default">未配置</Tag>}
                  {ready && ready.enabled === false && <Tag color="orange">已关闭</Tag>}
                </div>
              </Card>
            )
          })}
        </div>

        {/* 当前平台表单 */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {current && (
            <Card
              title={
                <Space>
                  {current.label}
                  <Tag>{isCollector ? '采集' : '发布'}</Tag>
                </Space>
              }
              extra={
                <Button
                  type="primary"
                  icon={<SaveOutlined />}
                  loading={savingKey === current.key}
                  onClick={() => savePlatform(current)}
                >
                  保存本平台
                </Button>
              }
            >
              <p style={{ color: '#888', marginBottom: 16 }}>{current.desc}</p>
              <Form layout="vertical">
                {(settings[current.category] || []).map(item => (
                  <Form.Item key={item.key} label={item.label} extra={item.description}>
                    {renderSettingField(item, values, setValues)}
                  </Form.Item>
                ))}
                {!(settings[current.category] || []).length && (
                  <Alert type="warning" message="该平台尚未在数据库中初始化配置项，请重启后端或检查 seed。" />
                )}
              </Form>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}
