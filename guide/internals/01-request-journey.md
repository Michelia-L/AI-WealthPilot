# 01 · 一次请求的完整旅程

## 目的与边界

本章不讲任何单一模块的细节。我们沿一次真实的用户操作，在组合优化器页点击「运行优化」，把整个系统从浏览器到量化引擎再回浏览器完整走一遍。读完你应该能建立一张全图，后续每章（量化引擎、数据管道、AI 层、API 壳、前端）都是这张图的局部放大。

选取的场景是 **6 个资产类别、经典 MVO、5 年历史窗口**的同步优化请求，随后再看 Resampled MVO 走的异步任务变体。

## 核心概念 · 三层架构

![架构总览](../diagrams/architecture-zh.svg)

系统的三层职责切分如下，这也是根 `AGENTS.md` 划出的架构红线。

| 层 | 位置 | 职责 | 不允许做什么 |
|---|---|---|---|
| 计算核心 | `src/` | 全部业务逻辑，涵盖优化、数据管道、AI 智能体、图表构建 | 不得 import `api/`（仅有的两个例外见第 4、5 章） |
| 传输壳 | `api/` | FastAPI 路由先做参数校验，再调 `src/`，最后组装响应 | 禁止写业务逻辑 |
| 前端 | `web/` | Next.js 16，RSC 只读取数，变更走同源代理转发 | 浏览器不直连 FastAPI |

有一个事实贯穿全章。**浏览器只和 Next.js 服务器说话**。FastAPI 的地址（`API_ORIGIN`）只存在于 Next 服务端，从不出现在浏览器包里。

## 同步链路 · 九跳

### 第 1 跳 · 表单状态与提交（浏览器）

优化器页的表单状态由 `web/src/components/optimizer/use-optimizer-form.ts` 管理，那是一个约 20 个字段的状态机。点击按钮时，`buildBody()` 把表单折叠成一个 `OptimizeRequest`。这一步做了防御性归一，例如选了 `risk-parity` 方法会强制 `allow_short: false`（引擎层面 ERC 也不支持做空，见第 2 章）。

提交逻辑在 `web/src/components/optimizer/use-optimize-run.ts` 的 `run()`，**方法分流就发生在这里**。`method === "resampled"` 走异步任务（见后文），其余 5 种方法直接 `fetch("/api/portfolio/optimize", {method: "POST", ...})`。注意 URL 用的是同源相对路径，请求发给 Next.js 服务器，不是 FastAPI。

### 第 2 跳 · 同源代理（Next.js 服务端）

`web/src/app/api/portfolio/optimize/route.ts` 只有 5 行。

```ts
export async function POST(request: Request) {
  return proxyPost("/api/portfolio/optimize", await request.json());
}
```

真正的转发在 `web/src/lib/proxy.ts` 的 `proxyJson()`，它做三件事。

1. 从 `wp_locale` cookie 解析出语言，注入 **`X-Locale` 请求头**，后端所有用户可见文案据此双语化；
2. 用 `fetch(`${API_ORIGIN}/api/portfolio/optimize`, {cache: "no-store", ...})` 转发；
3. 上游不可达时返回 502 和本地化文案，前端永远不需要知道 FastAPI 在哪。

`proxy.ts` 共 4 个函数。`proxyJson` 管 JSON 增删改查，`proxyStream` / `proxyStreamGet` 管 SSE 流，**不缓冲**直接 pipe，`proxyFile` 管 PDF 等二进制原样透传，用 JSON 代理会损坏文件。全站 24 个代理路由都是这种 5 到 17 行的薄转发。

### 第 3 跳 · 端点入口与校验（FastAPI）

入口是 `api/routers/portfolio.py` 的 `optimize()`。校验顺序是刻意的 **fail fast**。

