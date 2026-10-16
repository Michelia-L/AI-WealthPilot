# 06 · Web 前端

## 目的与边界

本章讲 `web/`，一个 Next.js 16 前端。它只管展示与交互，**业务逻辑零存在**。数字格式化走 `lib/format.ts`，图表 JSON 由 Python 端产出，文案走字典。前端可以崩、可以慢，但不能替后端做决定。

## 核心概念

### 两种组件，四条通道

App Router 下组件分两种，数据流按此分界。

- **服务端组件（RSC）** 是页面主体。只读取数经 `web/src/lib/api/` 直连 FastAPI，`API_ORIGIN` 只在服务端，浏览器看不到，因此不跨域、无 CORS。
- **客户端组件**（`"use client"`）是交互工作区。浏览器发起的**变更/流式/下载**必须经 `web/src/app/api/` 的同源代理路由（`lib/proxy.ts`），浏览器永远只跟 Next 服务器说话。

四条通道对应 `proxy.ts` 的四个函数。`proxyJson` 管 JSON 增删改查，对 204 特判；`proxyStream` / `proxyStreamGet` 管 SSE，**不缓冲**直接 pipe；`proxyFile` 把二进制原样透传，用 JSON 代理会把 PDF 解析坏。每个代理路由都是 5 到 17 行的薄转发，全部自动注入 `X-Locale` 头。

### RSC 只读通道的容错契约

`lib/api/client.ts` 的 `getJson<T>` 在非 2xx 或网络异常时返回 `null`，调用方渲染降级面板。该模块标记为 `server-only`，通过会话辅助函数读取认证头；本地化的域函数仍由调用方显式传入 locale，例如 `getMonitoringFleetStatus(locale)`。客户端可导入的类型和常量与服务端取数模块分开。

客户门户的 `lib/api/client-portal-server.ts` 同时保留数据和 HTTP 状态。文档详情仅在上游返回 404 时显示文档不可用；网络故障或其他错误显示可重试状态，避免把服务暂不可用解释成文档不存在。

## 应用骨架

`app/layout.tsx` 装配字体、`LocaleProvider` 和公共会话入口。未登录或尚未选定工作区时显示登录或工作区选择控件。

- **四个 next/font** 分别是 Geist Sans（正文拉丁）、Geist Mono + IBM Plex Mono（数字/表格等宽）、Fraunces（编辑级衬线标题，中文走 Songti/Noto Serif 回退栈）。
- `app/(advisor)/layout.tsx` 为顾问和管理员装配 `ClientProvider` 与 `AppShell`，顾问页原有 URL 保持不变。后端健康灯通过 Suspense 插槽加载。
- `app/client/layout.tsx` 为客户角色装配独立的 `ClientPortalShell`，并调用 `/api/me` 检查账户关联。客户访问顾问 URL 时转向 `/client`，顾问或管理员访问门户时转向 `/`。布局判断用于界面选择，各 API 仍独立验证权限。

`AppShell` 有 10 项导航（overview…settings），`NavLink` 的副标签**始终显示另一种语言**，这是墨金双语品牌层的有意设计，不是缺漏。移动端抽屉收起用 React 推荐的渲染期调整态模式。

`client-context.tsx` 只属于顾问控制台。它用 `useSyncExternalStore` 管理当前客户 ID，在 sessionStorage 中按用户、组织和浏览器标签页隔离，并从已授权画像列表解析客户。SSR 快照为 null；客户门户不挂载该选择器，读取范围直接由服务端身份关联确定。

## 页面地图

顾问控制台页面位于 `app/(advisor)/`。页面负责服务端取数，交互由工作区组件承担。

