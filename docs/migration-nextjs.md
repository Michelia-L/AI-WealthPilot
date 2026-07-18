# Next.js 迁移计划 / Migration Plan

> Status: **Phase 3a complete** (2026-07-18) — 多页导航骨架 + 组合优化器（MVO / Resampled / BL）。

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
| 3a | 多页导航骨架（sidebar layout）+ Portfolio Optimizer（首个 POST 端点 + 表单交互，MVO/Resampled/BL） | ✅ 2026-07-18 |
| 3b | Retirement Planner（蒙特卡洛 POST + 表单页） | ⬜ |
| 3c | 客户画像 CRUD 落 SQLite（SQLModel，schema 预留 `user_id`）+ 画像页面 | ⬜ |
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

## Phase 3a 交付内容（2026-07-18）

**API 新增（首个写端点）：**

- `GET /api/portfolio/asset-classes` — 优化资产宇宙（DEFAULT_ASSET_CLASSES）
- `POST /api/portfolio/optimize` — 组合优化。请求：资产 keys（≥2）、周期（1y–10y）、无风险利率（可空=自动获取）、方法（`mvo` / `resampled` / `black-litterman`）、目标（max-sharpe / min-vol）、做空开关、重采样次数、BL 配置（τ/δ/市值权重/观点列表，观点以资产 key 引用，服务端映射为名称）。响应：选中组合 + 最大夏普 + 最小波动三组权重与绩效、有效前沿图（含 CAL 与随机组合云）、配置饼图、逐资产统计、BL 均衡/后验收益对比、重采样权重波动。行情数据 TTL 缓存 5 min。

**Web 新增：**

- 侧边导航骨架：`layout.tsx` 重构为 sidebar + main 双栏，品牌与 API 健康徽标入驻 sidebar，`NavSidebar`（client，`usePathname` 高亮）驱动多页路由 `/` 与 `/optimizer`
- 同源代理模式：`web/src/app/api/portfolio/optimize/route.ts` —— 浏览器只跟 Next 说话，`API_ORIGIN` 不出服务端（未来所有写操作沿用此模式）
- `/optimizer` 页：完整参数表单（资产 chips、周期/方法/目标 pills、rf 自动/手动、做空开关、重采样滑块、BL 面板含 τ/δ/自定义市值权重/观点编辑器）→ 运行 → 指标卡 + 前沿图/饼图 + 权重明细表（含 BL 均衡/后验列、重采样 σ 列）+ 三组合对比卡

**已知限制：** 重采样（尤其高模拟次数）是分钟级同步计算，目前靠 loading 态承担；Phase 4 异步任务化后改善。

## 下一步（Phase 3b/3c 切入点）

1. `POST /api/retirement/simulate`：`MonteCarloSimulator.retirement_planning(...)` 参数化（年龄/储蓄/收入/通胀/收益/波动/模拟次数），响应 = 积累期/支取期路径图（`plot_monte_carlo_paths`）+ 存活率/分位数/枯竭分析；
2. `/retirement` 页复用 3a 的表单-代理-结果模式；
3. 画像 CRUD：`api/db.py`（SQLModel + SQLite，`user_id` 预留），`ClientProfile` 存为 JSON 列 + 索引字段（名称/年龄/风险等级/更新时间），迁移工具读 `data/profiles/*.json`；
4. `/profiles` 页：列表 + 新建/编辑表单（风险问卷后续单独迁移）。
