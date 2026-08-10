# AI 智能运营系统

面向个人经营者与小团队的 **内容运营 + 客户管理 + 视频生产 + 股票研究** 一体化后台。

用 AI 写口播、合成短视频、跟进客户，并把微信公众号作为对外留资入口；顾问侧用 Web 后台，客户侧用手机微信打开页面。

| 文档 | 说明 |
|------|------|
| [**部署文档**](docs/DEPLOY.md) | 本机 / Docker / 云服务器公网、域名 HTTPS、微信公众号挂链（完整步骤） |
| [功能说明](docs/FEATURES.md) | 模块与能力说明 |
| [变更记录](docs/CHANGELOG.md) | 版本变更 |

---

## 功能概览

| 模块 | 说明 |
|------|------|
| 总览 | 热点、文案、视频、客户、发布等数据一览 |
| 内容情报 | 全网热榜、官方数据台 API、选题 |
| 文案中心 | AI 生成口播文案、日更、出片 |
| 视频中心 | 配音 / 字幕 / 合成导出 |
| 发布中心 | 复制文案 + 打开官方创作者页（人工确认发布） |
| 客户管理 | 客户档案、跟进、提醒；线索池承接公众号留资 |
| 知识库 | 笔记与材料沉淀（供智仔检索） |
| 股票研究 | 市场概览 + 自选股、筛选、预警 |
| 智仔 · 数据问答 | 全站右下角桌宠：向量检索知识库/文案 + Agent 引用作答 |
| AI 助手 | Agent / 工作流 |
| 系统设置 | 大模型、推送、公众号对外页等（统一入口） |
| 微信对外页 | `/m/about` 介绍、`/m/book` 预约留资（挂公众号菜单） |

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React 18 · Ant Design 5 · Vite |
| 后端 | Python · Flask |
| 数据库 | PostgreSQL 16 |
| 视频 | MoviePy · FFmpeg · edge-tts |
| AI | OpenAI 兼容接口（智谱 / 火山 / DeepSeek / OpenAI 等） |
| 部署 | Docker Compose · Nginx / Caddy · 云服务器 |

依赖声明见 [`backend/pyproject.toml`](backend/pyproject.toml)；前端见 [`frontend/package.json`](frontend/package.json)。

---

## 架构说明

```text
顾问（电脑） ──► Web 管理后台 ──► Flask API ──► PostgreSQL

客户（微信） ──► 公众号菜单 ──► https://你的域名/m/about|/m/book
                              （必须公网可访问，推荐 HTTPS）
```

- 仅顾问本机使用：可不买域名。  
- 客户微信要打开介绍 / 预约页：必须部署到公网，并配置域名（详见 [部署文档](docs/DEPLOY.md)）。

---

## 快速开始

### Docker（推荐）

```bash
git clone https://github.com/devnexlab/ai-workspace.git
cd ai-workspace
cp backend/.env.example backend/.env
docker compose up -d --build
```

访问：前端 http://localhost:5180 · 后端 http://localhost:3456 · 健康检查 `/api/health`  

Windows 也可双击 **`安装并启动.bat`**。

### 本机开发

见 [部署文档 · 方式 A](docs/DEPLOY.md#3-方式-a本机开发启动)。

### 公网 / 域名 / 微信公众号

完整步骤（云服务器、安全组、Nginx/Caddy、备案 HTTPS、菜单挂链、验收清单）：

**→ [`docs/DEPLOY.md`](docs/DEPLOY.md)**

---

## 致谢

感谢以下开源项目与服务（排名不分先后）：

- [React](https://react.dev/) · [Vite](https://vitejs.dev/) · [Ant Design](https://ant.design/)
- [Flask](https://flask.palletsprojects.com/) · [psycopg2](https://www.psycopg.org/) · [PostgreSQL](https://www.postgresql.org/)
- [MoviePy](https://zulko.github.io/moviepy/) · [FFmpeg](https://ffmpeg.org/) · [edge-tts](https://github.com/rany2/edge-tts)
- [Playwright](https://playwright.dev/) · [AKShare](https://github.com/akfamily/akshare)
- [Docker](https://www.docker.com/) · [Nginx](https://nginx.org/) · [Caddy](https://caddyserver.com/)

以及智谱、火山引擎、DeepSeek、OpenAI 等大模型服务商提供的开放 API。

欢迎 Star；问题与建议可通过 GitHub Issues 反馈。

---

## 许可证

若仓库含 `LICENSE` 文件，以该文件为准；未声明时请仅作个人 / 团队内部使用，商用前请自行评估合规要求。

行情与第三方数据仅供学习与辅助决策，**不构成投资建议**。请遵守各平台规则，注意账号安全。