1. `_resolve_risk_constraints()` 把 profile_id 解析成客户风险等级的资产组上限，profile 不存在就 404；
2. `_resolve_surplus_raw()` 负责盈余方法的负债输入三通道解析，配置不合法就 422；
3. `_validate_method_constraints()` 要求 BL 必须带观点、risk-parity 禁止做空，违反就 422；
4. 以上全部通过**之后才碰行情数据**。取数是最贵的操作，能被参数校验拦下的请求绝不该打到数据源。

语言解析 `get_request_locale(request)` 排在最前面，它读 `X-Locale` 头，未知或缺失一律回退英文（`api/i18n.py`）。

### 第 4 跳 · 取数（数据管道，带缓存）

取数从 `_prepare_optimize()` 进到 `_fetch_returns()`。

- 15 个资产类别 key 先映射到 ticker（`src/config.py` 的 `DEFAULT_ASSET_CLASSES`）；
- 然后查进程内 TTL 缓存（`api/cache.py` 的 `TTLCache`，价格帧 TTL 300 秒），同一批 ticker 5 分钟内不重复取数；
- 未命中走 `src/data/market_data.py` 的 `fetch_price_history()`，由它做多源路由（CN 资产 tushare → akshare → yfinance 级联，其余 yfinance 直取）、FX 折算、日期对齐，细节见第 3 章；
- 为了防缓存污染，任一 ticker 取回为空或全 NaN 就直接 502 且**不写缓存**，瞬时上游故障不该毒化整个 TTL 窗口；
- 价格帧交给 `compute_returns()` 算简单收益率，列名从 ticker 改成显示名（如 `SPY` → `US Equities (S&P 500)`）。

盈余（LDI）方法有个细节。负债对冲代理（默认 `US_BOND`）会被**并进同一次行情抓取**，共享日期对齐与缓存条目，随后再从收益帧中拆出来。

### 第 5 跳 · 引擎分发

`_solve_optimize()` 按方法分发到 `src/portfolio/optimize_service.py` 的 5 个 runner 之一（`run_mvo` / `run_bl` / `run_cvar` / `run_surplus` / `run_risk_parity`），统一返回七元组 `(optimizer, selected, max_sharpe, min_vol, frontier, random_ports, extra)`。引擎抛出的 `ValueError`（如 LP 不可行）在这里被翻译成干净的 422。

这里有个披露性设计。`selected` 遵守客户风险约束，`max_sharpe` / `min_vol` 两个对照组保持无约束，读者能直观看到约束的成本。

### 第 6 跳 · 优化求解（计算核心）

以 `run_mvo` 为例，请求落到 `src/portfolio/optimizer.py` 的 `PortfolioOptimizer`。

- 构造时定下年化约定，均值 × 252、协方差 × 252（`TRADING_DAYS_PER_YEAR`）；协方差矩阵条件数 > 1e10 时自动对角正则化；
- `maximize_sharpe()` / `minimize_volatility()` 用 scipy SLSQP 求解；`efficient_frontier()` 逐点求解 50 个目标收益点（服务层常量，库默认 100）；`random_portfolios()` 做 Dirichlet 抽样，抽 1000 个组合作散点背景。

数学与六种方法的完整讲解是第 2 章的内容。这里只需要知道，**这一步是纯 numpy/scipy 计算，不碰网络、不碰数据库**。

### 第 7 跳 · 图表构建（Python 端产出 Plotly JSON）

`src/visualization/charts.py` 的 `plot_efficient_frontier()` 与 `plot_allocation_pie()` 把结果画成 Plotly figure，然后 `_fig_json()` 做 `fig.to_json()` 加递归清洗，把 NaN/Inf 改成 None，JSON 无法承载这两个值。

这里有个刻意为之的细节。**盈余方法的前沿不画 CAL 射线**（`risk_free_rate=None` 传入）。盈余不是可按无风险利率缩放的投资，画了会误导。

### 第 8 跳 · 响应组装

