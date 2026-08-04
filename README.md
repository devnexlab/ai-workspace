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
| **方式 A 必装** PostgreSQL 16+ | 本机跑库 | https://www.postgresql.org/download/windows/ |
| **方式 A 必装** Python 3.11+ | 跑后端 | https://www.python.org/downloads/ （安装时勾选 *Add python.exe to PATH*） |
| **方式 A 必装** Node.js 20 LTS | 跑前端 | https://nodejs.org/ |
| **方式 B 必装** Docker Desktop | 容器部署（含 Postgres） | https://www.docker.com/products/docker-desktop/ |

> Windows 可选两种部署：**方式 A 本机直接跑**，或 **方式 B Docker**。只需装对应方式需要的软件。  
> 方式 A 需要本机 **PostgreSQL**；方式 B 由 Compose 自带数据库，一般不用再装。

### macOS

| 软件 | 用途 | 下载 / 安装 |
|------|------|-------------|
| Git | 拉取代码 | 终端执行 `xcode-select --install`，或 https://git-scm.com/download/mac |
| Docker Desktop | 容器部署（含 Postgres） | https://www.docker.com/products/docker-desktop/ |

macOS 推荐用 **Docker** 部署（见下文）；Compose 已包含 PostgreSQL。本机开发再单独装库即可。

### Linux

| 软件 | 用途 | 安装示例 |
|------|------|----------|
| Git | 拉取代码 | `sudo apt install git`（Debian/Ubuntu） |
| Docker Engine + Compose 插件 | 容器部署（含 Postgres） | 见 https://docs.docker.com/engine/install/ |

Linux 推荐用 **Docker** 部署（见下文）；Compose 已包含 PostgreSQL。本机开发再单独装库即可。

---

## 安装 PostgreSQL

后端依赖 PostgreSQL。安装完成后创建数据库 `ai_ops`，并把账号密码写进 `backend/.env`。

### Windows（安装包）

1. 打开 https://www.postgresql.org/download/windows/ ，用 **EDB 安装器** 下载 PostgreSQL 16（或更新）。
2. 安装向导中：
   - 组件至少勾选 **PostgreSQL Server**、**Command Line Tools**、**pgAdmin**（可选）
   - 端口保持默认 **5432**
   - 设置超级用户 `postgres` 的密码（后面要填进 `.env`）
3. 安装完成后，打开 **SQL Shell (psql)** 或 **pgAdmin**，创建业务库：

```sql
CREATE DATABASE ai_ops;
```

用 psql 命令行时也可：

```bat
psql -U postgres -c "CREATE DATABASE ai_ops;"
```

4. 确认服务已启动：在「服务」里找到 `postgresql-x64-16`（名称因版本而异）为「正在运行」。

### macOS

**方式 1：Homebrew（推荐）**

```bash
brew install postgresql@16
brew services start postgresql@16

# 创建数据库（当前 macOS 用户一般为超级用户）
createdb ai_ops
# 若需 postgres 用户：
# createuser -s postgres
# psql -d postgres -c "ALTER USER postgres PASSWORD '你的密码';"
# createdb -O postgres ai_ops
```

**方式 2：官方安装包**

https://www.postgresql.org/download/macosx/

### Linux（Debian / Ubuntu 示例）

```bash
sudo apt update
sudo apt install -y postgresql postgresql-contrib
sudo systemctl enable --now postgresql

# 切换到 postgres 系统用户后建库建密
sudo -u postgres psql -c "ALTER USER postgres PASSWORD '你的密码';"
sudo -u postgres psql -c "CREATE DATABASE ai_ops OWNER postgres;"
```

若本机用密码登录 `127.0.0.1`，可能还需改 `pg_hba.conf` 中对应行为 `md5` 或 `scram-sha-256`，然后：

```bash
sudo systemctl reload postgresql
```

### 也可用 Docker 只跑数据库

本机不装 Postgres、只起一个数据库容器时：

```bash
docker run -d --name ai-ops-pg \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=ai_ops \
  -p 5432:5432 \
  -v ai_ops_pgdata:/var/lib/postgresql/data \
  postgres:16-alpine
```

此时 `backend/.env` 中：

