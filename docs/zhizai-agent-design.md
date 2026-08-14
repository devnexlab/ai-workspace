# 智仔升级为通用数据智能体 · 技术方案

> 目标：把"智仔"从"运营助手"升级为**能联网读网上数据、也能不联网读自己库所有表、并按用户意图自动选数据源**的通用数据智能体。
> 适用前提：个人号（抖音/小红书/视频号无法升企业号）场景下的本地部署后端（PostgreSQL + Flask + 自配大模型）。

---

## 1. 可行性结论

**三项需求全部可行，且现有底座正确，无需引入新框架。**

经代码核查，智仔（`backend/modules/pet/agent.py` 的 `run_pet_agent`）已是「LLM 意图路由 + 工具调用」架构：

- 意图路由：`_resolve_intents`（关键词）+ `tools_ops.py::plan_ops_with_llm`（让模型输出 JSON plan 选工具）。
- 现有工具：`tools_finance`（金融实时）、`tools_insurance`（保险常识）、`tools_ops`（运营：同步/发布/日更/定时）、`rag.search_vectors`（知识库/文案/股票简报向量召回）。
- 数据库：PostgreSQL（`config.get_db()` 返回 `RealDictCursor` 连接），全表结构在 `database.py::SCHEMA`。

**两个缺口**（即本次要补的）：

1. 无"按自然语言查任意表"的 Text-to-SQL 能力（现仅硬编码读 `stock_watchlist`/`reminder`/`video_task`/`publish_task`）。
2. 无"通用联网搜索/抓网页"工具（现仅有定向数据源：全网热点榜、股票行情/简报）。

`call_llm`（`modules/ai/writer.py`）是**纯 chat/completions，不支持 function calling**。因此新增能力沿用现有「prompt 让模型出 JSON plan / 生成 SQL」模式，不引入 ReAct，改动最小、风格一致。

---

## 2. 目标架构

```
用户提问
   │
   ▼
LLM 意图路由（理解意图 → 选工具）
   │
   ├─► 本地库查询 tools_data   （不联网·按意图查任意表，Text-to-SQL 只读）
   ├─► 联网读取   tools_web    （复用已配模型联网 / 抓指定网页）
   ├─► 知识库 RAG search_vectors
   ├─► 金融实时   tools_finance
   └─► 运营动作   tools_ops
   │
   ▼
汇总 + 引用作答（call_llm，工具结果作为【系统工具结果】）
   │
   ▼
带引用来源的回答
```

新增两个工具（`tools_data` / `tools_web`）并入现有路由，复用 `run_pet_agent` 的 `cites`/`tool_blocks` 流程。

---

## 3. 新增工具一：本地库任意表查询 `modules/pet/tools_data.py`

### 3.1 表结构目录（schema catalog）

运行时用 `information_schema.columns` 动态读取当前库所有表与字段；同时叠加一份**表业务含义映射**，帮模型把人话映射到正确的表：

| 表名 | 业务含义（喂给模型） |
|---|---|
| `customer` | 客户（昵称/微信/电话/意向/阶段） |
| `lead` | 线索（进线未转客户） |
| `follow_record` | 客户跟进记录 |
| `reminder` | 提醒（客户/股票预警） |
| `publish_task` | 发布任务（平台/状态/播放/赞/评） |
| `video_task` | 视频生产任务 |
| `script` | 文案库 |
| `hot_topic` | 全网热点 |
| `knowledge_item` | 知识库条目 |
| `stock_watchlist` | 自选/持仓股 |
| `stock_universe` | 全市场 A 股快照 |
| `stock_daily_briefing` | 股票每日简报 |
| `workflow` | 工作流 |
| `ai_agent` | AI 助手配置 |
| `pet_chat_session` / `pet_chat_message` | 智仔对话历史 |
| `system_setting` | 系统设置 |
| `ops_platform` | 平台配置 |
| `pet_job` | 智仔定时任务 |

> `rag_chunk` / `pg_*` / `information_schema` 等系统/向量表**不暴露**给查询，防止越权或误用。

### 3.2 自然语言 → SQL 生成 `generate_sql(question, history)`

