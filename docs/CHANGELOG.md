# 优化与变更辑录

按时间记录功能与体验优化，便于回顾「做了什么、为什么做」。

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
- Docker Compose（`ai-ops-net` + Postgres）、`pyproject.toml` 统一依赖
- README：分系统部署、PostgreSQL、FFmpeg / Playwright 说明