```env
PG_HOST=127.0.0.1
PG_PORT=5432
PG_DBNAME=ai_ops
PG_USER=postgres
PG_PASSWORD=postgres
```

> 若后端也在 Docker Compose 里跑，容器访问「本机」上的 Postgres 时，Windows / Mac 可用 `host.docker.internal` 作为 `PG_HOST`；Linux 视网络情况改用宿主机 IP 或把 Postgres 一并写进 `docker-compose.yml`。

### 验证能否连上

```bash
psql -h 127.0.0.1 -U postgres -d ai_ops -c "SELECT version();"
```

能输出版本信息即表示数据库就绪。首次启动后端时会自动建表，一般无需手工执行 SQL 建表脚本。

---

## 获取代码

```bash
git clone https://github.com/devnexlab/ai-workspace.git
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

`backend/.env` 至少确认数据库可连（与上面安装时设置的账号一致）：

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
2. 进入项目根目录，确认已有 `backend/.env`（可先从 `backend/.env.example` 复制）。
3. 构建并启动（会一并启动 **PostgreSQL**，无需本机再装数据库）：

```bash
docker compose up -d --build
```

4. 浏览器访问：

| 服务 | 地址 |
|------|------|
| 前端 | http://localhost:5180 |
| 后端 API | http://localhost:3456 |
| PostgreSQL | localhost:5432（库名 `ai_ops`，默认账号见 `.env`） |

常用命令：

```bash
docker compose ps          # 查看状态
docker compose logs -f     # 看日志
docker compose down        # 停止并移除容器（数据卷 pgdata 默认保留）
docker compose down -v     # 停止并删除数据库数据卷（慎用）
docker compose up -d --build   # 改代码后重新构建
```

> Compose 会挂载 `./backend/data`、`outputs`、`uploads`；数据库数据在 Docker 卷 `pgdata` 中。  
> 所有服务加入同一网络 `ai-ops-net`，容器内互访用服务名：`postgres`、`backend`、`frontend`（不要用 `127.0.0.1`）。

---

## Windows 部署

### 方式 A：下载软件后本机直接运行

适合本地开发、调试自动化（Playwright / 剪映等需本机环境时更方便）。

#### 1. 安装软件

安装 **Git、Python 3.11+、Node.js 20 LTS、PostgreSQL**（见上文下载表与「安装 PostgreSQL」）。安装 Python 时务必勾选 **Add to PATH**。

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

适合不想本机装 Python / Node、只要能跑起来的场景。`docker-compose.yml` 已内置 **PostgreSQL**，一般不必再单独装数据库。

#### 1. 安装软件

安装并启动 **Docker Desktop for Windows**（需开启 WSL2，安装向导会提示）。

#### 2. 配置 `.env`

```bat
copy backend\.env.example backend\.env
```

按需改密码等；Compose 会把后端的 `PG_HOST` 设为 `postgres`，连的是同组容器里的数据库。

#### 3. 启动

在项目根目录 PowerShell：

```powershell
docker compose up -d --build
```

#### 4. 访问

- 前端：http://localhost:5180  
- 后端：http://localhost:3456  
- 数据库：localhost:5432（库 `ai_ops`）

```powershell
docker compose logs -f
docker compose down
```

---

## 部署方式对照

| | Windows 方式 A（本机） | Windows 方式 B（Docker） | Linux / macOS（Docker） |
|--|------------------------|--------------------------|-------------------------|
| 需安装 | Git + Python + Node + **PostgreSQL** | Git + Docker Desktop | Git + Docker |
| 数据库 | 本机 / 外置 Postgres | Compose 内置 `postgres` | Compose 内置 `postgres` |
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

**4. 连不上 PostgreSQL / 后端启动报数据库错误**  
- 确认 Postgres 服务已启动，库名 `ai_ops` 已创建  
- `.env` 里 `PG_HOST` / `PG_PORT` / `PG_USER` / `PG_PASSWORD` 与安装时一致  
- Windows / Mac 上后端在 Docker、库在本机时，`PG_HOST` 用 `host.docker.internal`  
- 用 `psql -h 127.0.0.1 -U postgres -d ai_ops` 先测能否登录  

**5. 自选股刷新现价失败**  
需本机或容器能访问外网行情接口；重启后端后再点「刷新现价」。
