# Next.js 迁移计划 / Migration Plan

> Status: **Phase 5c complete** (2026-07-19) — 体验债清偿（resampled-MVO 异步化 + 画像对比/行为偏差页）。

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
| 3b | Retirement Planner（蒙特卡洛 POST + 表单页） | ✅ 2026-07-18 |
| 3c | 客户画像 CRUD 落 SQLite（SQLModel，schema 预留 `user_id`）+ 画像页面 | ✅ 2026-07-18 |
| 4a | AI Advisor 流式输出（SSE）+ 报告库 | ✅ 2026-07-18 |
| 4b | IPS 工作流异步任务化（进程内队列 + 进度推送） | ✅ 2026-07-18 |
| 5a | 部署打磨：镜像瘦身（requirements-api 分离）、compose 健康检查、首启自动迁移、.dockerignore 审计 | ✅ 2026-07-18 |
| 5b | 功能补齐：风险问卷迁移（9 题双轨制 + 自动算分）、IPS PDF 导出 | ✅ 2026-07-18 |
| 5c | 体验债：resampled-MVO 异步任务化、画像对比/行为偏差页 | ✅ 2026-07-19 |
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

## Phase 3b 交付内容（2026-07-18）

**API 新增：**

- `POST /api/retirement/simulate` — 两阶段退休蒙特卡洛（积累期储蓄注入 → 支取期通胀调整提款）。固定 seed=42 保证同参同结果；响应含积累/支取路径图（200 条采样路径 + 5–95 分位带）、存活率、退休时终值分位数（P5–P95 + 均值）、枯竭分析（从未耗尽 / 10 年内耗尽 / 中位耗尽年份，向量化镜像 Streamlit 算法）、储蓄敏感性表（0.5×–2× 六档，各 5000 次模拟）。年龄约束 422 校验。

**Web 新增：**

- `/retirement` 页：滑块表单（年龄三段、收益/波动/通胀）+ 金额输入 + 模拟次数档 → 存活率状态卡（≥85% 稳健 / ≥70% 关注 / 否则风险）+ 双路径图 + 枯竭分析 + 分位数表 + 敏感性表
- 代理泛化：`src/lib/proxy.ts` 的 `proxyPost()` 供所有写路由复用（optimize / simulate 已接入）
- 导航新增"退休规划"

## Phase 3c 交付内容（2026-07-18）

**持久层新增：**

- `api/db.py` — SQLModel + SQLite（`data/wealthpilot.db`，compose 卷挂载持久化）。`ProfileRecord` 表：完整画像存 JSON 列（保持 `asdict(ClientProfile)` 形状，下游 IPS/Advisor 阶段直接消费），名称/年龄/风险等级/更新时间为索引列，`user_id` 预留。`init_db()` 随应用启动幂等建表；`AIWP_DB_URL` 可覆盖（测试注入 tmp 库）。
- `api/migrate_profiles.py` — 旧 JSON 画像导入工具（按 `(name, created_at)` 幂等去重），CLI `python -m api.migrate_profiles` 与端点共用同一实现。

**API 新增：**

- `GET/POST /api/profiles`、`GET/PUT/DELETE /api/profiles/{id}` — 完整 CRUD。请求模型 `ProfilePayload` 镜像 `ClientProfile`（婚姻/税务/优先级 Literal 校验）；风险等级由服务端按 src 规则 `min(能力, 意愿)` 计算（未评估=空串，不误标保守型）；`derived` 响应块（净资产/储蓄率/负债比/综合评分）直接读 src dataclass 属性，+inf 负债比序列化为 null。
- `POST /api/profiles/import` — 从 `data/profiles/*.json` 导入（Streamlit 时代数据），幂等。
- CORS 方法扩展为 GET/POST/PUT/DELETE。

**Web 新增：**

- `/profiles` 页：服务端渲染列表（风险等级彩色 chip）+ 客户端管理组件（新建/编辑表单：基本信息、财务状况、目标动态行编辑器、约束偏好、风险双滑块实时预览等级；删除确认；JSON 导入按钮）。
- 代理层泛化：`proxyJson()` 支持 GET/POST/PUT/DELETE（204 空体特判），`/api/profiles` 三个写路由接入。
- 导航新增"客户画像"。

**已知限制：** 风险问卷 UI（9 题双轨制）后续单独迁移，当前以手动评分代替；画像对比（compare_profiles）与行为偏差分析随 Phase 4 顾问工作流接入。

## 下一步（Phase 6 切入点）

1. **6**：退役 Streamlit——删除 `src/views/`、`src/app.py` 与 streamlit 依赖（`requirements.txt` 与 `requirements-api.txt` 合一）；删除前确认 Streamlit 独有入口无残留引用（旧 JSON 画像导入工具可保留）。
2. 公网认证按产品定位（个人/小团队、本地优先）继续后置。