- 输入：用户问题 + 上轮对话（多轮指代，如"那这些客户里北京的有几个"）。
- 用 `call_llm` 输出 JSON：`{"sql": "SELECT ...", "thought": "..."}`。
- 系统提示词硬性约束：
  - 只能 `SELECT`；只能查上表业务表；必须带 `LIMIT`（默认 50，上限 200）。
  - 禁止子查询系统表、禁止 `*` 无 limit、禁止聚合爆量。
  - 时间字段多为 `TEXT`（如 `created_at` 存字符串），模型需按文本比较；给示例。

### 3.3 只读执行与校验 `run_sql_ro(sql)`

- **双保险只读**：
  1. 正则/解析预校验：仅放行以 `SELECT`/`WITH` 开头、无 `;`、`INSERT/UPDATE/DELETE/DROP/ALTER/TRUNCATE` 等关键字。
  2. 执行连接调用 `conn.set_session(readonly=True)`（psycopg2 只读事务），即使 SQL 被绕过也在 DB 层拒绝写入。
- 返回 `(columns, rows)`，行数封顶 200，超量截断并提示。
- 任何失败（SQL 不合法 / 表不存在 / 超时）返回友好错误，并给出"换个说法"建议，**不把原始异常抛给用户**。

### 3.4 接入 `run_pet_agent`

- 在 `_resolve_intents` 增加 `data` 意图；在工具调用段增加：

```python
if intents.get('data'):
    steps.append(_step('工具调用 · 本地库查询（按意图生成 SQL）'))
    try:
        c, text = tool_query_database(q, history=history)
        cites.extend(c); tool_blocks.append(text)
    except Exception as e:
        tool_blocks.append(f'本地库查询失败：{e}')
```

- `tool_query_database(question, history)` 编排：schema → `generate_sql` → 校验 → `run_sql_ro` → 格式化（表格/要点）+ 引用卡片（标注"来源：本地数据库·表X"）。

---

## 4. 新增工具二：联网读取 `modules/pet/tools_web.py`

依据已确认方案：**联网复用已配模型的联网能力（零额外 Key）**。

### 4.1 复用模型联网 `web_search(query)`

各已支持厂商（在 `modules/ai/writer.py` 的 PROVIDER 列表内）联网能力：

| 厂商 | 联网方式 | 实现要点 |
|---|---|---|
| 智谱 GLM | `tools: [{type:"web_search"}]` | `call_llm` 增加 `web_search=True` 开关，拼对应请求字段，解析返回中的搜索结果与引用 |
| 月之暗面 Moonshot | `web_search: true` | 同上，按厂商文档传参 |
| 通义千问 / DeepSeek / 火山 | 部分支持或需开白 | 不支持时优雅降级（见 4.3） |

- 实现：给 `call_llm` 增加可选 `web_search: bool` 参数；在 `tools_web.web_search` 内调用带联网开关的 `call_llm`，把模型基于联网检索的回答 + 引用来源整理成 `cites`/`text`。
- 这样"问最新消息/网上怎么讲"由模型自带联网兜底，无需 Tavily/SerpAPI Key。

### 4.2 抓指定网页 `web_fetch(url)`

- 不依赖任何 Key：用 `requests` 抓取 URL → 抽取正文（去除脚本/样式，取 `<article>`/`<main>`/`<p>` 文本）→ 截断到合理长度。
- 用途："读一下这个链接 https://…" 这类明确诉求。
- 安全：仅允许 `http/https`；限制响应大小与超时；不做登录态爬取。

### 4.3 接入与降级

- `run_pet_agent` 增加 `web` 意图（关键词：网上/搜索/查一下网上/最新消息/新闻/百科/这个链接）。
- 降级链：模型联网可用 → 直接用；模型不支持联网且未配搜索 API → 提示"当前模型不支持联网，可换智谱/月之暗面或在系统设置配置搜索 API"，并仍能处理 `web_fetch`（指定网址）。

---

## 5. 路由/意图判断改造

在 `run_pet_agent` 的 `_resolve_intents` 中新增：

