# AI 视频号自动运营系统

基于 PRD V1.1 实现的全栈运营管理系统。

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React 18 + Ant Design 5 + Vite |
| 后端 | Python + Flask |
| 数据库 | SQLite (开发) / PostgreSQL (生产) |
| 自动化 | Playwright + 剪映 |
| AI | OpenAI 兼容接口 |
| 部署 | Docker Compose |

## 功能模块

1. **Dashboard** — 热点、文案、视频、客户、发布汇总
2. **爆款采集** — 关键词管理、定时采集、AI评分、一键生成文案
3. **文案中心** — AI生成、多版本管理、Prompt模板、全文预览
4. **视频中心** — 配音/字幕/剪映/导出四步骤管理
5. **发布中心** — 多平台发布任务管理
6. **客户管理** — 客户资料、标签、跟进记录
7. **系统设置** — AI模型配置、自动化路径、采集参数

## 快速开始

```bash
# 安装依赖
cd backend && pip install -r requirements.txt
cd ../frontend && npm install

# 启动后端（端口 3456）
cd backend && python app.py

# 启动前端（端口 5173）
cd frontend && npx vite --host
```

访问 http://localhost:5173

## Docker 部署

```bash
docker-compose up -d
```

## 数据库表

- `hot_topic` — 爆款热点
- `script` — 口播文案
- `video_task` — 视频任务
- `customer` — 客户
- `follow_record` — 跟进记录
- `publish_task` — 发布任务
- `system_setting` — 系统设置

## REST API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/dashboard | 仪表盘汇总 |
| GET | /api/hot-topics | 热点列表 |
| POST | /api/hot-topics/collect | 采集热点 |
| POST | /api/hot-topics/:id/generate-script | 生成文案 |
| GET/POST | /api/scripts | 文案CRUD |
| POST | /api/scripts/generate | AI生成文案 |
| GET/POST | /api/videos | 视频CRUD |
| POST | /api/videos/:id/execute/:step | 执行视频步骤 |
| GET/POST | /api/customers | 客户CRUD |
| POST | /api/follows | 添加跟进 |
| GET/POST | /api/publish | 发布CRUD |
| GET/PUT | /api/settings | 系统设置 |