`OptimizeResponse`（`api/schemas.py`）负责组装，内容有 selected/max_sharpe/min_vol 三组合、两张图的 JSON、逐资产统计、参数回显（含 `cme_fallback_assets` 披露）、风险约束信息。Pydantic 序列化后沿来路返回，FastAPI 到代理再到浏览器。

### 第 9 跳 · 渲染（浏览器）

结果区 `web/src/components/optimizer/optimizer-results.tsx` 把两张图交给 `web/src/components/plot-chart.tsx`。

- plotly.js 体积大，经**动态 `import()` 懒加载**，服务端永不加载，独立分包；
- 注入「墨金私行」主题默认值（透明底、等宽字体、发丝网格线），**Python 显式设置的值优先**，主题只兜底；
- 删除 Python 侧可能固化的 `layout.width`，让图填满容器；
- `Plotly.react()` 高效更新，组件卸载时 `Plotly.purge()` 防泄漏。

至此 9 跳完成，用户看到有效前沿与资产配置图。

## 异步变体 · Resampled MVO 的任务链路

重采样是分钟级计算，同步 HTTP 会超时，所以走 202 + 任务流的模式。这条链路把系统的另一套机制带出来。

1. **建任务**。`POST /api/portfolio/optimize/async`（`optimize_async()`）先做掉所有不需要行情的校验和**数据库解析**（profile、风险上限），因为后台 executor 线程不允许碰 session。然后 `registry.create()` 落一行 `background_tasks` 表记录，`asyncio.create_task` 起后台任务，返回 **202 + task_id**（12 位 hex）。
2. **进度事件**。任务体 `_run_optimize_task()` 在关键节点 `task.publish()`，依次发出 `node(fetch)` → `node(solve)` → `done{result}`，失败发 `error` 事件。
3. **写穿透持久化**，由 `api/tasks.py` 的 `BackgroundTask.publish()` 实现。每个事件先盖从 1 开始的 `seq` 序号，**先写 SQLite（read-modify-write `events_json`，截断保留最后 500 条）再入内存队列**。这个顺序保证 SSE 消费者看到终态事件时，事件已经持久化。
4. **前端订阅**。`streamTaskEvents()` 打开 `GET /api/portfolio/tasks/{id}/events`（经 `proxyStreamGet` 代理的 SSE），同时把 task_id 存进 sessionStorage。
5. **断线重连**。切页卸载时前端 abort 事件流，但**服务端任务继续跑**。回到页面时凭 sessionStorage 的 task_id 重连，后端 `stream_task_events()` 先按序回放持久化日志并记下 `max_seq`，再 drain 活队列，跳过 `seq ≤ max_seq` 的事件，做到**无缺口、无重复**。
6. **终态回放**。已完成的任务（或服务重启后）重放直接读 SQLite，活队列早被第一个消费者排空，再读会挂起。重启时遗留的 `running` 记录由开机和解（`reconcile_interrupted_tasks()`）置为 `failed`，回放时在尾部合成一条本地化「任务被中断」的 error 事件。

## 横切地图

### 持久化三分

| 存什么 | 存哪 | 谁拥有 |
|---|---|---|
| 客户画像、后台任务记录、LLM 端点设置 | SQLite 三张表（`api/db.py`） | `api/` |
| 报告库、IPS 文档库 | `data/reports/`、`data/ips/` 的 JSON 文件 | `src/agents/*_storage.py` |
| CME 报告缓存 | `data/cache/` 的 JSON 文件（TTL + 参数哈希） | `src/portfolio/cme_cache.py` |

### i18n 两条路径

- **UI 文案**走 cookie `wp_locale`，服务端组件 `getDict()`、客户端 `useT()` 各自取词。字典用 TypeScript 类型强约束，zh 缺 key 编译即失败。
- **API 文案**（错误消息、SSE 事件）走 `X-Locale` 请求头，经 `get_request_locale()` 进 `api/i18n.py` 的 `msg(key, locale)`，那是一张 49 个 key 的双语消息表。

### 缓存一览