```python
_DATA_KEYS = ('我的数据库','查表','客户表','线索','有多少客户','统计一下','全部表','库里','订单','哪个表')
_WEB_KEYS  = ('网上','搜索','查一下网上','最新消息','新闻','百科','这个链接','网页')
```

- `data`：命中 `_DATA_KEYS`，或 `auto` 模式下无其它强意图且问题像"我的数据/统计"类。
- `web`：命中 `_WEB_KEYS`。
- 二者可并存（如"网上说的最新政策和我库里客户匹配一下"→ 先 web 后 data）。

`auto` 兜底：若 `auto` 且 RAG 无命中、无工具结果，且问题疑似本地数据 → 触发 `tool_query_database`（沿用现有"放宽检索"兜底思路），提升"开箱即问"体验。

---

## 6. 接口与配置

- 复用现有 `POST /api/pet-chat`（`message` / `mode` / `session_id`），`mode` 新增 `'data'` / `'web'` 锁定模式（可选）；返回结构不变（`answer`/`steps`/`cites`/`choices`）。
- 新增系统设置（`system_setting`）：
  - `web.enabled`（默认 true，是否允许联网）。
  - `web.search_provider`（默认 tavily，联网时使用的真实搜索引擎：tavily / brave / serpapi）。
  - `web.search_api_key`（Tavily/Brave/SerpAPI 的 Key；不填则降级到模型厂商原生联网）。
  - `data.query_enabled`（默认 true，是否允许自然语言查库）。
- 表业务含义映射放 `tools_data.py` 常量（随业务表增减维护）。

---

## 7. 安全与合规

- **Text-to-SQL 只读**：正则预校验 + psycopg2 `readonly` 事务双保险；强制 LIMIT≤200；禁止系统/向量表。
- **不触碰写入**：智仔只"读"与"运营动作类工具"（现有 tools_ops 已是人审核/半自动），不新增任何自动写库/发私信。
- **联网范围**：仅公共网页检索与指定 URL 抓取，不做登录态爬取、不模拟点击。
- **引用可溯**：每个答案标注数据来源（本地库表 / 网页 URL / 知识库），不编造。
- **透明告知**：模型联网受限时明确说明，不假装"已联网"。

---

## 8. 分阶段实现计划

- **P0 数据查询（核心）**：`tools_data.py`（schema catalog + generate_sql + run_sql_ro + tool_query_database）+ `run_pet_agent` 接入 + `mode='data'`。
- **P1 联网读取**：`tools_web.py`（web_search 复用模型联网 + web_fetch）+ `call_llm` 增加 `web_search` 开关 + 路由接入 + `mode='web'`。
- **P2 融合与兜底**：`auto` 模式下 data/web 自动判别与兜底；系统设置开关；前端「智仔」对话页增加"数据/联网"来源标签。

---

## 9. 验收标准

- 问"我库里有多少客户、几个高意向" → 智仔生成 SELECT 并正确返回统计，标注来源=本地数据库·customer。
- 问"上个月发布的视频里播放最高的是哪条" → 正确查 `publish_task` 并给出结果。
- 问"网上怎么看最新的个人养老金政策" → 经模型联网给出带引用的回答（或明确说明当前模型不支持联网）。
- 问"读一下这个链接 https://…" → 抓取并返回正文要点。
- 任意"删除/更新/清空"类表述 → 被只读校验拦截，绝不执行写操作。

---

## 10. 待确认 / 开放问题

1. `call_llm` 当前仅对接 OpenAI 兼容 chat 接口；**智谱/月之暗面的联网开关需在 `web_search=True` 时按厂商拼不同请求字段**——实现时按实际厂商文档逐项验证（建议先用智谱 GLM 跑通）。
2. 表业务含义映射是否足够？是否需要把"客户阶段/意向"等业务枚举也喂给模型以减少歧义。
3. 联网回答的"引用来源"是否要持久化进 `pet_chat_message.meta_json`（便于溯源/复查）。
4. 是否需要给数据查询加**行级脱敏**（如 `customer.phone`/`wechat` 默认掩码），防止对话中泄露隐私。
