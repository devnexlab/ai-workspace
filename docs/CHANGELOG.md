# 优化与变更辑录

按时间记录功能与体验优化，便于回顾「做了什么、为什么做」。

---

## 2026-08-07 · 智仔桌宠数据问答

1. **全站桌宠**：右下角「智仔」浮动入口（不进侧栏），对话面板含模式切换、Agent 步骤、引用卡片  
2. **向量 + Agent**：`rag_chunk` 索引知识库 / 文案 / 股票简报；优先厂商 embeddings，否则本地哈希向量；内容意图排除无关简报  
3. **API**：`POST /api/pet-chat`、`POST /api/pet-chat/reindex`、`GET /api/pet-chat/status`；会话写入 `pet_chat_session` / `pet_chat_message`  
4. **文档**：`README` / `FEATURES` 补充入口与充实知识库说明  

### 相关文件

- `backend/modules/{embeddings,pet_rag,pet_agent}.py`、`routes/agents/pet_chat.py`、`database.py`
- `frontend/src/features/pet/*`、`layouts/MainLayout.jsx`
- `docs/prototypes/pet-data-chat.html`、`docs/FEATURES.md`、`README.md`

---

## 2026-08-05 · 官方/商业数据台

1. **设置 · 官方数据台**：巨量算数 / 蝉妈妈 / 新榜 / 自定义，只配 API（Base URL、Key、路径、字段映射）
2. **内容情报**：新增「拉官方数据台」；全量刷新时顺带拉已启用源；来源类型 `commercial`
3. **试拉接口**：`POST /api/commercial-data/test/<provider>` 不入库验连通

### 相关文件

- `backend/modules/content_ops/commercial_data.py`、`database.py`
- `backend/routes/content/hot_topics.py`、`routes/system/settings.py`
- `frontend/.../HotTopics.jsx`、`SettingsModulePage.jsx`、`MainLayout.jsx`

---

## 2026-08-05 · 采集/发布防封号

1. **采集**：抖音/小红书/视频号登录态采集默认关闭；日更继续只用公开热榜  
2. **发布**：默认「准备发布」= 复制文案 + 打开官方创作者页 + 人工点发表；Playwright 自动填充降为高风险高级选项  
3. **就绪检查**：不再强制 Cookie/Playwright 才能算发布就绪  

### 相关文件

- `backend/database.py`、`modules/content_ops/platforms.py`、`pipeline.py`
- `backend/routes/system/settings.py`、`routes/publish/publish.py`
- `frontend/src/features/content/{Publish,HotTopics}.jsx`、`settings/SettingsModulePage.jsx`
- `docs/FEATURES.md`

---

## 2026-08-04 · 发布链接与咨询自动同步

1. **作品链接**：发布浏览器会话尽量自动检测并回填；确认弹窗可预填  
2. **同步互动**：从创作者作品管理页拉取赞/评；有点赞或评论则自动标「有咨询」（互动代理，仍可手动改）  

### 相关文件

- `backend/modules/publisher.py`、`backend/routes/publish/publish.py`、`backend/database.py`
- `frontend/src/features/content/Publish.jsx`、`frontend/src/api/content.js`

---

## 2026-08-04 · 中低优先级功能

1. **视频参数记忆**：成功出片后记住音色/分辨率/风格/素材，创建与日更出片自动预填  
2. **发布复盘**：`got_consult` 标记 + 本周已发/咨询率（发布页与总览）  
3. **股票预警**：目标价 / 跌破成本 → 提醒铃  
4. **素材库**：场景 / BGM / 封面 + 风格标记，合成可混 BGM  
5. **知识导入**：PDF（pypdf）/ 录音（faster-whisper，需另装）上传抽文本  

### 相关文件

- `backend/routes/video/videos.py`、`content/scripts.py`、`content/materials.py`、`publish/publish.py`、`knowledge/knowledge.py`、`stocks/stocks.py`
- `backend/modules/stock_watchlist_scheduler.py`、`video_composer.py`、`content_ops/daily_runner.py`
- `frontend/src/features/{content,stocks,knowledge,dashboard,notifications}/*`

---

## 2026-08-04 · 数据大屏图表化

总览改为图表主视觉：KPI 条 + 流水线漏斗、平台环图、近 7 日趋势、文案状态柱图、客户意向饼图；底部保留最新动态列表。接口新增 `trends` / `pipeline` / `scriptStatusDist` / `customerIntentionDist`。

### 相关文件

- `backend/routes/system/dashboard.py`
- `frontend/src/features/dashboard/Dashboard.jsx` / `Dashboard.css`
- `frontend/package.json`（`recharts`）

---

## 2026-08-04 · 总览去掉今日工作台

今日工作台与顶栏待办铃重复，已移除；总览只保留数据大屏。配置就绪改在系统设置查看。

### 相关文件

- `frontend/src/features/dashboard/Dashboard.jsx` / `Dashboard.css`

---

## 2026-08-04 · 总览页第二版布局

默认「先干活、再看数」：今日工作台置顶，数据大屏下移；顶栏增加待办汇总徽标；工作台与大屏视觉降噪、间距更紧凑。（后续已去掉工作台，见上条）

### 相关文件

- `frontend/src/features/dashboard/Dashboard.jsx` / `Dashboard.css`

---

## 2026-08-04 · 用户体验优化（第一批）

依据「今日干什么 → 干完回写 → 失败能接着干」优先级落地。

### 新增

1. **总览两大区块**  
   页面拆成「数据大屏」与「今日工作台」：前者看指标与动态，后者处理积压与配置就绪。

2. **配置就绪清单（总览）**  
   展示 AI / 采集 / 发布 / Playwright / FFmpeg 是否就绪，未配置可直达设置。

3. **发布结果回写**  
   确认已发时可填写作品链接；记录 `published_at`；列表展示链接与发布时间。

4. **视频失败步重试**  
   任一步失败时显示错误信息与「重试失败步骤」，从第一个失败环节继续。

5. **待办深链**  
   待办项跳转带 `focus` / 状态筛选，目标页自动定位或过滤。

6. **日更预期说明**  
   文案中心标明日更会做什么、不会做什么，避免误以为全自动发布。

7. **发布失败提示增强**  
   展示 `error_msg`；登录/待确认文案更明确。

### 文档

- 新增 `docs/FEATURES.md`（功能手册）
- 新增本文件 `docs/CHANGELOG.md`

### 相关文件（主要）

- `frontend/src/features/dashboard/Dashboard.jsx` / `Dashboard.css`
- `frontend/src/features/notifications/TodoBell.jsx`
- `frontend/src/features/content/{Scripts,Videos,Publish}.jsx`
- `backend/routes/system/{dashboard,settings}.py`
- `backend/routes/publish/publish.py`
- `backend/database.py`（`publish_task.published_at`）

---

## 更早已具备的能力（基线）

- 总览数据大屏与动态列表；待办/提醒分离
- 内容情报、文案出片、视频四步流水线、半自动发布
- 客户 CRM + 提醒、知识库、股票自选与现价刷新
- Docker Compose（`ai-ops-net` + Postgres）、根目录 `pyproject.toml` 统一后端依赖、`frontend/package.json` 管理前端依赖
- README：分系统部署、PostgreSQL、FFmpeg / Playwright 说明
