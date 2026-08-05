import { useEffect, useState } from 'react'
import { useOutletContext, useParams } from 'react-router-dom'
import {
  Alert, Button, Card, Checkbox, Form, Input, Modal, Select, Space, Spin, Tag, message, Popconfirm,
} from 'antd'
import {
  SaveOutlined, CheckCircleOutlined, ExclamationCircleOutlined, PlusOutlined, DeleteOutlined,
  ExperimentOutlined,
} from '@ant-design/icons'
import { settingsApi, platformsApi } from '../../api'
import { flattenValues, groupValues, renderSettingField } from './settingUtils'

const COLOR_OPTIONS = [
  { value: 'green', label: '绿' },
  { value: 'black', label: '黑' },
  { value: 'red', label: '红' },
  { value: 'blue', label: '蓝' },
  { value: 'orange', label: '橙' },
  { value: 'purple', label: '紫' },
  { value: 'cyan', label: '青' },
]

const CATEGORY_TITLES = {
  ai: '模型与 API',
  tts: '配音 (TTS)',
  video: '视频制作',
  system: '内容与采集策略',
}

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

  // 平台型模块：左侧列表 + 右侧表单
  if (
    mod.type === 'collector_platforms'
    || mod.type === 'publish_platforms'
    || mod.type === 'commercial_providers'
  ) {
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
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16, gap: 12, flexWrap: 'wrap' }}>
        <div>
          <div className="page-title">{mod.label}</div>
          <div className="page-desc" style={{ marginBottom: 0 }}>{mod.desc}</div>
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
            title={CATEGORY_TITLES[cat] || cat}
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
  const { reloadModules } = useOutletContext() || {}
  const [settings, setSettings] = useState({})
  const [readiness, setReadiness] = useState({})
  const [values, setValues] = useState({})
  const [loading, setLoading] = useState(true)
  const [savingKey, setSavingKey] = useState(null)
  const [testingKey, setTestingKey] = useState(null)
  const [activeKey, setActiveKey] = useState(null)
  const [addOpen, setAddOpen] = useState(false)
  const [adding, setAdding] = useState(false)
  const [form] = Form.useForm()

  const platforms = mod.platforms || []
  const isCollector = mod.type === 'collector_platforms'
  const isPublish = mod.type === 'publish_platforms'
  const isCommercial = mod.type === 'commercial_providers'

  const load = () => {
    setLoading(true)
    Promise.all([settingsApi.get(), settingsApi.check()])
      .then(([s, r]) => {
        setSettings(s)
        setReadiness(r)
        setValues(flattenValues(s))
        setActiveKey(prev => {
          if (prev && platforms.some(p => p.key === prev)) return prev
          return platforms[0]?.key || null
        })
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [mod.key, platforms.map(p => p.key).join(',')])

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

  const handleTestCommercial = (platform) => {
    setTestingKey(platform.key)
    const cat = platform.category
    const all = groupValues(values)
    settingsApi.update({ [cat]: all[cat] || {} })
      .then(() => settingsApi.testCommercial(platform.key))
      .then(res => {
        if (res.ok) {
          const sample = (res.items || []).map(i => i.title).filter(Boolean).slice(0, 3).join('；')
          message.success(`${res.message}${sample ? `：${sample}` : ''}`)
          load()
        } else {
          message.error(res.message || '试拉失败')
        }
      })
      .catch(err => message.error(err?.message || err?.error || '试拉失败'))
      .finally(() => setTestingKey(null))
  }

  const handleAdd = () => {
    form.validateFields().then(vals => {
      setAdding(true)
      const payload = {
        key: vals.key,
        label: vals.label,
        color: vals.color || 'blue',
        desc: vals.desc || '',
        cookie_domain: vals.cookie_domain || '',
        creator_url: vals.creator_url || '',
        search_url_template: vals.search_url_template || '',
        enable_collector: !!vals.enable_collector,
        enable_publish: !!vals.enable_publish,
      }
      platformsApi.create(payload)
        .then(res => {
          message.success(res.message || '平台已添加')
          setAddOpen(false)
          form.resetFields()
          return reloadModules?.()
        })
        .then(() => {
          setActiveKey(vals.key)
          load()
        })
        .catch(err => message.error(err?.error || '添加失败'))
        .finally(() => setAdding(false))
    })
  }

  const handleDelete = (platform) => {
    platformsApi.delete(platform.key)
      .then(res => {
        message.success(res.message || '已删除')
        return reloadModules?.()
      })
      .then(() => {
        setActiveKey(null)
        load()
      })
      .catch(err => message.error(err?.error || '删除失败'))
  }

  if (loading) {
    return <div style={{ textAlign: 'center', padding: 60 }}><Spin /></div>
  }

  const moduleReady = readiness[mod.key]
  const current = platforms.find(p => p.key === activeKey) || platforms[0]

  const statusTag = (ready) => {
    if (isCommercial) {
      if (ready?.enabled === false) return <Tag color="orange">已关闭</Tag>
      if (ready?.ready && ready?.enabled) return <Tag color="success">API 已配</Tag>
      if (ready?.enabled) return <Tag color="warning">待配 API</Tag>
      return <Tag color="default">未启用</Tag>
    }
    return (
      <>
        {ready?.ready
          ? <Tag color="success">{isCollector ? 'Cookies 已填' : '已启用'}</Tag>
          : <Tag color="default">未配置</Tag>}
        {ready && ready.enabled === false && <Tag color="orange">已关闭</Tag>}
      </>
    )
  }

  const alertDesc = isCommercial
    ? '填入官方/企业 API 的 Base URL、Key、榜单路径与字段映射；点「试拉」验证后，到内容情报「拉官方数据台」。不用 Cookie 爬网页。'
    : isCollector
      ? '【重要】抖音/小红书等登录态自动采集易封号，默认已关闭。日常请用内容情报「全网热榜」选题。仅实验需要时再开启并填写 Cookies。'
      : '推荐：发布中心「准备发布」复制文案并打开官方创作者页，由你手动点发表。Cookies / Playwright 仅高级自动填充需要（有封号风险）。'

  const typeTag = isCommercial ? '数据台' : isCollector ? '采集' : '发布'

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16, flexWrap: 'wrap' }}>
        <div>
          <div className="page-title">{mod.label}</div>
          <div className="page-desc" style={{ marginBottom: 0 }}>{mod.desc}</div>
          {moduleReady && (
            <Alert
              style={{ marginTop: 12 }}
              type={isCollector ? 'warning' : 'info'}
              showIcon
              message={moduleReady.message}
              description={alertDesc}
            />
          )}
        </div>
        {!isCommercial && (
          <Button type="primary" icon={<PlusOutlined />} onClick={() => {
            form.resetFields()
            form.setFieldsValue({
              enable_collector: isCollector,
              enable_publish: isPublish,
              color: 'blue',
            })
            setAddOpen(true)
          }}>
            添加平台
          </Button>
        )}
      </div>

      <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
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
                <div style={{ fontWeight: 600 }}>
                  {p.label}
                  {!p.builtin && <Tag style={{ marginLeft: 6 }} color="processing">自定义</Tag>}
                </div>
                <div style={{ fontSize: 12, color: '#888', marginTop: 4 }}>{p.desc}</div>
                <div style={{ marginTop: 8 }}>
                  {statusTag(ready)}
                </div>
              </Card>
            )
          })}
          {!platforms.length && (
            <Alert type="info" message="暂无平台，点击右上角添加" />
          )}
        </div>

        <div style={{ flex: 1, minWidth: 0 }}>
          {current && (
            <Card
              title={
                <Space>
                  {current.label}
                  <Tag>{typeTag}</Tag>
                  {!current.builtin && <Tag color="processing">自定义</Tag>}
                </Space>
              }
              extra={
                <Space>
                  {isCommercial && (
                    <Button
                      icon={<ExperimentOutlined />}
                      loading={testingKey === current.key}
                      onClick={() => handleTestCommercial(current)}
                    >
                      试拉
                    </Button>
                  )}
                  {!isCommercial && !current.builtin && (
                    <Popconfirm
                      title={`删除平台「${current.label}」？`}
                      description="将同时删除对应配置项，不可恢复"
                      onConfirm={() => handleDelete(current)}
                    >
                      <Button danger icon={<DeleteOutlined />}>删除</Button>
                    </Popconfirm>
                  )}
                  <Button
                    type="primary"
                    icon={<SaveOutlined />}
                    loading={savingKey === current.key}
                    onClick={() => savePlatform(current)}
                  >
                    保存本{isCommercial ? '数据源' : '平台'}
                  </Button>
                </Space>
              }
            >
              <p style={{ color: '#888', marginBottom: 16 }}>{current.desc}</p>
              {!isCommercial && !current.builtin && (
                <Alert
                  style={{ marginBottom: 16 }}
                  type="info"
                  showIcon
                  message={
                    isCollector
                      ? `搜索模板：${current.search_url_template || '未填'}；Cookie 域名：${current.cookie_domain || '自动'}`
                      : `创作者后台：${current.creator_url || '未填'}；Cookie 域名：${current.cookie_domain || '自动'}`
                  }
                />
              )}
              <Form layout="vertical">
                {(settings[current.category] || []).map(item => (
                  <Form.Item key={item.key} label={item.label} extra={item.description}>
                    {renderSettingField(item, values, setValues)}
                  </Form.Item>
                ))}
                {!(settings[current.category] || []).length && (
                  <Alert type="warning" message="该平台尚未初始化配置项，请刷新页面或重启后端以写入默认配置。" />
                )}
              </Form>
            </Card>
          )}
        </div>
      </div>

      {!isCommercial && (
        <Modal
          title="添加平台"
          open={addOpen}
          onOk={handleAdd}
          confirmLoading={adding}
          onCancel={() => setAddOpen(false)}
          width={640}
          destroyOnClose
        >
          <Form form={form} layout="vertical" style={{ marginTop: 8 }}>
            <Form.Item name="key" label="平台标识" rules={[
              { required: true, message: '必填' },
              { pattern: /^[a-z][a-z0-9_]{1,31}$/, message: '小写字母开头，仅 a-z/0-9/_，2-32 位' },
            ]} extra="如 kuaishou、bilibili，创建后不可改">
              <Input placeholder="kuaishou" />
            </Form.Item>
            <Form.Item name="label" label="显示名称" rules={[{ required: true }]}>
              <Input placeholder="快手" />
            </Form.Item>
            <Form.Item name="desc" label="简介">
              <Input placeholder="可选" />
            </Form.Item>
            <Form.Item name="color" label="标签颜色">
              <Select options={COLOR_OPTIONS} />
            </Form.Item>
            <Form.Item name="cookie_domain" label="Cookie 域名" extra="如 .kuaishou.com；不填则从 URL 自动推断">
              <Input placeholder=".kuaishou.com" />
            </Form.Item>
            <Form.Item name="enable_collector" valuePropName="checked">
              <Checkbox>用于采集</Checkbox>
            </Form.Item>
            <Form.Item
              noStyle
              shouldUpdate={(prev, cur) => prev.enable_collector !== cur.enable_collector}
            >
              {({ getFieldValue }) => getFieldValue('enable_collector') ? (
                <Form.Item
                  name="search_url_template"
                  label="搜索页 URL 模板"
                  rules={[{ required: true, message: '采集需要搜索模板' }]}
                  extra="必须包含 {keyword}，例如 https://www.kuaishou.com/search/video?searchKey={keyword}"
                >
                  <Input placeholder="https://www.example.com/search?q={keyword}" />
                </Form.Item>
              ) : null}
            </Form.Item>
            <Form.Item name="enable_publish" valuePropName="checked">
              <Checkbox>用于发布</Checkbox>
            </Form.Item>
            <Form.Item
              noStyle
              shouldUpdate={(prev, cur) => prev.enable_publish !== cur.enable_publish}
            >
              {({ getFieldValue }) => getFieldValue('enable_publish') ? (
                <Form.Item
                  name="creator_url"
                  label="创作者后台地址"
                  rules={[{ required: true, message: '发布需要创作者后台 URL' }]}
                  extra="发布时会打开此页面并注入 Cookies"
                >
                  <Input placeholder="https://cp.kuaishou.com/article/publish/video" />
                </Form.Item>
              ) : null}
            </Form.Item>
          </Form>
        </Modal>
      )}
    </div>
  )
}
