# AI 智能运营系统

内容运营、客户管理、视频发布与股票研究一体化的全栈系统。

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React 18 + Ant Design 5 + Vite |
| 后端 | Python + Flask |
| 数据库 | PostgreSQL（生产）/ 可按配置切换 |
| 自动化 | Playwright（采集 / 发布） |
| AI | OpenAI 兼容接口 |
| 部署 | Docker Compose / 本地直接运行 |

## 功能模块

1. **总览** — 热点、文案、视频、客户、发布等数据一览
2. **内容情报** — 全网热点采集、AI 评分、选题
3. **文案中心** — AI 生成口播文案、出片
4. **视频中心** — 配音 / 字幕 / 剪辑 / 导出
5. **发布中心** — 多平台发布任务
6. **客户管理** — 客户资料、跟进、提醒
7. **知识库** — 知识条目沉淀
8. **股票研究** — 自选股、筛选、策略、AI 复盘（现价可定时刷新）
9. **AI 助手 / Agents** — 运营与客户相关工作流
10. **系统设置** — AI 模型、路径与业务参数

---

## 部署前：先下载软件

按你的操作系统安装下列工具，再继续部署。

### Windows

| 软件 | 用途 | 下载 |
|------|------|------|
| Git | 拉取代码 | https://git-scm.com/download/win |
| **方式 A 必装** Python 3.11+ | 跑后端 | https://www.python.org/downloads/ （安装时勾选 *Add python.exe to PATH*） |
| **方式 A 必装** Node.js 20 LTS | 跑前端 | https://nodejs.org/ |
| **方式 B 必装** Docker Desktop | 容器部署 | https://www.docker.com/products/docker-desktop/ |

> Windows 可选两种部署：**方式 A 本机直接跑**，或 **方式 B Docker**。只需装对应方式需要的软件。

### macOS

| 软件 | 用途 | 下载 / 安装 |
|------|------|-------------|
| Git | 拉取代码 | 终端执行 `xcode-select --install`，或 https://git-scm.com/download/mac |
| Docker Desktop | 容器部署 | https://www.docker.com/products/docker-desktop/ |

macOS 推荐用 **Docker** 部署（见下文）。

### Linux

| 软件 | 用途 | 安装示例 |
|------|------|----------|
| Git | 拉取代码 | `sudo apt install git`（Debian/Ubuntu） |
| Docker Engine + Compose 插件 | 容器部署 | 见 https://docs.docker.com/engine/install/ |

Linux 推荐用 **Docker** 部署（见下文）。

---

## 获取代码

```bash
git clone https://github.com/spp742513/ai-workspace.git
cd ai-workspace
```

---

## 配置环境变量（所有方式都建议做）

```bash
# 后端
cp backend/.env.example backend/.env
# 按实际修改 PostgreSQL 等配置

# 前端（可选，有默认值）
cp frontend/.env.example frontend/.env
```

`backend/.env` 至少确认数据库可连：

```env
PG_HOST=127.0.0.1
PG_PORT=5432
PG_DBNAME=ai_ops
PG_USER=postgres
PG_PASSWORD=你的密码

FLASK_HOST=0.0.0.0
FLASK_PORT=3456
```

---

## Linux / macOS：Docker 部署（推荐）

1. 安装并启动 **Docker Desktop**（Mac）或 **Docker Engine**（Linux）。
2. 进入项目根目录，确认已有 `backend/.env`。
3. 构建并启动：

```bash
docker compose up -d --build
```

4. 浏览器访问：

| 服务 | 地址 |
|------|------|
| 前端 | http://localhost:5180 |
| 后端 API | http://localhost:3456 |

常用命令：

```bash
docker compose ps          # 查看状态
docker compose logs -f     # 看日志
docker compose down        # 停止并移除容器
docker compose up -d --build   # 改代码后重新构建
```

> Compose 会挂载 `./backend/data` 到容器，输出与缓存会落在本机该目录。

---

## Windows 部署

### 方式 A：下载软件后本机直接运行

适合本地开发、调试自动化（Playwright / 剪映等需本机环境时更方便）。

