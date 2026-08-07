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
  notify: '微信推送',
  wechat_oa: '微信服务号',
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

  if (mod.type === 'notify_channels') {
    return <NotifyChannelsPage mod={mod} />
  }

  if (mod.type === 'ai_providers') {
    return <AiProvidersPage mod={mod} />
  }

  if (mod.type === 'wechat_oa') {
    return <WechatOaSettingsPage mod={mod} />
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

function NotifyChannelsPage({ mod }) {
  const [settings, setSettings] = useState({})
  const [readiness, setReadiness] = useState({})
  const [values, setValues] = useState({})
  const [loading, setLoading] = useState(true)
  const [savingKey, setSavingKey] = useState(null)
  const [testingKey, setTestingKey] = useState(null)
  const [activeKey, setActiveKey] = useState(null)

  const channels = mod.platforms || []

  const load = () => {
    setLoading(true)
    Promise.all([settingsApi.get(), settingsApi.check()])
      .then(([s, r]) => {
        setSettings(s)
        setReadiness(r)
        setValues(flattenValues(s))
        setActiveKey(prev => {
          if (prev && channels.some(p => p.key === prev)) return prev
          return channels[0]?.key || null
        })
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [mod.key, channels.map(p => p.key).join(',')])

  const saveChannel = (channel) => {
    const cat = channel.category
    setSavingKey(channel.key)
    const all = groupValues(values)
    const payload = { [cat]: all[cat] || {} }

    // 启用某一渠道时，关闭其他渠道（规则卡片除外）
    if (channel.key !== 'rules') {
      const enabling = String(payload[cat]?.enabled || '').toLowerCase() === 'true'
      if (enabling) {
        channels.forEach(c => {
          if (c.key === 'rules' || c.key === channel.key) return
          payload[c.category] = {
            ...(all[c.category] || {}),
            enabled: 'false',
          }
        })
      }
    }

    settingsApi.update(payload)
      .then(() => {
        message.success(`${channel.label} 已保存`)
        load()
      })
      .catch(() => message.error('保存失败'))
      .finally(() => setSavingKey(null))
  }

  const handleTest = (channel) => {
    if (channel.key === 'rules') return
    setTestingKey(channel.key)
    const cat = channel.category
    const all = groupValues(values)
    const payload = { [cat]: all[cat] || {} }
    settingsApi.update(payload)
      .then(() => settingsApi.testNotify({ channel: channel.key }))
      .then((res) => {
        message.success(res?.message || '测试消息已发送')
        load()
      })
      .catch((err) => message.error(err?.error || err?.message || '测试失败'))
      .finally(() => setTestingKey(null))
  }

  if (loading) {
    return <div style={{ textAlign: 'center', padding: 60 }}><Spin /></div>
  }

  const moduleReady = readiness[mod.key]
  const current = channels.find(p => p.key === activeKey) || channels[0]
  const isRules = current?.key === 'rules'

  const statusTag = (channel) => {
    if (channel.key === 'rules') {
      return <Tag color="purple">事件开关</Tag>
    }
    const ready = readiness[channel.category]
    if (ready?.enabled && ready?.ready) return <Tag color="success">已启用</Tag>
    if (ready?.enabled) return <Tag color="warning">待配凭证</Tag>
    return <Tag color="default">未启用</Tag>
  }

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <div className="page-title">{mod.label}</div>
        <div className="page-desc" style={{ marginBottom: 0 }}>{mod.desc}</div>
        <Alert
          style={{ marginTop: 12 }}
          type="info"
          showIcon
          message={moduleReady?.message || '推荐启用企业微信群机器人（免费）'}
          description="上方选择推送渠道；启用一个渠道即可。企微：建群 → 添加群机器人 → 粘贴 Webhook → 保存并发送测试。"
        />
      </div>

      <div className="settings-plat-switch">
        {channels.map(p => {
          const selected = current?.key === p.key
          const ready = readiness[p.category]
          const on = !!(ready?.enabled && ready?.ready)
          return (
            <button
              key={p.key}
              type="button"
              className={`settings-plat-pill${selected ? ' active' : ''}`}
              onClick={() => setActiveKey(p.key)}
            >
              <span className={`dot ${on ? 'on' : 'off'}`} />
              {p.label}
              {p.recommended ? ' · 推荐' : ''}
            </button>
          )
        })}
      </div>

      {current && (
        <div className="settings-plat-meta">
          <span className="meta-text">{current.desc}</span>
          {statusTag(current)}
        </div>
      )}

      <div>
          {current && (
            <Card
              title={
                <Space>
                  {current.label}
                  <Tag>推送</Tag>
                  {current.recommended && <Tag color="green">推荐</Tag>}
                </Space>
              }
              extra={
                <Space>
                  {!isRules && (
                    <Button
                      icon={<ExperimentOutlined />}
                      loading={testingKey === current.key}
                      onClick={() => handleTest(current)}
                    >
                      发送测试
                    </Button>
                  )}
                  <Button
                    type="primary"
                    icon={<SaveOutlined />}
                    loading={savingKey === current.key}
                    onClick={() => saveChannel(current)}
                  >
                    保存
                  </Button>
                </Space>
              }
            >
              {!isRules && current.key === 'wecom' && (
                <Alert
                  style={{ marginBottom: 16 }}
                  type="success"
                  showIcon
                  message="企业微信免费，不用 PushPlus 实名付费"
                  description="手机企微建一个只有自己的群 → 群机器人 → 复制 Webhook 填到下方并启用。"
                />
              )}
              <Form layout="vertical">
                {(settings[current.category] || [])
                  .filter(item => !isRules || ['on_stock_alert', 'on_screening_done'].includes(item.key))
                  .map(item => (
                  <Form.Item key={item.key} label={item.label} extra={item.description}>
                    {renderSettingField(item, values, setValues)}
                  </Form.Item>
                ))}
                {!(settings[current.category] || []).length && (
                  <Alert type="warning" message="该渠道尚未初始化配置项，请刷新页面或重启后端。" />
                )}
              </Form>
            </Card>
          )}
      </div>
    </div>
  )
}

function WechatOaSettingsPage({ mod }) {
  const [settings, setSettings] = useState({})
  const [values, setValues] = useState({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [links, setLinks] = useState(null)

  const load = () => {
    setLoading(true)
    Promise.all([settingsApi.get(), settingsApi.wechatOaMenuLinks()])
      .then(([s, l]) => {
        setSettings(s)
        setValues(flattenValues(s))
        setLinks(l)
      })
      .catch(() => message.error('加载失败'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [mod.key])

  const handleSave = () => {
    setSaving(true)
    const payload = groupValues(values)
    settingsApi.update(payload)
      .then(() => {
        message.success('服务号配置已保存')
        return settingsApi.wechatOaMenuLinks()
      })
      .then(l => setLinks(l))
      .catch(() => message.error('保存失败'))
      .finally(() => setSaving(false))
  }

  const copyText = (text) => {
    if (!text) {
      message.warning('请先填写并保存「对外访问地址」')
      return
    }
    navigator.clipboard?.writeText(text)
      .then(() => message.success('已复制'))
      .catch(() => message.info(text))
  }

  if (loading) {
    return <div style={{ textAlign: 'center', padding: 60 }}><Spin /></div>
  }

  const items = settings.wechat_oa || []

  return (
    <div>
      <div className="page-title">{mod.label}</div>
      <div className="page-desc">{mod.desc}</div>

      <Alert
        style={{ marginBottom: 16 }}
        type="info"
        showIcon
        message="阶段①：服务号菜单 + 客户页（改动最小）"
        description={
          <ol style={{ margin: '8px 0 0', paddingLeft: 18 }}>
            <li>在微信公众平台注册并认证「服务号」</li>
            <li>本页填写品牌文案，打开「启用」，填客户能打开的「对外访问地址」</li>
            <li>公众平台 → 自定义菜单：介绍页 / 预约沟通，粘贴下方链接</li>
            <li>客户提交预约后，会出现在「线索池」，并尽量走消息推送通知你；转客户后再进客户列表</li>
          </ol>
        }
      />

      <Card title="菜单链接（复制到公众平台）" style={{ marginBottom: 16 }}>
        <p style={{ color: '#666', marginBottom: 12 }}>{links?.hint}</p>
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <div>
            <div style={{ marginBottom: 6 }}>介绍页</div>
            <Space.Compact style={{ width: '100%' }}>
              <Input readOnly value={links?.about_url || `（保存对外地址后生成）…${links?.about_path || '/m/about'}`} />
              <Button onClick={() => copyText(links?.about_url)}>复制</Button>
            </Space.Compact>
          </div>
          <div>
            <div style={{ marginBottom: 6 }}>预约沟通</div>
            <Space.Compact style={{ width: '100%' }}>
              <Input readOnly value={links?.book_url || `（保存对外地址后生成）…${links?.book_path || '/m/book'}`} />
              <Button onClick={() => copyText(links?.book_url)}>复制</Button>
            </Space.Compact>
          </div>
          <Space wrap>
            <Button href={links?.about_path || '/m/about'} target="_blank">本机预览介绍页</Button>
            <Button href={links?.book_path || '/m/book'} target="_blank">本机预览预约页</Button>
          </Space>
        </Space>
      </Card>

      <Card
        title="对外内容与开关"
        extra={
          <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={handleSave}>
            保存
          </Button>
        }
      >
        <Form layout="vertical">
          {items.map(item => (
            <Form.Item key={item.key} label={item.label} extra={item.description}>
              {renderSettingField(item, values, setValues)}
            </Form.Item>
          ))}
          {!items.length && (
            <Alert type="warning" message="配置项未初始化，请重启后端后再打开本页。" />
          )}
        </Form>
      </Card>
    </div>
  )
}

function AiProvidersPage({ mod }) {
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

  const cards = mod.platforms || []

  const load = () => {
    setLoading(true)
    Promise.all([settingsApi.get(), settingsApi.check()])
      .then(([s, r]) => {
        setSettings(s)
        setReadiness(r)
        setValues(flattenValues(s))
        setActiveKey(prev => {
          if (prev && cards.some(p => p.key === prev)) return prev
          const enabled = cards.find(p => p.key !== 'common' && r?.[p.category]?.enabled)
          return enabled?.key || cards[0]?.key || null
        })
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [mod.key, cards.map(p => p.key).join(',')])

  const saveCard = (card) => {
    const cat = card.category
    setSavingKey(card.key)
    const all = groupValues(values)
    const payload = { [cat]: all[cat] || {} }

    if (card.key !== 'common') {
      const enabling = String(payload[cat]?.enabled || '').toLowerCase() === 'true'
      if (enabling) {
        cards.forEach(c => {
          if (c.key === 'common' || c.key === card.key) return
          payload[c.category] = {
            ...(all[c.category] || {}),
            enabled: 'false',
          }
        })
      }
    }

    settingsApi.update(payload)
      .then(() => {
        message.success(`${card.label} 已保存`)
        load()
      })
      .catch(() => message.error('保存失败'))
      .finally(() => setSavingKey(null))
  }

  const handleTest = (card) => {
    if (card.key === 'common') return
    setTestingKey(card.key)
    const cat = card.category
    const all = groupValues(values)
    settingsApi.update({ [cat]: all[cat] || {} })
      .then(() => settingsApi.testAi({ provider: card.key }))
      .then((res) => {
        message.success(`${res?.message || '连通成功'}（${res?.model || card.key}）`)
        load()
      })
      .catch((err) => message.error(err?.error || err?.message || '测试失败'))
      .finally(() => setTestingKey(null))
  }

  const handleAdd = () => {
    form.validateFields().then(vals => {
      setAdding(true)
      settingsApi.createAiProvider({
        key: vals.key,
        label: vals.label,
        desc: vals.desc || '',
        color: vals.color || 'blue',
        default_base_url: vals.default_base_url || '',
        default_model: vals.default_model || '',
        model_hint: vals.model_hint || '',
      })
        .then(res => {
          message.success(res.message || '厂商已添加')
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

  const handleDelete = (card) => {
    settingsApi.deleteAiProvider(card.key)
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
  const current = cards.find(p => p.key === activeKey) || cards[0]
  const isCommon = current?.key === 'common'

  const visibleFields = (card) => {
    const items = settings[card.category] || []
    if (card.key === 'common') return items
    return items.filter(item => !['auth_type', 'username', 'password'].includes(item.key))
  }

  const statusTag = (card) => {
    if (card.key === 'common') return <Tag color="purple">共用</Tag>
    const ready = readiness[card.category]
    if (ready?.enabled && ready?.ready) return <Tag color="success">使用中</Tag>
    if (ready?.enabled) return <Tag color="warning">待配齐</Tag>
    if (ready?.message?.includes('已填')) return <Tag color="blue">已配置</Tag>
    return <Tag color="default">未启用</Tag>
  }

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16, flexWrap: 'wrap' }}>
        <div>
          <div className="page-title">{mod.label}</div>
          <div className="page-desc" style={{ marginBottom: 0 }}>{mod.desc}</div>
          <Alert
            style={{ marginTop: 12 }}
            type="info"
            showIcon
            message={moduleReady?.message || '选择一家大模型并启用'}
            description="填写 API Key 后启用即可。ChatGPT/GPT 请选「OpenAI / ChatGPT」，使用 platform.openai.com 的 sk- Key。"
          />
        </div>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => {
            form.resetFields()
            form.setFieldsValue({ color: 'blue' })
            setAddOpen(true)
          }}
        >
          添加模型
        </Button>
      </div>

      <div className="settings-plat-switch">
        {cards.map(p => {
          const selected = current?.key === p.key
          const ready = readiness[p.category]
          const on = !!(ready?.enabled && ready?.ready)
          return (
            <button
              key={p.key}
              type="button"
              className={`settings-plat-pill${selected ? ' active' : ''}`}
              onClick={() => setActiveKey(p.key)}
            >
              <span className={`dot ${on ? 'on' : 'off'}`} />
              {p.label}
              {p.recommended ? ' · 推荐' : ''}
            </button>
          )
        })}
      </div>

      {current && (
        <div className="settings-plat-meta">
          <span className="meta-text">{current.desc}</span>
          {statusTag(current)}
        </div>
      )}

      <div>
        <div style={{ minWidth: 0 }}>
          {current && (
            <Card
              title={
                <Space>
                  {current.label}
                  <Tag>大模型</Tag>
                  {current.recommended && <Tag color="green">推荐</Tag>}
                </Space>
              }
              extra={
                <Space>
                  {!isCommon && (
                    <Button
                      icon={<ExperimentOutlined />}
                      loading={testingKey === current.key}
                      onClick={() => handleTest(current)}
                    >
                      测试连通
                    </Button>
                  )}
                  {!isCommon && !current.builtin && (
                    <Popconfirm
                      title={`删除厂商「${current.label}」？`}
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
                    onClick={() => saveCard(current)}
                  >
                    保存
                  </Button>
                </Space>
              }
            >
              {!isCommon && current.key === 'volcano' && (
                <Alert
                  style={{ marginBottom: 16 }}
                  type="warning"
                  showIcon
                  message="火山引擎需填推理接入点"
                  description="API Key 用方舟 ARK_API_KEY；模型名称填控制台接入点 ID（ep-xxxxxxxx），不是模型展示名。"
                />
              )}
              {!isCommon && current.key === 'openai' && (
                <Alert
                  style={{ marginBottom: 16 }}
                  type="info"
                  showIcon
                  message="ChatGPT / GPT 官方接法"
                  description="到 https://platform.openai.com/api-keys 创建 sk- 开头的 API Key（需开通付费/有余额）。"
                />
              )}
              <Form layout="vertical">
                {visibleFields(current).map(item => (
                  <Form.Item key={item.key} label={item.label} extra={item.description}>
                    {renderSettingField(item, values, setValues)}
                  </Form.Item>
                ))}
                {!visibleFields(current).length && (
                  <Alert type="warning" message="该厂商尚未初始化配置项，请刷新页面或重启后端。" />
                )}
              </Form>
            </Card>
          )}
        </div>
      </div>

      <Modal
        title="添加大模型厂商"
        open={addOpen}
        onOk={handleAdd}
        confirmLoading={adding}
        onCancel={() => setAddOpen(false)}
        width={560}
        destroyOnClose
      >
        <Form form={form} layout="vertical" style={{ marginTop: 8 }}>
          <Form.Item
            name="key"
            label="标识"
            rules={[
              { required: true, message: '必填' },
              { pattern: /^[a-z][a-z0-9_]{1,31}$/, message: '小写字母开头，仅 a-z/0-9/_，2-32 位' },
            ]}
            extra="如 myproxy、local_llm，创建后不可改"
          >
            <Input placeholder="myproxy" />
          </Form.Item>
          <Form.Item name="label" label="显示名称" rules={[{ required: true }]}>
            <Input placeholder="我的中转" />
          </Form.Item>
          <Form.Item name="desc" label="简介">
            <Input placeholder="可选" />
          </Form.Item>
          <Form.Item name="default_base_url" label="默认 API Base URL" extra="OpenAI 兼容根地址">
            <Input placeholder="https://api.example.com/v1" />
          </Form.Item>
          <Form.Item name="default_model" label="默认模型名">
            <Input placeholder="gpt-4o-mini" />
          </Form.Item>
          <Form.Item name="color" label="标签颜色">
            <Select options={COLOR_OPTIONS} />
          </Form.Item>
        </Form>
      </Modal>
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

      <div className="settings-plat-switch">
        {platforms.map(p => {
          const ready = readiness[p.category]
          const selected = current?.key === p.key
          const on = isCommercial
            ? !!(ready?.ready && ready?.enabled)
            : !!ready?.ready
          return (
            <button
              key={p.key}
              type="button"
              className={`settings-plat-pill${selected ? ' active' : ''}`}
              onClick={() => setActiveKey(p.key)}
            >
              <span className={`dot ${on ? 'on' : 'off'}`} />
              {p.label}
            </button>
          )
        })}
      </div>

      {!platforms.length && (
        <Alert type="info" message="暂无平台，点击右上角添加" style={{ marginBottom: 14 }} />
      )}

      {current && (
        <div className="settings-plat-meta">
          <span className="meta-text">{current.desc}</span>
          {statusTag(readiness[current.category])}
        </div>
      )}

      <div>
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
                    title="保存"
                  >
                    保存
                  </Button>
                </Space>
              }
            >
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
