# 部署文档

本文说明如何把 **AI 智能运营系统** 跑起来，以及如何做成 **手机微信 / 公网可访问** 的服务（含域名、HTTPS、微信公众号挂链）。

> 功能说明见 [`FEATURES.md`](FEATURES.md) · 项目总览见根目录 [`README.md`](../README.md)

---

## 目录

1. [先搞清楚：本机 vs 公网](#1-先搞清楚本机-vs-公网)
2. [端口与组件](#2-端口与组件)
3. [方式 A：本机开发启动](#3-方式-a本机开发启动)
4. [方式 B：Docker 一键部署（推荐）](#4-方式-bdocker-一键部署推荐)
5. [方式 C：云服务器公网部署（生产）](#5-方式-c云服务器公网部署生产)
6. [域名、备案与 HTTPS](#6-域名备案与-https)
7. [关联微信公众号](#7-关联微信公众号)
8. [环境变量清单](#8-环境变量清单)
9. [升级、备份与运维](#9-升级备份与运维)
10. [验收清单](#10-验收清单)
11. [故障排查](#11-故障排查)

---

## 1. 先搞清楚：本机 vs 公网

| 你的目标 | 怎么部署 | 域名 / HTTPS |
|----------|----------|--------------|
| 只有顾问在电脑上用后台 | 本机或 Docker 即可 | 不需要 |
| 客户要在 **微信** 里打开介绍页 / 预约页 | 必须部署到 **有公网 IP 的服务器** | **强烈推荐** 备案域名 + HTTPS |
| 顾问本地 + 客户微信 | 两套环境：本地给顾问调试，云上给客户访问；或全部放云上 | 对外页必须用云上地址 |

**重要结论：**

- 客户微信 **无法打开** `http://localhost:5180` 或你电脑的局域网 IP（除非客户和你在同一 Wi‑Fi，实际不可用）。
- 公众号菜单里的链接，必须是客户手机能访问的地址，例如 `https://ops.example.com/m/about`。
- 「顾问电脑装好了」≠「客户能打开」。对外页请走云服务器（或临时用内网穿透做联调，不建议长期生产）。

```text
顾问浏览器 ──► https://你的域名/          （管理后台）
客户微信菜单 ──► https://你的域名/m/about  （介绍）
               https://你的域名/m/book   （预约留资）
                    │
                    ▼
            云服务器 Docker
            ┌ frontend :80（映射宿主机 5180）
            ├ backend  :3456
            └ postgres :5432
```

---

## 2. 端口与组件

| 组件 | 容器名（Docker） | 宿主机端口 | 说明 |
|------|------------------|------------|------|
| 前端 | `ai-ops-frontend` | **5180** → 容器 80 | Nginx 托管静态资源，并把 `/api` 转到后端 |
| 后端 | `ai-ops-backend` | **3456** | Flask API |
| 数据库 | `ai-ops-postgres` | **5432** | PostgreSQL 16，库名默认 `ai_ops` |

健康检查：

```bash
curl http://127.0.0.1:3456/api/health
```

生产经域名反代后，只对外暴露 **80 / 443**，不必把 3456、5432 开到公网。

---

## 3. 方式 A：本机开发启动

适合改代码、本地调试。**不适合**给客户微信用。

### 3.1 依赖

| 软件 | 建议版本 |
|------|----------|
| Git | 最新 |
| Python | 3.11+ |
| Node.js | 20 LTS |
| PostgreSQL | 16+ |
| FFmpeg | 推荐（视频合成） |

### 3.2 配置

```bash
git clone https://github.com/devnexlab/ai-workspace.git
cd ai-workspace
cp backend/.env.example backend/.env
```

编辑 `backend/.env`：填好数据库账号；生产/客户机务必 `FLASK_DEBUG=false`。

在 PostgreSQL 中建库：

```sql
CREATE DATABASE ai_ops;
```

### 3.3 Windows

```bat
uv sync
.venv\Scripts\playwright install chromium

cd frontend && npm install && cd ..

start_backend.bat
start_frontend.bat
```

（也可用 `python -m venv .venv` 后 `pip install -e .` 代替 `uv sync`。）

停止：`stop_backend.bat` / `stop_frontend.bat`。

### 3.4 Linux / macOS

```bash
uv sync
# 或: python3 -m venv .venv && source .venv/bin/activate && pip install -e .
.venv/bin/playwright install chromium

cd frontend && npm install
npm run dev
```

另开终端：

```bash
cd backend && ../.venv/bin/python app.py
```

### 3.5 访问

| 服务 | 地址 |
|------|------|
| 前端 | http://localhost:5180 |
| 后端 | http://localhost:3456 |
| 健康检查 | http://localhost:3456/api/health |

首次启动后端会自动建表。

---

## 4. 方式 B：Docker 一键部署（推荐）

适合本机或服务器「不想装 Python / Node / Postgres」。

### 4.1 前置

- 已安装 [Docker](https://docs.docker.com/get-docker/) 与 Compose 插件  
- Windows 可用 Docker Desktop；也可双击仓库根目录 **`安装并启动.bat`**

### 4.2 启动

```bash
git clone https://github.com/devnexlab/ai-workspace.git
cd ai-workspace
cp backend/.env.example backend/.env
# 至少修改 PG_PASSWORD，并确认 FLASK_DEBUG=false

docker compose up -d --build
```

Compose 会把后端的 `PG_HOST` 覆盖为服务名 `postgres`，**不要**在容器场景下把 `PG_HOST` 写成 `127.0.0.1`。

### 4.3 访问与常用命令

| 服务 | 地址 |
|------|------|
| 前端 | http://localhost:5180 |
| 后端 | http://localhost:3456 |
| 数据库 | localhost:5432（库 `ai_ops`） |

```bash
docker compose ps
docker compose logs -f
docker compose logs -f backend
docker compose restart backend
docker compose down          # 停止，保留数据卷
docker compose down -v       # 停止并删除数据库数据（慎用）
```

数据持久化：

- 数据库：Docker volume `pgdata`
- 业务文件：`backend/data`、`backend/outputs`、`backend/uploads`（挂载进容器）

---

## 5. 方式 C：云服务器公网部署（生产）

目标：手机浏览器 / 微信能访问管理后台与 `/m/about`、`/m/book`。

### 5.1 选购与安全组

| 项 | 建议 |
|----|------|
| 系统 | Ubuntu 22.04 LTS（或同类 Linux） |
| 配置 | 2 核 4G 起；经常合成视频建议 4 核 8G |
| 磁盘 | 40GB+ |
| 公网 | 需要公网 IP |
| 安全组 | 先放行 **22**（SSH）、**80**、**443**；联调阶段可临时放行 **5180** |

**不要**长期把 PostgreSQL `5432` 对整个公网开放。

云厂商操作位置通常在：云服务器 → 安全组 / 防火墙 → 入站规则。

### 5.2 安装 Docker（Ubuntu 示例）

以官方文档为准：[Install Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/)

摘要：

```bash
sudo apt update
sudo apt install -y git ca-certificates curl
# …按官方步骤安装 docker-ce、containerd、docker-compose-plugin…

sudo usermod -aG docker $USER
# 退出 SSH 再登录，使 docker 组生效
docker version
docker compose version
```

### 5.3 部署应用

```bash
git clone https://github.com/devnexlab/ai-workspace.git
cd ai-workspace
cp backend/.env.example backend/.env
nano backend/.env
```

`backend/.env` 生产必改：

```env
PG_PASSWORD=换成足够长的随机密码
FLASK_DEBUG=false
```

启动：

```bash
docker compose up -d --build
docker compose ps
curl http://127.0.0.1:3456/api/health
```

### 5.4 先用公网 IP 验证（可选）

1. 安全组临时放行 **5180**  
2. 手机浏览器打开：`http://你的公网IP:5180`  
3. 再试：`http://你的公网IP:5180/m/about`

能打开后，再配域名与 HTTPS（下一节）。正式对外不要长期依赖「裸 IP + HTTP」。

### 5.5 防火墙（若系统启用了 ufw）

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
# 联调可临时：sudo ufw allow 5180/tcp
sudo ufw enable
sudo ufw status
```

---

## 6. 域名、备案与 HTTPS

国内云主机给公众号用时，常见要求：**域名已备案 + HTTPS**。海外服务器规则不同，但仍建议 HTTPS。

### 6.1 域名准备

1. 购买域名（任意注册商）。  
2. 服务器在中国大陆：按云厂商流程完成 **ICP 备案**。  
3. 添加 DNS **A 记录**：

```text
主机记录：ops（或 @）
记录值：你的云服务器公网 IP
```

例如解析结果：`ops.example.com` → `1.2.3.4`。

等待解析生效（可用 `ping ops.example.com` 或在线 DNS 查询确认）。

### 6.2 方案一：Nginx + Let’s Encrypt（常用）

服务器安装 Nginx，把 80/443 反代到本机 Docker 前端 `127.0.0.1:5180`。  
前端容器内已把 `/api` 转到 `backend:3456`，因此 **只反代前端即可**。

创建站点配置 `/etc/nginx/sites-available/ai-ops`：

```nginx
server {
    listen 80;
    server_name ops.example.com;

    client_max_body_size 100m;

    location / {
        proxy_pass http://127.0.0.1:5180;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
    }
}
```

启用并申请证书：

```bash
sudo ln -s /etc/nginx/sites-available/ai-ops /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d ops.example.com
```

完成后对外地址：

```text
https://ops.example.com
```

建议：安全组保留 80/443；可关闭公网 5180、3456。

### 6.3 方案二：Caddy（自动 HTTPS）

安装 Caddy 后写入 Caddyfile：

```caddy
ops.example.com {
    reverse_proxy 127.0.0.1:5180
}
```

启动 Caddy，确认域名已解析且 80/443 可达，证书会自动申请与续期。

### 6.4 在系统里填写「对外访问地址」

1. 浏览器打开 `https://ops.example.com` 登录管理后台。  
2. 进入 **系统设置 → 微信服务号**（或「微信公众号」相关模块）。  
3. 配置示例：

| 配置项 | 填写示例 |
|--------|----------|
| 启用对外页 | 开启 |
| 对外访问地址 | `https://ops.example.com`（**不要**末尾 `/`） |
| 品牌名 / 介绍文案 | 按业务填写 |

4. 保存后复制：
   - 介绍页：`https://ops.example.com/m/about`
   - 预约页：`https://ops.example.com/m/book`

---

## 7. 关联微信公众号

本项目阶段①：`公众号自定义菜单 → 跳转网页（H5）`。  
**小程序账号不能当成公众号用**，需单独注册「公众号」。

### 7.1 注册公众号

1. 打开 [微信公众平台](https://mp.weixin.qq.com/) → **立即注册** → 选 **公众号**（不要选小程序）。  
2. 主体：
   - **个人**：多为 **订阅号**；阶段①挂菜单一般可用。  
   - **企业**：可申请 **服务号**，后续能力更全。  
3. 注册完成后，用「切换账号」进入公众号后台（不是小程序列表）。

### 7.2 配置菜单链接

前置：公网 HTTPS（或至少公网可访问地址）已通；系统内「对外访问地址」已保存。

1. 公众平台 → **自定义菜单**（菜单名称以后台实际为准）。  
2. 菜单类型选 **跳转网页**，粘贴：
   - `https://你的域名/m/about`
   - `https://你的域名/m/book`
3. **保存并发布**。  
4. 手机微信打开公众号 → 点菜单 → 确认页面能打开。  
5. 在预约页提交一条测试留资。  
6. 管理后台 **客户管理** 应出现来源为「微信服务号」的记录；若已配置消息推送，顾问侧会收到通知。

### 7.3 微信侧常见限制

- 未备案域名、仅 HTTP、或本机地址：菜单可能无法配置，或手机打不开。  
- 订阅号与服务号能力不同，但「菜单跳转 H5」阶段①通常都够用。  
- 业务域名 / JS 安全域名等：当前阶段若只做简单 H5 打开与表单提交，一般按公众平台提示补齐即可。

---

## 8. 环境变量清单

文件：`backend/.env`（可从 `backend/.env.example` 复制）。

| 变量 | 说明 | 生产建议 |
|------|------|----------|
| `PG_HOST` | 数据库主机 | Compose 内由编排覆盖为 `postgres`；本机直连用 `127.0.0.1` |
| `PG_PORT` | 端口 | `5432` |
| `PG_DBNAME` | 库名 | `ai_ops` |
| `PG_USER` / `PG_PASSWORD` | 账号密码 | **改强密码** |
| `PG_POOL_MIN` / `PG_POOL_MAX` | 连接池 | 默认即可 |
| `FLASK_HOST` | 监听地址 | `0.0.0.0` |
| `FLASK_PORT` | 端口 | `3456` |
| `FLASK_DEBUG` | 调试模式 | **必须 `false`** |
| `FLASK_THREADED` | 多线程 | `true` |

前端生产镜像一般无需 `.env`；开发见 `frontend/.env.example`。

---

## 9. 升级、备份与运维

### 9.1 升级代码

```bash
cd ai-workspace
git pull
docker compose up -d --build
```

拉取含 **智仔数据问答** 等改动后：重启后端即可（启动时 `init_db` 会自动建 `rag_chunk` / 会话表，**无需手写 SQL**）。生产环境前端需重新构建（上例 `docker compose up -d --build` 已包含）。首次提问会按知识库/文案自动建向量索引，数据量大时首问可能稍慢；也可调用 `POST /api/pet-chat/reindex` 预热。

### 9.2 备份数据库

```bash
# 导出
docker compose exec -T postgres pg_dump -U postgres ai_ops > backup-$(date +%F).sql

# 恢复（会覆盖现有数据，谨慎）
cat backup-YYYY-MM-DD.sql | docker compose exec -T postgres psql -U postgres ai_ops
```

同时备份目录：`backend/uploads`、`backend/outputs`、`backend/data`。

### 9.3 查看日志

```bash
docker compose logs -f --tail=200 backend
docker compose logs -f --tail=200 frontend
docker compose logs -f --tail=200 postgres
```

### 9.4 资源占用提示

视频合成、Playwright、大模型请求较耗 CPU/内存。若云主机卡顿，先升配或错峰合成，并确认 `FLASK_DEBUG=false`。

---

## 10. 验收清单

按顺序勾选：

- [ ] `docker compose ps` 三个服务均为 healthy / running  
- [ ] `curl http://127.0.0.1:3456/api/health` 成功  
- [ ] 本机或服务器浏览器能打开前端并登录后台  
- [ ] （公网）手机浏览器能打开 `https://域名` 或 `http://公网IP:5180`  
- [ ] 手机能打开 `/m/about`、`/m/book`  
- [ ] 设置里「对外访问地址」已填公网域名（无末尾斜杠）  
- [ ] 公众号菜单已发布，微信内可打开并提交留资  
- [ ] 客户管理出现对应线索；安全组未对公网开放 5432  

---

## 11. 故障排查

| 现象 | 排查 |
|------|------|
| 前端能开，接口全失败 | 后端是否启动；`/api/health`；`docker compose logs backend` |
| 数据库连接失败 | 密码是否与 compose 一致；Compose 下 `PG_HOST` 应为 `postgres` |
| 公网 IP 打不开 | 安全组 / ufw 是否放行；Docker 是否在跑；是否用了正确端口 5180 |
| 域名打不开 | DNS 是否指向本机；Nginx/Caddy 是否监听 80/443；证书是否申请成功 |
| 微信菜单打不开 | 是否填了 localhost；是否 HTTPS/备案；手机流量下是否可访问同一 URL |
| 只有小程序没有公众号 | 需重新注册「公众号」，不能互相转换 |
| 视频合成失败 | Docker 镜像已含 ffmpeg；本机部署需安装 FFmpeg 并配置 PATH |
| AI 调用失败 | 服务器能否访问模型厂商域名；检查 Key 与网络 |

---

## 附录：最小公网部署命令速查

```bash
# 1. 服务器装好 Docker 后
git clone https://github.com/devnexlab/ai-workspace.git
cd ai-workspace
cp backend/.env.example backend/.env
# 编辑 PG_PASSWORD、FLASK_DEBUG=false

docker compose up -d --build

# 2. 配好域名解析后（Nginx 示例略，见上文第 6 节）
# 对外：https://ops.example.com

# 3. 后台设置「对外访问地址」= https://ops.example.com
# 4. 公众号菜单挂：
#    https://ops.example.com/m/about
#    https://ops.example.com/m/book
```