## Phase 4a 交付内容（2026-07-18）

**API 新增（首个 SSE 端点）：**

- `POST /api/advisor/report/stream` — 流式建议书。按 `profile_id` 从 SQLite 取画像 → 复用 src `generate_advice_stream` 同步生成器（Starlette 线程池迭代，事件循环不阻塞）→ SSE 事件协议：`token`（逐块文本）→ `done`（校验结果 + token 用量）/ `error`。未配置 `DEEPSEEK_API_KEY` 返回 503。
- `GET /api/advisor/status` — API key 配置状态与模型名（前端据此降级提示）。
- 报告库 CRUD：`POST/GET /api/advisor/reports`、`GET/DELETE /api/advisor/reports/{id}` — 复用 src report_storage（与 Streamlit 共享同一 JSON 报告库），列表响应剥离内部文件路径。
- 重构：画像转换逻辑抽出为 `api/profile_convert.py`（payload ↔ asdict dict ↔ dataclass + derived 计算），供 profiles/advisor/IPS 三套路由复用。

**Web 新增：**

- `/advisor` 页：画像下拉（含风险等级）→ 生成 → markdown 逐 token 实时渲染（fetch + ReadableStream 手解 SSE，支持中止）→ done 元信息（token 用量）→ 保存到报告库 → 历史报告查看/删除。
- `Markdown` 组件：react-markdown + remark-gfm，全套 slate/amber 暗色主题元素映射（后续 IPS 页复用）。
- `proxyStream()`：SSE 直通代理（`res.body` 原样转发，零缓冲；错误回退 JSON）。
- 导航新增"AI 顾问"。

**已验证：** 容器内真实 DeepSeek 链路 60s 收到 2356 个 token 事件（约 100KB），逐 token 到达；测试 mock 生成器断言事件协议（token→done 序列、503/404 分支）。

## Phase 4b 交付内容（2026-07-18）

**API 新增（异步任务 + 进度推送）：**

- `POST /api/ips/generate` — 202 创建 IPS 生成任务。LangGraph 工作流以进程内 asyncio 任务运行（按既定决策不引入 Celery/Redis；任务进程级存活，重启即失）；`astream(stream_mode="updates")` 的节点完成事件推入每任务 `asyncio.Queue`；逐节点 delta 合并重建终态，成功后经 src `save_ips` 入库（与 Streamlit 共享 JSON 存储）。
- `GET /api/ips/tasks/{id}/events` — SSE 进度流：`node`（含中文节点标签）→ `done`（document_id/状态/修订轮数）/ `error`。
- 文档库：`GET /api/ips`（列表，document_id=文件 stem）、`GET /api/ips/{id}`（`export_ips_markdown` 渲染全文）；glob 按 id 定位文件，杜绝路径穿越。
- 依赖修复：`pydantic-ai` 钉 `<1.107`（1.107+ 移除了 `ips_agents.py` 使用的 `OpenAIModel`；src 零改动原则下以钉版本解决）。

**Web 新增：**

- `/ips` 页：画像选择 + 最大修订轮数 → 创建任务 → SSE 实时节点进度时间线（节点逐个打勾 + 处理中转圈；修订循环自然展开为多行）→ 完成卡片（直达文档）→ 文档库表格（版本/风险等级/审批状态/修订轮数）→ markdown 全文查看。
- `lib/sse.ts`：`parseSseBlock` + `readSseStream` 抽取共享（advisor 页同步重构复用）。
- `proxyStreamGet()`：GET 型 SSE 直通代理（任务进度流）。
- 导航新增"IPS 生成"。

**已知限制：** 任务为进程内存活——API 重启后任务消失（已生成的 IPS 文档不受影响）；SSE 断连不取消后台任务；PDF 导出（`export_ips_pdf`）留待 Phase 5。

## Phase 5a 交付内容（2026-07-18）

**部署打磨：**

- **镜像瘦身**：新增 `requirements-api.txt`（= 完整 requirements 剔除 streamlit/pytest 及其传递依赖树）；API 镜像 **1.31GB → 1.05GB（-20%）**。审计确认 `import streamlit` 仅存在于 `src/app.py` 与 `src/views/*`（API 导入图不可达）。完整 requirements.txt 保留为开发/Streamlit 环境直至 Phase 6。
- **compose 健康检查**：api 服务内建 `/api/health` 健康检查（python urllib，零新依赖），web `depends_on: service_healthy` —— 启动顺序由"先后"变为"就绪"。
- **首启自动迁移**：`maybe_auto_import()` 挂入 lifespan —— 仅当画像表为空时幂等导入 `data/profiles/*.json`（老用户 clone 后 `docker compose up` 即得既有画像；有数据则完全不动）。
- **.dockerignore 收紧**：`data/` 整体排除（含 `wealthpilot.db`），构建上下文不再随运行数据膨胀。
- 验证：437 测试通过；6 页 0 降级面板；optimize/retirement/ips 冒烟全过（retirement 存活率 0.71 与瘦身前逐位一致）。