`TTLCache` 是进程内线程安全缓存，锁外执行 factory，慢取数不阻塞读者。行情报价 300s、价格帧 300s、无风险利率 3600s、回测 600s、收益率曲线 3600s、基金 AUM 86400s、监控 fleet 86400s（日期进 key，实现每日首访自动重算的懒语义）。

## 设计决策与取舍

- **为什么变更走同源代理而不是浏览器直连？** 不跨域（无 CORS 配置面），不泄露内网地址（`API_ORIGIN` 不出服务端），cookie 里的 locale 还能自动注入。代价是多一跳转发，对本地/局域网部署可忽略。
- **为什么没有 Celery/Redis？** 单用户工作站形态，任务在进程内跑加 SQLite 写穿透持久化，已覆盖断线重连、重启回放的真实需求。引入外部任务队列是把运维负担强加给单机用户。取舍写得很清楚，多进程部署时这套要换共享存储（代码注释明示）。
- **为什么只有 resampled 走异步？** 它是唯一分钟级的方法，其他五种秒级完成，同步 HTTP 更简单。前端分流点集中在 `use-optimize-run.ts` 一处。
- **为什么校验放在取数之前？** 取数最贵（网络 + 缓存粒度），参数错误必须 fail fast。这条顺序还决定了 404/422 的优先级语义。
- **为什么事件持久化失败只记日志不抛出？** DB 坏了不许弄死计算任务本身，持久化是增强，不是命门。

## 已知近似与边界

- **API 路径的优化结果不完全可复现**。服务层构造 optimizer 不传 `seed`，`random_portfolios` 的 Dirichlet 抽样与 resampled 的权重平均每次请求都有细微差异。种子机制（P26）目前只到库级 API。
- **行情数据最长滞后 5 分钟**（价格帧 TTL 300s），无风险利率最长滞后 1 小时。这是缓存语义，不是实时行情。
- **任务注册表是单进程的**。多 worker 跑 uvicorn 时，任务只活在创建它的那个进程里，重连可能 404。当前单进程部署下无影响。
- **持久化事件只保留最后 500 条**（`MAX_PERSISTED_EVENTS`）。超长任务（理论上 IPS 多轮修订）的早期事件会被截断。
- **mean-cvar 的 LP 用完全案例场景**（含 NaN 的日历错位行被整行丢弃，KI-003），与均值-方差路径的 pandas skipna 容忍是两种口径。同一 returns 帧在不同方法下的有效样本不同。

## 自检问题

1. 浏览器里点运行优化，请求发给谁？为什么不让浏览器直连 FastAPI？
2. 同步优化端点的校验为什么按 profile 解析 → 方法约束 → 取行情这个顺序排？颠倒过来会浪费什么？
3. `_fetch_returns` 遇到坏 ticker 为什么抛 502 且刻意不写缓存？
4. 切页再切回来，进度条为什么能续上且不重不漏？`seq` 分别在哪两个地方被比较？
5. 已完成的任务重放为什么从 SQLite 读而不是读内存队列？
6. 服务器重启后，一个状态还是 `running` 的任务记录会经历什么？
7. Plotly 图表的主题样式（深色底、字体）由哪一端注入？Python 侧显式设置和前端默认值谁优先？
8. 为什么异步任务的数据库解析（profile、风险约束）都在端点内完成，而不是后台 executor 线程里？

## 代码入口清单（推荐阅读顺序）

1. `web/src/components/optimizer/use-optimize-run.ts`，前端分流与任务恢复
2. `web/src/lib/proxy.ts` + 任一 `web/src/app/api/**/route.ts`，同源代理
3. `api/routers/portfolio.py` 的 `optimize()` / `_prepare_optimize()` / `_solve_optimize()` / `optimize_async()`，端点全流程
4. `src/portfolio/optimize_service.py`，引擎分发
5. `api/tasks.py`，任务持久化与 SSE 回放（本章含金量最高的文件）
6. `web/src/components/plot-chart.tsx`，渲染终点