| 路由 | 职责 |
|---|---|
| `/` | 总览页。行情跑马灯、监控告警横幅、客户速览、最近交付物、模块入口卡 |
| `/market` | 市场仪表盘。URL 驱动筛选（`?period=&categories=`），报价/分析/CME 三区各自 Suspense 流式 |
| `/optimizer` | 优化器壳。服务端取资产宇宙，解析 `?assets=` 与退休 LDI 深链后交给工作区 |
| `/retirement` | 退休规划壳。两阶段蒙特卡洛表单 |
| `/profiles` | 画像列表壳。支持 `?edit=<id>` 深链直接进编辑态 |
| `/profiles/[id]` | 客户枢纽。画像全景 + 派生指标 + 风险双轨分数 + 推荐配置 + 该客户交付物聚合 |
| `/advisor` | AI 顾问壳。SSE 流式生成归 `AdvisorWorkspace` |
| `/ips` | IPS 壳。LangGraph 异步任务工作流归 `IpsWorkspace` |
| `/deliverables` | 交付物中心。建议书+IPS 统一表格，行内 PDF/HTML/MD 导出 |
| `/deliverables/[type]/[id]` | 交付物阅读页。Markdown 渲染 + 导出 |
| `/monitoring` | 组合监控。漂移条/越带徽章/复衡交易/回测区 |
| `/settings` | 设置页。LLM 端点配置（db/env/none 三来源） |

客户门户位于 `app/client/`，有总览、投资组合、财务目标、风险画像、文档和 AI 六个导航入口。手机端将入口排成两行。文档详情 `/client/documents/[id]` 只展示已发布或已确认阅读的版本，并经同源代理记录阅读确认；未发布修订版和其他客户的文档由 API 拒绝访问。

