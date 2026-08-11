# 智能运营台 · 设计系统与 UI 升级说明

> UI Designer 交付 · 在既有 Linear 风格基础上精修，新增深色模式、统一组件库、移动端适配与微动效。

## 一、本次交付内容

| 模块 | 文件 | 说明 |
| --- | --- | --- |
| 设计令牌 + 深色模式 | `src/styles/theme.css` | 全量深色变量 `[data-theme="dark"]`、各页面深色覆盖、统一原语类、微动效 |
| 主题 Provider | `src/theme/ThemeProvider.jsx`、`src/theme/ThemeContext.js` | 运行时切换 antd 暗色算法、localStorage 持久化、跟随系统偏好 |
| 共享组件库 | `src/components/ui/*` | `PageHeader` `StatCard` `Toolbar` `EmptyState` `Skeleton` `Sparkline` `ThemeToggle` |
| 布局外壳 | `src/layouts/MainLayout.jsx` | 顶栏主题切换、移动端抽屉式侧栏（汉堡菜单 + Drawer）、面包屑 |
| 入口接入 | `src/main.jsx` | 引入 `theme.css`，用 `ThemeProvider` 包裹 |
| 仪表盘示范 | `src/features/dashboard/Dashboard.jsx` | KPI 卡改用统一 `StatCard`，获得一致趋势/迷你图/悬浮微交互 |

## 二、设计语言

- **品牌色**：主色 `#5b5bd6`（紫），派生浅 `#7d7dff` / 深 `#4a4ab8`；语义色 成功 `#00b884`、警告 `#ff9500`、错误 `#ff3b5c`、信息 `#3b82f6`。
- **圆角**：sm 6 / md 8 / lg 12 / xl 16 / 2xl 20（pill 999）。
- **阴影**：卡片 `0 1px 2px`、悬浮 `0 4px 16px`、浮层 `0 8px 32px`（深色下加深）。
- **间距**：8px 基准（4/8/12/16/24/32/48/64）。
- **字体**：系统字体栈（PingFang SC / Microsoft YaHei），正文 14px，标题 -0.02em 字距。

## 三、深色模式

- 通过 `<html data-theme="dark">` 切换，整套 CSS 变量自动翻转；antd 组件经 `darkAlgorithm` 同步。
- 页面级写死浅色（Stocks / StockBrief / Settings / Leads / PetChat / 公众号 H5）已在 `theme.css` 内集中覆盖，无需改动业务 JSX。
- 偏好持久化在 `localStorage['app-theme']`，首次进入跟随系统 `prefers-color-scheme`。

## 四、统一组件（推荐用法）

```jsx
import { PageHeader, StatCard, Toolbar, EmptyState, Skeleton } from '../../components/ui'

<PageHeader
  title="热点情报"
  description="两大板块：股票动态 / 视频号热榜选题池"
  icon={<FireOutlined />}
  actions={<Button type="primary" icon={<PlusOutlined/>}>新建</Button>}
/>

<StatCard
  label="今日热点" value={12} unit="条"
  trend="+8%" trendUp sub="累计 240"
  icon={<FireOutlined />} accent="#5b5bd6"
  spark={[3,5,4,8,6,9,12]} onClick={() => navigate('/hot-topics')}
/>
```

- `StatCard`：KPI 卡，支持趋势箭头、迷你面积图、点击跳转、强调色描边与悬浮上浮。
- `Toolbar`：左筛选 / 右操作的统一工具条。
- `EmptyState` / `Skeleton`：友好的空状态与加载骨架（带 shimmer 动效）。

## 五、交互与适配

- **主题切换**：顶栏右上角日/月图标一键切换，全局平滑过渡。
- **移动端**：≤768px 自动隐藏侧栏，顶栏出现汉堡按钮，点击以 Drawer 抽屉式展开导航；卡片栅格自适应换行。
- **微动效**：页面入场淡入、卡片悬浮上浮、Modal/Drawer 弹入、按钮按压反馈；尊重 `prefers-reduced-motion`。
- **无障碍**：统一 `:focus-visible` 焦点环，语义化结构与 ARIA 标签。

## 六、本地预览

```bash
npm install      # 若依赖未装
npm run dev      # 默认 http://localhost:5173
npm run build    # 生产构建（已验证通过）
```

> 注：页面数据依赖后端 API；无后端时表格/图表显示空状态或加载态，但设计系统、深色模式、导航、主题切换与移动端抽屉均可直接体验。