#### 1. 安装软件

安装 **Git、Python 3.11+、Node.js 20 LTS**（见上文下载表）。安装 Python 时务必勾选 **Add to PATH**。

#### 2. 配置 `.env`

按上文复制并修改 `backend/.env`。

#### 3. 安装依赖（首次）

在 **PowerShell** 或 **CMD** 中：

```bat
cd backend
python -m venv venv
venv\Scripts\pip install -r requirements.txt

cd ..\frontend
npm install
```

如需浏览器自动化，在 `backend` 虚拟环境中再执行：

```bat
venv\Scripts\playwright install
```

#### 4. 启动

项目根目录已提供脚本，**各开一个窗口**：

```bat
start_backend.bat
start_frontend.bat
```

或手动启动：

```bat
:: 后端（端口 3456）
cd backend
venv\Scripts\python.exe app.py

:: 前端（默认开发端口见 frontend/.env，一般为 5180）
cd frontend
npm run dev
```

#### 5. 访问

- 前端：http://localhost:5180  
- 后端：http://localhost:3456  

---

### 方式 B：Docker 部署

适合不想本机装 Python / Node、只要能跑起来的场景。

#### 1. 安装软件

安装并启动 **Docker Desktop for Windows**（需开启 WSL2，安装向导会提示）。

#### 2. 配置 `.env`

复制并修改 `backend/.env`（数据库若在局域网其它机器，把 `PG_HOST` 写成可达地址；容器访问本机服务时常用 `host.docker.internal`）。

#### 3. 启动

在项目根目录 PowerShell：

```powershell
docker compose up -d --build
```

#### 4. 访问

- 前端：http://localhost:5180  
- 后端：http://localhost:3456  

```powershell
docker compose logs -f
docker compose down
```

---

## 部署方式对照

| | Windows 方式 A（本机） | Windows 方式 B（Docker） | Linux / macOS（Docker） |
|--|------------------------|--------------------------|-------------------------|
| 需安装 | Git + Python + Node | Git + Docker Desktop | Git + Docker |
| 启动 | `start_*.bat` 或手动 | `docker compose up -d` | `docker compose up -d` |
| 前端地址 | http://localhost:5180 | http://localhost:5180 | http://localhost:5180 |
| 后端地址 | http://localhost:3456 | http://localhost:3456 | http://localhost:3456 |
| 适用 | 开发、本机自动化 | 快速部署 | 推荐生产 / 一键部署 |

---

## 数据库相关表（节选）

- `hot_topic` — 热点
- `script` — 口播文案
- `video_task` — 视频任务
- `customer` / `follow_record` — 客户与跟进
- `publish_task` — 发布
- `stock_watchlist` — 自选股
- `knowledge_item` — 知识库
- `system_setting` — 系统设置

## 主要 API（节选）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/dashboard | 总览汇总 |
| GET/POST | /api/hot-topics | 热点 |
| GET/POST | /api/scripts | 文案 |
| POST | /api/scripts/:id/produce | 文案出片 |
| GET/POST | /api/videos | 视频任务 |
| GET/POST | /api/customers | 客户 |
| GET/POST | /api/publish | 发布 |
| GET/POST | /api/stocks/watchlist | 自选股 |
| POST | /api/stocks/watchlist/refresh-prices | 刷新自选股现价 |
| GET/PUT | /api/settings | 系统设置 |

---

## 常见问题

**1. Windows 上 `python` / `pip` 找不到**  
重新安装 Python 并勾选 *Add to PATH*，或使用完整路径：`backend\venv\Scripts\python.exe`。

**2. Docker 起不来 / 端口被占用**  
确认 5180、3456 未被占用；Docker Desktop 已启动；Linux 用户是否在 `docker` 组：`sudo usermod -aG docker $USER` 后重新登录。

**3. 前端能开但接口失败**  
检查后端是否在跑、`backend/.env` 数据库是否通；Docker 下看 `docker compose logs backend`。

**4. 自选股刷新现价失败**  
需本机或容器能访问外网行情接口；重启后端后再点「刷新现价」。