门户读取 `/api/me/*` 的客户专用 DTO，不展示优化器、原始产物或系统设置。组合页展示已发布 IPS 的建议目标，实际收益、回撤和基准对比当前不可用。目标页与顾问客户详情共用 `goal-funding-cards.tsx`，展示后端按优先级计算的规划预算、覆盖率、年度投入和所需收益率。覆盖率可超过 100%，条形图宽度封顶；金额或期限缺失时显示补充信息提示。实际目标余额、达成概率和情景预测仍待后续实现，前端未增加金融计算。账户关联、发布流程与当前限制见[客户门户说明](https://github.com/Michelia-L/AI-WealthPilot/blob/main/docs/client-portal.md)。

## 数据层

`lib/api/` 按市场、组合、退休、画像、顾问、设置、IPS、监控、回测和客户门户等域拆分。浏览器可用的类型与服务端取数入口分别导出，后者通过 `api/server.ts` 聚合。类型定义镜像 API 的 Pydantic 模型（如 `OptimizeMethod` 6 值联合），客户门户单独镜像客户 DTO。两个客户端镜像函数（`classifyRiskPreview`/`scoreFromAnswers`）只做实时预览，**服务端保存时重算权威值**，注释里写明了这一点。

深链契约（`lib/optimizer-link.ts`）管退休页到优化器 LDI 通道的 URL 预填，规则是**全有或全无**。只有 `method=surplus&source=retirement` 且 ytr/dy/income 齐全合法才预填，任何残缺整体忽略，落回默认。

## 自研 i18n（P22）

这套方案没有用 next-intl/react-i18next，自研，零依赖。

- **字典即 TypeScript 模块**。`dictionaries/en/` 聚合各 namespace，包括门户专用的 `clientPortal`；`Dictionary = typeof en`，**类型真源在英文侧**。zh 字典声明为 `: Dictionary`，**缺 key 是编译错误**，tsc 层面强制双语同步。
- **字典含插值函数**（如 `t.overview.clientAge(age)`），因此**不能作为 RSC props 序列化**。跨边界只传 `locale` 字符串，客户端从 `dictionaries` map 自取。这就是 `locale-context.tsx` 直接在客户端 import 字典的原因。
- **切换** 的流程是侧栏切换器 → `POST /api/locale` 写 cookie → `router.refresh()` 整树重渲。locale 由根布局服务端解析后传入，首屏与水合永远一致。
- 两条传输路径不要混。UI 文案走 cookie 加字典；API 文案（错误、SSE 事件）走 `X-Locale` 头（第 5 章）。

## 渲染管线

- **`plot-chart.tsx`** 里 plotly 经动态 `import("plotly.js-dist-min")` 懒加载，服务端永不加载，独立分包。组件注入墨金主题默认值（透明底、从 `getComputedStyle` 解析 `--font-mono` 实际字体族、发丝网格线），**Python 显式设置的值优先**。`delete layout.width` 保证响应式，卸载时 `Plotly.purge` 防泄漏。
- **Markdown** 用 `react-markdown` + `remark-gfm`，组件映射到主题样式（交付物阅读页、AI 报告正文）。
- **SSE 消费**（`lib/sse.ts`）用 `fetch + ReadableStream` 手动分块，`\n\n` 分隔，`data: ` 行做 JSON.parse。**故意不用 EventSource，因为它不能 POST**（头注写明）。
- **思维链区**（`reasoning-section.tsx`）把 reasoning 事件以弱化样式流式渲染，生成中自动展开，结束自动折叠（FR-001）。

## 优化器工作区深潜

这里是全站最复杂的客户端，拆成两个 hook 加若干面板。

- **`use-optimizer-form.ts`** 是约 20 个字段的表单状态机，外加 `buildBody(): OptimizeRequest`。默认值有资产四件套（US_EQUITY/INTL_EQUITY/US_BOND/GOLD）、period 5y、nSim 200、cvar 0.95、BL τ=0.025 δ=2.5。`buildBody` 内做防御性归一，百分比转小数，`risk-parity` 强制 `allow_short:false`，这是 UI 灰显之外、到达服务端前的最后一道。
- **`use-optimize-run.ts`** 管执行侧。`resampled` 走异步任务（POST → 202 → SSE 进度），其余同步 POST。**挂载时按 sessionStorage 的 task_id 重连事件流**（404 → `TaskGoneError` 静默清句柄）。卸载时 abort 流，服务端任务继续跑（第 1/5 章的 server 侧机制在此汇合）。
- 面板分工如下。`bl-config-panel` 管 τ/δ、等权/自定义市值权重、动态观点行；`surplus-config-panel` 管三通道，**故意不支持 custom 通胀预设**；`optimizer-results` 管指标瓷贴、两图、权重表条件列、三组合对比、联动回测。
- UI 有个反直觉点。risk-parity 下 mode/allow-short 控件**不隐藏，原地灰显禁用**，附 hint 文案，这比藏起来更可学习。

## 设计系统「墨金私行」

`globals.css` 的 `@theme`（Tailwind v4）是唯一令牌源。

- **色板** 分几组。ink 曜石灰阶 5 档管背景层级，gold 香槟金 6 档管品牌强调，mist 暖雾 6 档管文本，jade（涨/成功）、cinnabar（跌/风险）、steel（信息）各 3 档。禁止散落 slate/amber 等旧色值字面量（根 AGENTS.md 规则）。
- **字体三栈** 是 sans/mono/display，均带中文回退（PingFang/雅黑/Noto/宋体系）。
- **动效** 有 `ease-luxe`/`ease-silk` 两条缓动加 6 个动画（fade-up/marquee 42s 跑马灯等）。
- **质感细节** 值得逐个看。`body::before` 是固定金色穹顶光晕，不随滚动重绘；`body::after` 是 **z-index 70 的胶片噪点 SVG 层**（opacity 0.032、`pointer-events:none`），悬于几乎所有内容之上，做截图和测试时要知道它存在。`.tnum` 让数字等宽，细滚动条融入底色。
- **组件库** `components/ui/` 有 17 个组件条目（Button/Panel/Chip/Table/Icon…）加 barrel；`icon.tsx` 提供 33 个细线图标（`IconName` 联合类型），**禁止 emoji**。

## 工程配置

- `next.config.ts` 极简，只有 `output: "standalone"`。产物 Docker 自包含，运行时无 node_modules；`API_ORIGIN` 请求时才读取，同一镜像可对任意 API 主机复用。
- `tsconfig.json` 开了 strict 和 `@/*` 别名，include 覆盖测试文件，所以 `npm run typecheck` 含测试（`next build` 不覆盖）。
- 双测试 runner 有分工。vitest（lib 单测 + 组件测试，jsdom）管单元；playwright 管全栈，e2e 做双进程编排，DEMO_MODE 后端在 8300 端口，`next start` 在 3300 端口，配临时 SQLite。e2e 只跑 chromium、`workers: 1`，共享单后端单库。

## 设计决策与取舍

- **为什么自研 i18n 而不用 next-intl？** 需求只有 en/zh 两个 locale 加插值函数，类型真源方案让缺 key 从运行时错误提前到编译期。零依赖，零运行时库开销。
- **为什么只读走 RSC、变更走代理？** 只读数量大且接受服务端缓存语义；变更和流式要 cookie 注入与错误归一。RSC 直连砍掉了一整层浏览器到代理的只读转发。
- **为什么 `getJson` 永不抛错？** 自托管工作站的常态是后端没起，每个页面独立降级比整站白屏好。调用方按全 null 才算离线来判断。
- **为什么 plotly 主题在前端注入，不在 Python 端写死？** Python 端只产数据语义，视觉主题归前端。同一 figure 未来可换肤，且 Python 显式设置仍优先（接口契约不被主题覆盖）。

## 已知近似与边界

- `lib/api/profiles.ts` 的 `MARITAL_STATUS_OPTIONS`/`TAX_STATUS_OPTIONS` label 是硬编码中文，不走字典；`TaskGoneError` 的 message 也是中文。这是文案全走字典规则的已知例外。
- 客户端镜像函数（风险分级预览）与服务端权威重算并存，预览值可能与保存值不同，以服务端为准。
- `risk_level` 是 English / 中文 这样的双语数据串，UI 按 locale 切一半显示（`localizedRiskLabel`）。双语发生在数据层，不在文案层。
- e2e 用例可能由循环生成，用例清单以 `npm run test:e2e -- --list` 为准。门户测试使用临时数据库中的虚构客户，覆盖跨客户文档访问、草稿隐藏、账户关联、权限撤销和双语导航。
- IPS 的 EWH 港股在优化器宇宙无代理，监控页「在优化器分析」时被**静默跳过**（`OPTIMIZER_KEY_MAP` 注释）。

## 自检问题

1. RSC 只读通道和同源代理通道的分界是什么？为什么变更不能走 RSC？
2. `getJson` 为什么永不抛错？调用方怎么区分无数据和 API 挂了？
3. 字典为什么不能作为 RSC props 传递？跨边界传的是什么？
4. zh 字典缺一个 key 会在什么时候、以什么形式失败？
5. `client-context` 为什么用 `useSyncExternalStore` 而不是 `useState` + `useEffect` 读 localStorage？（提示是水合一致性）
6. 优化器里 risk-parity 的 `allow_short` 有几道防线？（UI 灰显 + buildBody 归一 + API 422 + 引擎构造）
7. SSE 为什么不用 EventSource？
8. `body::after` 噪点层对 UI 测试截图有什么影响？

## 代码入口清单（推荐阅读顺序）

1. `web/src/app/layout.tsx`、`app/(advisor)/layout.tsx`、`app/client/layout.tsx`，公共会话入口与两端布局
2. `web/src/lib/proxy.ts` + 任一 `app/api/**/route.ts`，代理通道
3. `web/src/lib/api/client.ts` + 一个域模块（如 `portfolio.ts`），RSC 数据层
4. `web/src/lib/i18n/`（locale.ts → dictionaries/ → server.ts）+ `components/locale-context.tsx`，i18n 全貌
5. `web/src/components/client-context.tsx`，useSyncExternalStore 范本
6. `web/src/components/optimizer/use-optimizer-form.ts` + `use-optimize-run.ts`，工作区状态机
7. `web/src/components/plot-chart.tsx`、`lib/sse.ts`、`lib/task-resume.ts`，渲染与流式
8. `web/src/app/globals.css` + `components/ui/`，设计系统
9. `web/src/lib/api/client-portal-server.ts` + `components/client-portal/`，客户读取边界、发布版本阅读和受限助手
