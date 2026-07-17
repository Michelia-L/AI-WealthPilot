# Next.js 迁移计划 / Migration Plan

> Status: **Phase 2 complete** (2026-07-17) — 正式 Market Dashboard（图表平移 + 交互控件）。

## 目标

将 Streamlit 单体 UI 演进为**前后端分离**架构，支撑长期产品化（个人/小团队工具定位，本地优先部署）：

```
web/    Next.js (App Router) + Tailwind — 前端
api/    FastAPI 薄壳 — 只做路由/校验/缓存/序列化，不含业务逻辑
src/    Python 量化核心（优化器、CME、Agents）— 零改动，Streamlit 与新前端共用
```

关键原则：

- **业务逻辑只活在 `src/`**。`api/` 是传输层，永远不放计算逻辑；新增端点 = 包装现有 `src/` 函数。
- **Streamlit 全程可用**，直到 Phase 6 才退役。每个阶段结束都是可工作状态。
- **本地优先**：`docker compose up` 一条命令起全栈；源码直跑 `uvicorn` + `next dev` 同样支持。
- 数据 schema 预留 `user_id` 维度，但多用户认证后置。

## 阶段路线

| Phase | 内容 | 状态 |
|---|---|---|
| 0+1 | 仓库改造 + FastAPI 薄壳（健康检查、行情、无风险利率、CME）+ Next.js 脚手架 + 验证页 + Docker | ✅ 2026-07-17 |
| 2 | Market Dashboard 正式版（图表迁移：plotly `fig.to_json()` → plotly.js；类别/周期控件；Tabs + 归一化） | ✅ 2026-07-17 |
| 3 | Portfolio Optimizer + Retirement Planner（表单 → POST → 图表）；客户画像 CRUD 落 SQLite（SQLModel） | ⬜ |
| 4 | AI Advisor 流式输出（SSE）；IPS 工作流异步任务化（进程内队列 + 进度推送） | ⬜ |
| 5 | 部署打磨：数据迁移工具、公网简单认证、镜像瘦身 | ⬜ |
| 6 | 退役 Streamlit（删除 `src/views/`、`app.py`、streamlit 依赖） | ⬜ |

## Milestone 1 交付内容

- `api/` — FastAPI 应用：
  - `GET /api/health` — 版本与状态
  - `GET /api/market/quotes` — 全资产宇宙最新报价（进程内 TTL 缓存 5 min）
  - `GET /api/market/risk-free-rate` — 动态无风险利率（TTL 1 h）
  - `GET /api/cme?force_refresh=` — 完整 CME 报告（复用引擎自带文件缓存，返回 `cache_status` 溯源标记）
  - 交互文档：`http://localhost:8000/docs`
- `web/` — Next.js 16 脚手架 + 迁移验证页（`/`）：行情卡片、CME 表格、API 健康徽标；服务端组件经 `API_ORIGIN` 直连 API，慢区块 `<Suspense>` 流式渲染
- `docker-compose.yml` + `api/Dockerfile` + `web/Dockerfile`（standalone 输出）

## 日常开发命令

```bash
# 后端（项目根目录）
uvicorn api.main:app --reload --port 8000

# 前端（web/ 目录）
npm run dev        # http://localhost:3000

# 全栈（推荐）
docker compose up --build

# Streamlit 旧 UI（迁移期间保持可用）
streamlit run src/app.py

# Python 测试
pytest tests/
```

## 已确认的技术决策

| 决策点 | 选择 | 理由 |
|---|---|---|
| 前后端通信 | Server Components 经 `API_ORIGIN` 服务端直连 | 无 CORS、无构建期环境烘焙；浏览器只跟 Next.js 说话 |
| API 缓存 | 进程内 `TTLCache` + CME 文件缓存 | 单机够用；多进程部署时再换 Redis |
| 前端缓存 | 不在 Next 层缓存（`no-store`），新鲜度归 API 层管 | 单一事实来源，避免双层缓存不一致 |
| 图表 | `fig.to_json()` + 自研薄包装（`plotly.js-dist-min` 动态 import） | 现有 Plotly 图表 1:1 平移；避开 react-plotly.js 对 React 19 的 peer 依赖问题 |
| 数据库 | SQLite + SQLModel（Phase 3 引入） | 个人/小团队正解；schema 预留 `user_id` |
| 长任务 | 进程内异步队列 + SSE（Phase 4） | 不引入 Celery/Redis |
| 配色 | 红涨绿跌（中国习惯） | 目标客户为中国投资者 |

## Phase 2 交付内容（2026-07-17）

**API 新增：**

- `GET /api/market/universe` — 资产宇宙静态元数据（名称/类别/币种/颜色）
- `GET /api/market/quotes?tickers=` — 支持逗号分隔过滤，响应内嵌币种符号与颜色（前端免二次请求）
- `GET /api/market/analytics?period=&tickers=` — 聚合分析包：价格走势图 + 相关性热力图（`fig.to_json()` 原样透传，numpy 数组以 base64 typed-array 编码）+ 风险统计表（年化收益/波动、夏普、最大回撤、日 VaR95），TTL 缓存 5 min

**Web 新增：**

- `PlotChart` 客户端组件：`plotly.js-dist-min` 动态 import（SSR 安全、自动代码分割），`Plotly.react` 增量更新
- 仪表盘控制条：类别 chips + 周期 pill（状态存 URL query，可分享，服务端渲染不破坏）
- 分析 Tabs：价格走势（客户端 base-100 归一化——直接解码 bdata typed array，零重取数）/ 相关性热力图 + 解读 / 风险统计表
- 报价卡按类别分组，移植 Streamlit 版币种小数位规则与绿涨红跌约定

## 下一步（Phase 3 切入点）

1. `POST /api/portfolio/optimize`：请求体 = 资产选择 + 参数（回看窗口、无风险利率、约束、BL views），响应 = 权重 + 绩效 + 有效前沿/CAL 图表 JSON（复用 `plot_efficient_frontier`、`plot_allocation_pie`）；
2. `POST /api/retirement/simulate`：蒙特卡洛参数 → 路径分位数 + `plot_monte_carlo_paths` 图表 JSON；
3. 客户画像 CRUD：SQLModel + SQLite（schema 预留 `user_id`），替换 `data/profiles/*.json` 文件存储；
4. 前端新增对应页面与侧边导航（多页面结构从此开始）。
