import { useState, useEffect, useRef } from 'react'
import {
  Table, Tag, Button, Input, Select, Space, Modal, message,
  Popconfirm, Tooltip, Row, Col, Card, Statistic, Form, Steps, Alert,
  Upload, Image as AntImage, Empty, Checkbox, Badge, InputNumber,
} from 'antd'
import {
  PlusOutlined, DeleteOutlined, SearchOutlined, ReloadOutlined,
  PlayCircleOutlined, SoundOutlined, FileTextOutlined, VideoCameraOutlined,
  CheckCircleOutlined, CloseCircleOutlined, ClockCircleOutlined,
  DownloadOutlined, UploadOutlined, PictureOutlined, FileOutlined,
  LoadingOutlined, MessageOutlined, ApartmentOutlined, ThunderboltOutlined,
} from '@ant-design/icons'
import { videosApi, scriptsApi, settingsApi, materialsApi } from '../../api'

const { TextArea } = Input

const statusIcons = {
  pending: <ClockCircleOutlined style={{ color: '#999' }} />,
  done: <CheckCircleOutlined style={{ color: '#52c41a' }} />,
  failed: <CloseCircleOutlined style={{ color: '#ff4d4f' }} />,
  processing: <LoadingOutlined style={{ color: '#1890ff' }} />,
}
const statusColors = { pending: 'default', done: 'success', failed: 'error', processing: 'processing' }
const statusLabels = { pending: '待处理', done: '完成', failed: '失败', processing: '执行中' }

const STYLE_COLORS = {
  default: 'blue', cyberpunk: 'cyan', punk: 'red', minimalist: 'default',
  vintage: 'orange', tech: 'geekblue', warm: 'gold', cinematic: 'purple',
  nature: 'green', business: 'blue',
}

