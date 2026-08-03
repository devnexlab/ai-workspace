import { useState, useEffect } from 'react'
import { Row, Col, Card, Statistic, Table, Tag, List, Avatar, Spin, message, Button, Progress, Empty } from 'antd'
import {
  FireOutlined, FileTextOutlined, VideoCameraOutlined, TeamOutlined,
  RocketOutlined, ClockCircleOutlined, ArrowUpOutlined, AlertOutlined,
  BulbOutlined, StockOutlined, RobotOutlined, ApartmentOutlined, BellOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { dashboardApi } from '../../api'

const intentionColors = { high: 'red', medium: 'orange', low: 'default' }
const intentionLabels = { high: '高意向', medium: '中意向', low: '低意向' }

export default function Dashboard() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    dashboardApi.get().then(d => { setData(d); setLoading(false) })
      .catch(() => { message.error('加载仪表盘失败'); setLoading(false) })
  }, [])

  if (loading) return <div style={{ textAlign: 'center', padding: 80 }}><Spin size="large" /></div>
  if (!data) return <Empty description="暂无数据" />

  const { stats, recentTopics, recentScripts, pendingVideos, pendingPublish, recentCustomers, followCustomers, platformDist, recentKnowledge, upcomingReminders } = data

  const statCards = [
    { title: '热点总数', value: stats.hotTopics, sub: `今日新增 ${stats.hotTopicsToday}`, icon: <FireOutlined />, color: '#ff4d4f' },
    { title: '文案数量', value: stats.scripts, sub: `草稿 ${stats.scriptsDraft}`, icon: <FileTextOutlined />, color: '#1890ff' },
    { title: '视频任务', value: stats.videosPending + stats.videosDone, sub: `已完成 ${stats.videosDone}`, icon: <VideoCameraOutlined />, color: '#722ed1' },
    { title: '客户总数', value: stats.customers, sub: `今日新增 ${stats.customersNew} | 高意向 ${stats.customersHigh}`, icon: <TeamOutlined />, color: '#52c41a' },
    { title: '待发布', value: stats.publishPending, sub: `已发布 ${stats.publishDone}`, icon: <RocketOutlined />, color: '#faad14' },
  ]

  // V1.2 stat cards
  const v12Cards = [
    { title: '知识条目', value: stats.knowledgeItems, sub: `今日新增 ${stats.knowledgeToday}`, icon: <BulbOutlined />, color: '#13c2c2', path: '/knowledge' },
    { title: '自选股票', value: stats.stockCount, sub: `持仓 ${stats.stockHolding}`, icon: <StockOutlined />, color: '#eb2f96', path: '/stocks' },
    { title: 'AI Agents', value: stats.agents, sub: `活跃 ${stats.agentsActive}`, icon: <RobotOutlined />, color: '#722ed1', path: '/agents' },
    { title: 'AI助手', value: stats.agents, sub: '客户 / 运营 / 发布', icon: <ApartmentOutlined />, color: '#fa8c16', path: '/workflows' },
    { title: '待处理提醒', value: stats.pendingReminders, sub: '客户跟进提醒', icon: <BellOutlined />, color: '#f5222d', path: '/customers' },
  ]

  const scoreColor = (s) => s >= 8 ? 'red' : s >= 7 ? 'orange' : 'green'

  return (
    <div>
      <div className="page-title">Dashboard</div>

      {/* 统计卡片 */}
      <Row gutter={[16, 16]}>
        {statCards.map((s, i) => (
          <Col xs={12} sm={8} md={6} lg={5} key={i}>
            <Card className="stat-card" size="small">
              <Statistic
                title={<span style={{ fontSize: 13 }}>{s.title}</span>}
                value={s.value}
                prefix={<span style={{ color: s.color }}>{s.icon}</span>}
                valueStyle={{ fontSize: 28, fontWeight: 700 }}
              />
              <div style={{ fontSize: 12, color: '#999', marginTop: 4 }}>{s.sub}</div>
            </Card>
          </Col>
        ))}
      </Row>

      {/* V1.2 新模块统计 */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        {v12Cards.map((s, i) => (
          <Col xs={12} sm={8} md={6} lg={5} key={i}>
            <Card className="stat-card" size="small" hoverable onClick={() => navigate(s.path)}>
              <Statistic
                title={<span style={{ fontSize: 13 }}>{s.title}</span>}
                value={s.value}
                prefix={<span style={{ color: s.color }}>{s.icon}</span>}
                valueStyle={{ fontSize: 28, fontWeight: 700 }}
              />
              <div style={{ fontSize: 12, color: '#999', marginTop: 4 }}>{s.sub}</div>
            </Card>
          </Col>
        ))}
      </Row>

      {/* 平台分布 */}
      {platformDist?.length > 0 && (
        <Card size="small" style={{ marginTop: 16 }}>
          <div className="section-title"><FireOutlined /> 热点平台分布</div>
          <Row gutter={16}>
            {platformDist.map(p => (
              <Col key={p.platform} span={6}>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: 20, fontWeight: 700, color: '#5b6eff' }}>{p.count}</div>
                  <div style={{ fontSize: 13, color: '#999' }}>{p.platform}</div>
                </div>
              </Col>
            ))}
          </Row>
        </Card>
      )}

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        {/* 今日热点 */}
        <Col xs={24} lg={12}>
          <Card
            size="small"
            title={<span><FireOutlined /> 最新热点</span>}
            extra={<Button type="link" size="small" onClick={() => navigate('/hot-topics')}>查看全部</Button>}
          >
            <Table
              size="small"
              dataSource={recentTopics}
              rowKey="id"
              pagination={false}
              columns={[
                { title: '标题', dataIndex: 'title', ellipsis: true, width: '50%' },
                { title: '平台', dataIndex: 'platform', width: 80 },
                { title: '点赞', dataIndex: 'likes', width: 80, render: v => v?.toLocaleString() },
                { title: 'AI评分', dataIndex: 'ai_score', width: 80, render: v => <Tag color={scoreColor(v)}>{v}</Tag> },
              ]}
            />
          </Card>
        </Col>

        {/* 推荐文案 */}
        <Col xs={24} lg={12}>
          <Card
            size="small"
            title={<span><FileTextOutlined /> 最新文案</span>}
            extra={<Button type="link" size="small" onClick={() => navigate('/scripts')}>查看全部</Button>}
          >
            <Table
              size="small"
              dataSource={recentScripts}
              rowKey="id"
              pagination={false}
              columns={[
                { title: '标题', dataIndex: 'title', ellipsis: true, width: '55%' },
                { title: '版本', dataIndex: 'version', width: 60, render: v => `v${v}` },
                { title: '状态', dataIndex: 'status', width: 80, render: v => {
                  const m = { draft: { c: 'default', t: '草稿' }, approved: { c: 'blue', t: '已通过' }, used: { c: 'green', t: '已使用' } }
                  const conf = m[v] || { c: 'default', t: v }
                  return <Tag color={conf.c}>{conf.t}</Tag>
                }},
              ]}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        {/* 待生成视频 */}
        <Col xs={24} lg={12}>
          <Card size="small" title={<span><VideoCameraOutlined /> 待生成视频</span>}
            extra={<Button type="link" size="small" onClick={() => navigate('/videos')}>查看全部</Button>}
          >
            {pendingVideos?.length ? (
              <List
                size="small"
                dataSource={pendingVideos}
                renderItem={v => (
                  <List.Item>
                    <List.Item.Meta
                      title={v.title || `视频任务 #${v.id}`}
                      description={
                        <span>
                          <Tag color={v.voice_status === 'done' ? 'green' : 'default'}>配音</Tag>
                          <Tag color={v.subtitle_status === 'done' ? 'green' : 'default'}>字幕</Tag>
                          <Tag color={v.video_status === 'done' ? 'green' : 'default'}>剪辑</Tag>
                          <Tag color={v.export_status === 'done' ? 'green' : 'default'}>导出</Tag>
                        </span>
                      }
                    />
                  </List.Item>
                )}
              />
            ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无待处理视频" />}
          </Card>
        </Col>

        {/* 待发布 */}
        <Col xs={24} lg={12}>
          <Card size="small" title={<span><RocketOutlined /> 待发布视频</span>}
            extra={<Button type="link" size="small" onClick={() => navigate('/publish')}>查看全部</Button>}
          >
            {pendingPublish?.length ? (
              <Table
                size="small"
                dataSource={pendingPublish}
                rowKey="id"
                pagination={false}
                columns={[
                  { title: '视频', dataIndex: 'video_title', ellipsis: true, width: '50%' },
                  { title: '平台', dataIndex: 'platform', width: 80 },
                  { title: '状态', dataIndex: 'status', width: 80, render: () => <Tag color="orange">待发布</Tag> },
                ]}
              />
            ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无待发布任务" />}
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        {/* 新增客户 */}
        <Col xs={24} lg={12}>
          <Card size="small" title={<span><TeamOutlined /> 新增客户</span>}
            extra={<Button type="link" size="small" onClick={() => navigate('/customers')}>查看全部</Button>}
          >
            <Table
              size="small"
              dataSource={recentCustomers}
              rowKey="id"
              pagination={false}
              columns={[
                { title: '昵称', dataIndex: 'nickname', width: 100 },
                { title: '来源', dataIndex: 'source_video', ellipsis: true, width: '40%' },
                { title: '意向', dataIndex: 'intention', width: 80, render: v => <Tag color={intentionColors[v]}>{intentionLabels[v]}</Tag> },
              ]}
            />
          </Card>
        </Col>

        {/* 待跟进客户 */}
        <Col xs={24} lg={12}>
          <Card size="small" title={<span><AlertOutlined /> 待跟进客户</span>}
            extra={<Button type="link" size="small" onClick={() => navigate('/customers')}>查看全部</Button>}
          >
            <Table
              size="small"
              dataSource={followCustomers}
              rowKey="id"
              pagination={false}
              columns={[
                { title: '昵称', dataIndex: 'nickname', width: 100 },
                { title: '最后跟进', dataIndex: 'last_follow_time', ellipsis: true, width: '45%', render: v => v || '未跟进' },
                { title: '意向', dataIndex: 'intention', width: 80, render: v => <Tag color={intentionColors[v]}>{intentionLabels[v]}</Tag> },
              ]}
            />
          </Card>
        </Col>
      </Row>

      {/* V1.2: 知识库 + 提醒 */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={12}>
          <Card size="small" title={<span><BulbOutlined /> 最新知识</span>}
            extra={<Button type="link" size="small" onClick={() => navigate('/knowledge')}>查看全部</Button>}
          >
            {recentKnowledge?.length ? (
              <Table
                size="small"
                dataSource={recentKnowledge}
                rowKey="id"
                pagination={false}
                columns={[
                  { title: '标题', dataIndex: 'title', ellipsis: true, width: '50%' },
                  { title: '分类', dataIndex: 'category', width: 100, render: v => v ? <Tag color="cyan">{v}</Tag> : '-' },
                  { title: '来源', dataIndex: 'source_type', width: 90, render: v => <Tag>{v}</Tag> },
                ]}
              />
            ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无知识条目" />}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card size="small" title={<span><BellOutlined /> 即将到期提醒</span>}
            extra={<Button type="link" size="small" onClick={() => navigate('/customers')}>查看全部</Button>}
          >
            {upcomingReminders?.length ? (
              <Table
                size="small"
                dataSource={upcomingReminders}
                rowKey="id"
                pagination={false}
                columns={[
                  { title: '提醒', dataIndex: 'title', ellipsis: true, width: '45%' },
                  { title: '类型', dataIndex: 'type', width: 80, render: v => {
                    const m = { birthday: {c:'pink',t:'生日'}, policy_expiry: {c:'red',t:'保单到期'}, silent: {c:'orange',t:'沉默'}, high_intent: {c:'volcano',t:'高意向'}, follow_up: {c:'blue',t:'跟进'}, general: {c:'default',t:'一般'} }
                    const conf = m[v] || {c:'default', t:v}
                    return <Tag color={conf.c}>{conf.t}</Tag>
                  }},
                  { title: '客户', dataIndex: 'customer_name', width: 80 },
                  { title: '日期', dataIndex: 'remind_date', width: 100 },
                ]}
              />
            ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无提醒" />}
          </Card>
        </Col>
      </Row>
    </div>
  )
}