**注：** 公网认证按产品定位（个人/小团队、本地优先）继续后置，不计入 Phase 5 范围。

## Phase 5b 交付内容（2026-07-18）

**风险问卷迁移：**

- `GET /api/profiles/questionnaire` — 输出 src 双轨问卷元数据（能力 5 题 + 意愿 4 题，题目与选项均为双语），含每题每选项分值供前端实时预览；服务端保存时仍按 src `compute_*_score` 权威重算。
- **算分优先级**：`payload_to_data` 中某轨答案非空即由问卷派生该轨分数并覆盖手动滑块分（部分作答按已答题平均）；答案为空轨保留手动分 —— 旧画像（无答案）行为完全不变。答案随画像落库，编辑时回填。
- `/profiles` 表单：风险评分区替换为 9 题问卷 UI（选项点选/再点取消，实时显示能力/意愿分与综合等级预览）；问卷加载失败（API 未就绪）降级回手动滑块。

**IPS PDF 导出：**

- `GET /api/ips/{id}/pdf` — 复用 src `export_ips_pdf`（临时目录渲染后回读字节流），`Content-Disposition` 按 RFC 5987 编码（文件名含中文客户端名）。
- API 镜像内置 CJK 字体（WenQuanYi Micro Hei，软链至 `_find_cjk_font` 探测路径）—— slim 基础镜像无 CJK 字体；实测 Debian 的 fonts-noto-cjk 为 CFF 轮廓，fpdf2 2.8.7 嵌入后中文乱码，改用 TrueType 轮廓的文泉驿微米黑（仅 ~5MB）。
- Web：`proxyFile()` 二进制直通代理（`proxyGet` 的 `res.json()` 会毁文件流）；文档库表格与 markdown 查看页各加下载按钮。

验证：442 测试通过（新增问卷端点/算分优先级/部分作答平均/无效答案键/PDF 导出 5 项）；`next build` 通过；容器内端到端冒烟（问卷端点、PDF 真实字节流、字体落位）见提交记录。

## Phase 5c 交付内容（2026-07-19）

**任务框架泛化 + resampled-MVO 异步化：**

- `api/tasks.py` — 4b IPS 任务框架泛化为共享模块：`BackgroundTask`（kind + meta 字典）/ `TaskRegistry` / `sse()` / `stream_task_events()`；ips.py 重构复用（行为不变，4b 测试原样通过）。
- `POST /api/portfolio/optimize/async` — 202 创建优化任务。不需要行情数据的校验（资产 keys、BL 观点非空）同步前置，坏请求立即 422 而非流落事件流；计算拆为 `_prepare_optimize`（取数，IO）+ `_solve_optimize`（求解 + 图表，CPU），两段经 `run_in_executor` 运行，节点事件 `fetch` → `solve` → `done`（携带完整 OptimizeResponse JSON）/ `error`（HTTPException detail 原样透传）。
- `GET /api/portfolio/tasks/{id}/events` — SSE 进度流（复用泛化 drain）。
- 前端 optimizer 页：`method=resampled` 走异步流（任务创建 → SSE → 节点标签实时显示），mvo/BL 保留同步快速路径；结果渲染完全复用。

**画像对比 + 行为偏差：**

- `GET /api/profiles/compare?ids=1,2,…`（2–6 个）— src `compare_profiles` + 逐画像 `identify_behavioral_biases`。src 对比字典按客户名键控，重名会互相覆盖 → 422 拒绝；任一 id 缺失 → 404。
- `/profiles` 页列表加勾选列（上限 6）→「对比所选」→ 对比区块：指标对照表（风险评分/等级/净资产/收入/储蓄率/应急基金/偏差数）、src 双语洞察、逐画像偏差卡片（严重度 chip + 双语描述与建议）。

验证：450 测试通过（新增异步任务生命周期/前置 422/错误事件/404 五项，对比偏差/校验/重名三项）；容器内真实重采样任务经 web 代理跑通（50 次模拟，sharpe 1.094，weight_std 齐全）；问卷作答创建画像 → 派生分数正确（4.4/1.75 → 稳健型）→ 双画像对比返回损失厌恶/风险错配偏差与 4 条洞察；6 页 0 降级面板。