export default function Videos() {
  const [data, setData] = useState({ list: [], total: 0 })
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [filters, setFilters] = useState({})
  const [createModal, setCreateModal] = useState(false)
  const [executing, setExecuting] = useState(null)
  const [scripts, setScripts] = useState([])
  const [ffmpegOk, setFfmpegOk] = useState(null)
  const [form] = Form.useForm()

  // Style and materials
  const [styles, setStyles] = useState([])
  const [materials, setMaterials] = useState([])
  const [materialModal, setMaterialModal] = useState(false)
  const [selectedMaterialIds, setSelectedMaterialIds] = useState([])
  const [uploading, setUploading] = useState(false)
  const [materialFilter, setMaterialFilter] = useState({ type: '', q: '' })
  // Per-task video defaults (from system settings)
  const [videoDefaults, setVideoDefaults] = useState({})
  // Voice options and narration presets from backend
  const [voiceOptions, setVoiceOptions] = useState([])
  const [narrationPresets, setNarrationPresets] = useState([])
  // Track polling for background tasks: { taskId: intervalId }
  const pollingRef = useRef({})
  const [pollingTasks, setPollingTasks] = useState(new Set())
  // Scene editor state
  const [sceneModal, setSceneModal] = useState(false)
  const [sceneTaskId, setSceneTaskId] = useState(null)
  const [scenes, setScenes] = useState([])
  const [sceneMaterials, setSceneMaterials] = useState([])
  const [sceneLoading, setSceneLoading] = useState(false)

  const loadData = (p = page, f = filters) => {
    setLoading(true)
    videosApi.list({ page: p, pageSize: 15, ...f })
      .then(res => { setData(res); setPage(p) })
      .finally(() => setLoading(false))
  }

  // Poll task status for background tasks
  const startPolling = (taskId) => {
    if (pollingRef.current[taskId]) return  // Already polling

    setPollingTasks(prev => new Set([...prev, taskId]))

    const poll = () => {
      videosApi.getStatus(taskId).then(res => {
        // Update the task in the local data without full reload
        setData(prev => ({
          ...prev,
          list: prev.list.map(item =>
            item.id === taskId
              ? { ...item, ...res }
              : item
          )
        }))

        if (res.is_running || res.video_status === 'processing' || res.export_status === 'processing') {
          // Keep polling
          pollingRef.current[taskId] = setTimeout(poll, 3000)
        } else {
          // Done - stop polling and reload full data
          stopPolling(taskId)
          loadData()
          if (res.export_status === 'done') {
            message.success(`视频任务 #${taskId} 制作完成！`)
          } else if (res.video_status === 'failed' || res.export_status === 'failed') {
            message.error(`视频任务 #${taskId} 失败: ${res.error_msg || '未知错误'}`)
          }
        }
      }).catch(() => {
        // On error, keep polling but slower
        pollingRef.current[taskId] = setTimeout(poll, 5000)
      })
    }

    pollingRef.current[taskId] = setTimeout(poll, 2000)
  }

  const stopPolling = (taskId) => {
    if (pollingRef.current[taskId]) {
      clearTimeout(pollingRef.current[taskId])
      delete pollingRef.current[taskId]
    }
    setPollingTasks(prev => {
      const next = new Set(prev)
      next.delete(taskId)
      return next
    })
  }

  // Cleanup all polling on unmount
  useEffect(() => {
    return () => {
      Object.values(pollingRef.current).forEach(clearTimeout)
    }
  }, [])

  useEffect(() => {
    loadData(1)
    videosApi.checkFfmpeg().then(res => setFfmpegOk(res.available)).catch(() => {})
    materialsApi.styles().then(res => setStyles(res.styles || [])).catch(() => {})
    // Load default video params from system settings
    settingsApi.get().then(res => {
      const v = (res.video || []).reduce((acc, s) => { acc[s.key] = s.value; return acc }, {})
      setVideoDefaults(v)
    }).catch(() => {})
    // Load voice options and narration presets
    videosApi.voiceOptions().then(res => {
      setVoiceOptions(res.voices || [])
      setNarrationPresets(res.narration_presets || [])
    }).catch(() => {})
  }, [])

  // Check for tasks that are in 'processing' state on page load (e.g. after refresh)
  // and resume polling for them
  useEffect(() => {
    data.list.forEach(item => {
      if (item.voice_status === 'processing' || item.video_status === 'processing' || item.export_status === 'processing') {
        if (!pollingTasks.has(item.id)) {
          startPolling(item.id)
        }
      }
    })
  }, [data.list])

  const loadScripts = () => {
    scriptsApi.list({ pageSize: 100 }).then(res => setScripts(res.list)).catch(() => {})
  }

  const loadMaterials = (f = materialFilter) => {
    materialsApi.list({ ...f, pageSize: 100 }).then(res => setMaterials(res.list || [])).catch(() => {})
  }

  const handleCreate = () => {
    form.validateFields().then(values => {
      const payload = {
        ...values,
        material_ids: selectedMaterialIds.join(','),
      }
      videosApi.create(payload).then(() => {
        message.success('视频任务已创建')
        setCreateModal(false)
        form.resetFields()
        setSelectedMaterialIds([])
        loadData(1)
      })
    })
  }

  const handleExecute = (id, step, stepName) => {
    setExecuting(`${id}-${step}`)
    videosApi.execute(id, step).then(res => {
      // For compose/all steps, the API returns immediately with 'processing' status
      // Start polling for completion
      if (step === 'compose' || step === 'all') {
        if (res.status === 'processing' || res.task_id) {
          message.info(res.message || `${stepName}已开始后台执行，请等待完成`)
          setExecuting(null)
          startPolling(id)
          return
        }
      }
      message.success(res.message || `${stepName}完成`)
      loadData()
    }).catch(err => {
      message.error(err?.error || `${stepName}失败`)
    }).finally(() => {
      setExecuting(null)
    })
  }

  const handleUpload = (file) => {
    const formData = new FormData()
    formData.append('file', file)
    const fileName = file.name.replace(/\.[^.]+$/, '')
    formData.append('name', fileName)
    setUploading(true)
    materialsApi.upload(formData).then(() => {
      message.success('素材上传成功')
      loadMaterials()
    }).catch(err => {
      message.error(err?.error || '上传失败')
    }).finally(() => setUploading(false))
    return false  // prevent auto upload
  }

  const handleDeleteMaterial = (id) => {
    materialsApi.delete(id).then(() => {
      message.success('已删除')
      loadMaterials()
      setSelectedMaterialIds(prev => prev.filter(x => x !== id))
    })
  }

  // === Scene Editor ===
  const openSceneEditor = (taskId) => {
    setSceneTaskId(taskId)
    setSceneModal(true)
    setSceneLoading(true)
    setScenes([])
    setSceneMaterials([])
    videosApi.getScenes(taskId).then(res => {
      setScenes(res.scenes || [])
      setSceneMaterials(res.materials_info || [])
    }).catch(() => {
      message.error('加载场景失败')
    }).finally(() => setSceneLoading(false))
  }

  const handleGenerateScenes = () => {
    if (!sceneTaskId) return
    setSceneLoading(true)
    videosApi.generateScenes(sceneTaskId, {}).then(res => {
      setScenes(res.scenes || [])
      setSceneMaterials(res.materials_info || [])
      message.success(res.message || '场景生成完成')
    }).catch(err => {
      message.error(err?.error || '场景生成失败')
    }).finally(() => setSceneLoading(false))
  }

  const handleSaveScenes = () => {
    if (!sceneTaskId || scenes.length === 0) return
    setSceneLoading(true)
    videosApi.updateScenes(sceneTaskId, scenes).then(res => {
      message.success('场景已保存，生成视频时将按场景切换素材')
      setSceneModal(false)
    }).catch(err => {
      message.error(err?.error || '保存失败')
    }).finally(() => setSceneLoading(false))
  }

  const handleSceneMaterialChange = (sceneIndex, materialId) => {
    setScenes(prev => prev.map(s => {
      if (s.index === sceneIndex) {
        if (materialId === null || materialId === undefined) {
          return { ...s, material_id: null, material_index: -1, material_name: '', material_type: '' }
        }
        const mat = sceneMaterials.find(m => m.id === materialId)
        if (mat) {
          return {
            ...s,
            material_id: mat.id,
            material_index: mat.index,
            material_name: mat.name,
            material_type: mat.type,
          }
        }
      }
      return s
    }))
  }

  const columns = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    { title: '标题', dataIndex: 'title', ellipsis: true },
    {
      title: '风格', dataIndex: 'video_style', width: 90,
      render: v => {
        const style = styles.find(s => s.key === v)
        return style ? <Tag color={STYLE_COLORS[v] || 'blue'}>{style.name}</Tag> : <Tag>默认</Tag>
      }
    },
    {
      title: '分辨率', dataIndex: 'resolution', width: 100,
      render: v => v ? <Tag>{v}</Tag> : '-'
    },
    {
      title: '引擎', dataIndex: 'video_engine', width: 80,
      render: v => <Tag color={v === 'moviepy' ? 'geekblue' : 'default'}>{v === 'moviepy' ? 'MoviePy' : 'FFmpeg'}</Tag>
    },
    { title: '关联文案', dataIndex: 'script_title', width: 120, ellipsis: true,
      render: v => v || '-' },
    {
      title: '配音', dataIndex: 'voice_status', width: 70,
      render: v => <Tag color={statusColors[v]} icon={statusIcons[v]}>{statusLabels[v] || v}</Tag>
    },
    {
      title: '字幕', dataIndex: 'subtitle_status', width: 70,
      render: v => <Tag color={statusColors[v]} icon={statusIcons[v]}>{statusLabels[v] || v}</Tag>
    },
    {
      title: '合成', dataIndex: 'video_status', width: 70,
      render: v => <Tag color={statusColors[v]} icon={statusIcons[v]}>{statusLabels[v] || v}</Tag>
    },
    {
      title: '导出', dataIndex: 'export_status', width: 70,
      render: v => <Tag color={statusColors[v]} icon={statusIcons[v]}>{statusLabels[v] || v}</Tag>
    },
    { title: '时长', dataIndex: 'duration', width: 70,
      render: v => v ? `${v.toFixed(1)}s` : '-' },
    { title: '创建时间', dataIndex: 'created_at', width: 160 },
    {
      title: '操作', key: 'action', width: 330, fixed: 'right',
      render: (_, r) => {
        const isProcessing = r.voice_status === 'processing' || r.video_status === 'processing' || r.export_status === 'processing'
        return (
        <Space size="small" wrap>
          <Tooltip title="配音">
            <Button size="small" icon={<SoundOutlined />}
              loading={executing === `${r.id}-voice`}
              disabled={r.voice_status === 'done' || isProcessing}
              onClick={() => handleExecute(r.id, 'voice', '配音')} />
          </Tooltip>
          <Tooltip title="字幕">
            <Button size="small" icon={<FileTextOutlined />}
              loading={executing === `${r.id}-subtitle`}
              disabled={r.subtitle_status === 'done' || isProcessing}
              onClick={() => handleExecute(r.id, 'subtitle', '字幕')} />
          </Tooltip>
          <Tooltip title="合成视频">
            <Button size="small" icon={<VideoCameraOutlined />}
              loading={pollingTasks.has(r.id) && executing === `${r.id}-compose`}
              disabled={r.video_status === 'done' || r.voice_status !== 'done' || r.subtitle_status !== 'done' || isProcessing}
              onClick={() => handleExecute(r.id, 'compose', '合成')} />
          </Tooltip>
          <Tooltip title={r.scenes_json ? '编辑场景编排' : '场景编排（AI分割+素材匹配）'}>
            <Button size="small" icon={<ApartmentOutlined />}
              type={r.scenes_json ? 'primary' : 'default'}
              ghost={!!r.scenes_json}
              disabled={isProcessing}
              onClick={() => openSceneEditor(r.id)} />
          </Tooltip>
          <Tooltip title="一键全流程">
            <Button size="small" type="primary" icon={
              pollingTasks.has(r.id) ? <LoadingOutlined /> : <PlayCircleOutlined />
            }
              disabled={r.export_status === 'done' || isProcessing}
              onClick={() => handleExecute(r.id, 'all', '全流程')} />
          </Tooltip>
          {r.output_path && (
            <Tooltip title="下载视频">
              <Button size="small" icon={<DownloadOutlined />}
                href={`/api/videos/${r.id}/download`} />
            </Tooltip>
          )}
          <Popconfirm title="确认删除？" onConfirm={() => {
            stopPolling(r.id)
            videosApi.delete(r.id).then(() => { message.success('已删除'); loadData() })
          }}>
            <Button size="small" danger icon={<DeleteOutlined />} disabled={isProcessing} />
          </Popconfirm>
        </Space>
        )
      }
    },
  ]

  return (
    <div>
      <div className="page-title">视频中心</div>

      {ffmpegOk === false && (
        <Alert type="info" showIcon style={{ marginBottom: 16 }}
          message="系统未检测到独立安装的 FFmpeg"
          description="MoviePy 引擎自带 FFmpeg，无需额外安装即可生成视频。独立 FFmpeg 仅用于 ffprobe（获取音频时长）和 FFmpeg 回退引擎。如需使用 FFmpeg 引擎，请在「系统设置」中配置 FFmpeg 路径。" />
      )}

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card size="small"><Statistic title="视频任务" value={data.total} prefix={<VideoCameraOutlined />} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="已完成" value={data.list.filter(d => d.export_status === 'done').length} valueStyle={{ color: '#52c41a' }} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="进行中" value={data.list.filter(d => d.export_status === 'pending' && d.voice_status !== 'pending').length} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="待处理" value={data.list.filter(d => d.voice_status === 'pending').length} /></Card></Col>
      </Row>

      <div className="table-toolbar">
        <div className="table-toolbar-left">
          <Select placeholder="状态" allowClear style={{ width: 120 }}
            value={filters.export_status}
            onChange={v => setFilters({ ...filters, export_status: v })}
            options={[
              { label: '待处理', value: 'pending' },
              { label: '已完成', value: 'done' },
              { label: '失败', value: 'failed' },
            ]} />
          <Input placeholder="搜索标题" allowClear style={{ width: 200 }}
            value={filters.q}
            onChange={e => setFilters({ ...filters, q: e.target.value })}
            onPressEnter={() => loadData(1, filters)} />
          <Button type="primary" icon={<SearchOutlined />} onClick={() => loadData(1, filters)}>搜索</Button>
          <Button icon={<ReloadOutlined />} onClick={() => { setFilters({}); loadData(1, {}) }}>重置</Button>
        </div>
        <Space>
          <Button icon={<PictureOutlined />} onClick={() => {
            setMaterialModal(true); loadMaterials()
          }}>素材库</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => {
            loadScripts(); form.resetFields(); setSelectedMaterialIds([]); setCreateModal(true)
          }}>创建视频任务</Button>
        </Space>
      </div>

      <Table columns={columns} dataSource={data.list} rowKey="id" loading={loading}
        scroll={{ x: 1400 }}
        pagination={{
          current: page, total: data.total, pageSize: 15,
          onChange: (p) => loadData(p),
          showTotal: (t) => `共 ${t} 条`,
        }}
        size="middle" />

      {/* Create Modal */}
      <Modal title="创建视频任务" open={createModal} onOk={handleCreate}
        onCancel={() => { setCreateModal(false); setSelectedMaterialIds([]) }} width={720}>
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}
          initialValues={{
            video_style: 'default',
            resolution: videoDefaults.default_resolution || '1080x1920',
            fps: videoDefaults.default_fps || '30',
            render_quality: videoDefaults.default_render_quality || 'high',
            video_engine: videoDefaults.default_video_engine || 'moviepy',
            fade_transition: videoDefaults.default_fade_transition || 'true',
            title_overlay: videoDefaults.default_title_overlay || 'true',
          }}>
          <Form.Item name="script_id" label="选择文案" rules={[{ required: true }]}>
            <Select showSearch optionFilterProp="label" placeholder="选择已有文案"
              options={scripts.map(s => ({ label: s.title, value: s.id }))} />
          </Form.Item>
          <Form.Item name="title" label="视频标题" extra="不填则使用文案标题">
            <Input placeholder="视频标题" />
          </Form.Item>
          <Form.Item name="video_style" label="视频风格">
            <Select options={styles.map(s => ({ label: s.name, value: s.key }))} />
          </Form.Item>
          <Form.Item label="选择素材" extra="从素材库选择图片或视频作为背景，不选则使用纯色背景">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Badge count={selectedMaterialIds.length}>
                <Button icon={<PictureOutlined />} onClick={() => {
                  setMaterialModal(true); loadMaterials()
                }}>从素材库选择</Button>
              </Badge>
              {selectedMaterialIds.length > 0 && (
                <span style={{ color: '#999' }}>
                  已选 {selectedMaterialIds.length} 个素材
                </span>
              )}
            </div>
          </Form.Item>

          {/* Narration Settings */}
          <div style={{ borderTop: '1px solid #f0f0f0', paddingTop: 16, marginTop: 8 }}>
            <div style={{ marginBottom: 12, fontWeight: 500, color: '#666' }}>
              <MessageOutlined style={{ marginRight: 6 }} />
              旁白设置（让视频更像真人拍摄）
            </div>

            {/* Narration preset quick buttons */}
            <div style={{ marginBottom: 12 }}>
              <span style={{ fontSize: 12, color: '#999', marginRight: 8 }}>快捷风格:</span>
              {narrationPresets.map(p => (
                <Tag key={p.value} style={{ cursor: 'pointer', marginBottom: 4 }}
                  color="blue"
                  onClick={() => form.setFieldValue('narration_prompt', p.label)}>
                  {p.label.length > 12 ? p.label.substring(0, 12) + '...' : p.label}
                </Tag>
              ))}
            </div>

            <Form.Item name="narration_prompt" label="旁白提示词"
              extra="填写后AI会将文案改写为更自然的口播旁白，不填则直接朗读原文">
              <TextArea rows={3} placeholder="例如：用讲故事的口吻，像在跟朋友聊天，有悬念和情感起伏。留空则直接朗读原文文案。" />
            </Form.Item>

            <Row gutter={16}>
              <Col span={14}>
                <Form.Item name="voice" label="语音角色"
                  extra="不选则使用系统设置中的默认语音">
                  <Select allowClear placeholder="使用系统默认语音"
                    options={voiceOptions.map(v => ({ label: v.label, value: v.value }))} />
                </Form.Item>
              </Col>
              <Col span={10}>
                <Form.Item name="voice_rate" label="语速调整"
                  extra="正数加快，负数减慢">
                  <Select allowClear placeholder="默认语速"
                    options={[
                      { label: '很慢 (-15%)', value: '-15%' },
                      { label: '稍慢 (-8%)', value: '-8%' },
                      { label: '默认 (+0%)', value: '+0%' },
                      { label: '稍快 (+8%)', value: '+8%' },
                      { label: '很快 (+15%)', value: '+15%' },
                    ]} />
                </Form.Item>
              </Col>
            </Row>
          </div>

          <div style={{ borderTop: '1px solid #f0f0f0', paddingTop: 16, marginTop: 8 }}>
            <div style={{ marginBottom: 12, fontWeight: 500, color: '#666' }}>视频参数（每个任务可不同）</div>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="resolution" label="分辨率">
                  <Select options={[
                    { label: '竖屏 1080×1920', value: '1080x1920' },
                    { label: '横屏 1920×1080', value: '1920x1080' },
                    { label: '竖屏 720×1280', value: '720x1280' },
                  ]} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="fps" label="帧率">
                  <Select options={[
                    { label: '30 fps', value: '30' },
                    { label: '24 fps', value: '24' },
                    { label: '60 fps', value: '60' },
                  ]} />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="video_engine" label="合成引擎"
                  extra={form.getFieldValue('video_engine') === 'moviepy' ? '高质量，渲染较慢' : '快速，效果一般'}>
                  <Select options={[
                    { label: 'MoviePy（高质量）', value: 'moviepy' },
                    { label: 'FFmpeg（快速）', value: 'ffmpeg' },
                  ]} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="render_quality" label="渲染质量"
                  extra={form.getFieldValue('render_quality') === 'preview' ? '最快，低分辨率预览' :
                         form.getFieldValue('render_quality') === 'medium' ? '中等，720p' : '最高质量，最慢'}>
                  <Select options={[
                    { label: '高质量', value: 'high' },
                    { label: '中等', value: 'medium' },
                    { label: '预览（最快）', value: 'preview' },
                  ]} />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="fade_transition" label="淡入淡出">
                  <Select options={[
                    { label: '开启', value: 'true' },
                    { label: '关闭', value: 'false' },
                  ]} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="title_overlay" label="显示标题">
                  <Select options={[
                    { label: '显示', value: 'true' },
                    { label: '隐藏', value: 'false' },
                  ]} />
                </Form.Item>
              </Col>
            </Row>
          </div>
        </Form>
        <Alert type="info" message="视频制作流程：配音 → 字幕 → 合成。可逐步执行或一键全流程。填写旁白提示词可让AI改写文案为自然口播，语音更人性化。" />
      </Modal>

      {/* Material Library Modal */}
      <Modal title="素材库" open={materialModal}
        onCancel={() => setMaterialModal(false)}
        footer={null} width={800}>
        <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Space>
            <Select placeholder="类型" allowClear style={{ width: 100 }}
              value={materialFilter.type}
              onChange={v => { setMaterialFilter({ ...materialFilter, type: v }); loadMaterials({ ...materialFilter, type: v }) }}
              options={[{ label: '图片', value: 'image' }, { label: '视频', value: 'video' }]} />
            <Input placeholder="搜索名称" allowClear style={{ width: 180 }}
              value={materialFilter.q}
              onChange={e => setMaterialFilter({ ...materialFilter, q: e.target.value })}
              onPressEnter={() => loadMaterials()} />
            <Button icon={<ReloadOutlined />} onClick={() => {
              setMaterialFilter({ type: '', q: '' }); loadMaterials({ type: '', q: '' })
            }}>刷新</Button>
          </Space>
          <Upload beforeUpload={handleUpload} showUploadList={false}
            accept="image/*,video/*">
            <Button type="primary" icon={<UploadOutlined />} loading={uploading}>上传素材</Button>
          </Upload>
        </div>

        {materials.length === 0 ? (
          <Empty description="暂无素材，点击右上角上传" />
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, maxHeight: 500, overflow: 'auto' }}>
            {materials.map(m => {
              const selected = selectedMaterialIds.includes(m.id)
              return (
                <div key={m.id}
                  style={{
                    position: 'relative', border: selected ? '2px solid #1890ff' : '1px solid #d9d9d9',
                    borderRadius: 8, cursor: 'pointer', overflow: 'hidden',
                  }}
                  onClick={() => {
                    setSelectedMaterialIds(prev =>
                      prev.includes(m.id) ? prev.filter(x => x !== m.id) : [...prev, m.id]
                    )
                  }}>
                  <div style={{ width: '100%', height: 120, background: '#f5f5f5', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    {m.type === 'image' ? (
                      <img src={`/api/materials/${m.id}/preview`} alt={m.name}
                        style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    ) : (
                      <div style={{ textAlign: 'center' }}>
                        <FileOutlined style={{ fontSize: 40, color: '#999' }} />
                        <div style={{ fontSize: 12, color: '#999', marginTop: 4 }}>视频文件</div>
                      </div>
                    )}
                  </div>
                  <div style={{ padding: '4px 8px', fontSize: 12 }}>
                    <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {m.name}
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Tag color={m.type === 'image' ? 'blue' : 'purple'}>{m.type === 'image' ? '图片' : '视频'}</Tag>
                      <Popconfirm title="确认删除？" onConfirm={(e) => {
                        e.stopPropagation(); handleDeleteMaterial(m.id)
                      }}>
                        <Button size="small" danger icon={<DeleteOutlined />} type="text" />
                      </Popconfirm>
                    </div>
                  </div>
                  {selected && (
                    <div style={{
                      position: 'absolute', top: 4, right: 4,
                      background: '#1890ff', borderRadius: '50%', width: 20, height: 20,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                    }}>
                      <CheckCircleOutlined style={{ color: 'white', fontSize: 14 }} />
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}

        {selectedMaterialIds.length > 0 && (
          <div style={{ marginTop: 16, textAlign: 'right' }}>
            <span style={{ marginRight: 12, color: '#666' }}>
              已选 {selectedMaterialIds.length} 个素材
            </span>
            <Button onClick={() => setSelectedMaterialIds([])}>清空选择</Button>
            <Button type="primary" style={{ marginLeft: 8 }}
              onClick={() => setMaterialModal(false)}>完成</Button>
          </div>
        )}
      </Modal>

      {/* Scene Editor Modal */}
      <Modal title="场景编排 — 素材与旁白智能匹配" open={sceneModal}
        onCancel={() => setSceneModal(false)}
        width={820}
        footer={null}>
        {sceneLoading ? (
          <div style={{ textAlign: 'center', padding: 60 }}>
            <LoadingOutlined style={{ fontSize: 32 }} />
            <div style={{ marginTop: 16, color: '#999' }}>AI 正在分析文案并匹配素材...</div>
          </div>
        ) : scenes.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <ApartmentOutlined style={{ fontSize: 48, color: '#d9d9d9' }} />
            <div style={{ marginTop: 16, color: '#666' }}>
              AI 会将旁白拆分为多个场景段落，并为每个场景匹配最合适的素材
            </div>
            <div style={{ marginTop: 8, color: '#999', fontSize: 12 }}>
              需要先选择素材并创建任务，才能生成场景
            </div>
            <Button type="primary" icon={<ThunderboltOutlined />} style={{ marginTop: 20 }}
              onClick={handleGenerateScenes}>
              生成场景
            </Button>
          </div>
        ) : (
          <>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <Space>
                <span style={{ fontWeight: 500 }}>
                  共 {scenes.length} 个场景
                </span>
                {sceneMaterials.length > 0 && (
                  <span style={{ color: '#999', fontSize: 12 }}>
                    可用素材 {sceneMaterials.length} 个
                  </span>
                )}
              </Space>
              <Space>
                <Button icon={<ThunderboltOutlined />} onClick={handleGenerateScenes}>
                  重新生成
                </Button>
                <Button type="primary" onClick={handleSaveScenes}>
                  保存场景
                </Button>
              </Space>
            </div>

            <div style={{ maxHeight: 480, overflow: 'auto' }}>
              {scenes.map((scene, i) => (
                <div key={i} style={{
                  display: 'flex', gap: 12, padding: 12, marginBottom: 8,
                  border: '1px solid #f0f0f0', borderRadius: 8,
                  background: '#fafafa',
                }}>
                  {/* Scene number */}
                  <div style={{
                    minWidth: 28, height: 28, borderRadius: '50%',
                    background: '#1890ff', color: 'white',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 13, fontWeight: 600, marginTop: 2,
                  }}>
                    {i + 1}
                  </div>

                  {/* Scene content */}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{
                      fontSize: 13, lineHeight: 1.6, color: '#333',
                      maxHeight: 60, overflow: 'hidden',
                    }}>
                      {scene.text}
                    </div>
                    {scene.keywords && scene.keywords.length > 0 && (
                      <div style={{ marginTop: 6 }}>
                        {scene.keywords.map((kw, j) => (
                          <Tag key={j} color="blue" style={{ marginBottom: 2 }}>{kw}</Tag>
                        ))}
                      </div>
                    )}
                    {scene.visual_desc && (
                      <div style={{ marginTop: 4, fontSize: 11, color: '#999' }}>
                        画面建议: {scene.visual_desc}
                      </div>
                    )}
                  </div>

                  {/* Material selector */}
                  <div style={{ minWidth: 180 }}>
                    <Select
                      size="small"
                      style={{ width: '100%' }}
                      placeholder="选择素材"
                      value={scene.material_id || undefined}
                      onChange={(val) => handleSceneMaterialChange(scene.index, val)}
                      allowClear
                      options={sceneMaterials.map(m => ({
                        label: `${m.type === 'video' ? '🎬' : '🖼'} ${m.name}`,
                        value: m.id,
                      }))}
                    />
                    {scene.material_name && (
                      <div style={{ marginTop: 4, fontSize: 11, color: '#999' }}>
                        {scene.material_type === 'video' ? '视频' : '图片'}: {scene.material_name}
                      </div>
                    )}
                    {scene.start != null && scene.end != null && (
                      <div style={{ fontSize: 11, color: '#bbb' }}>
                        {scene.start.toFixed(1)}s - {scene.end.toFixed(1)}s
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>

            <Alert type="info" style={{ marginTop: 12 }}
              message="保存后，生成视频时每个场景会显示匹配的素材，场景间自动淡入过渡。时长由旁白决定，不再固定。"
            />
          </>
        )}
      </Modal>
    </div>
  )
}
