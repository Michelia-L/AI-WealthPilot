# 06 · Web 前端

## 目的与边界

本章讲 `web/`——Next.js 16 前端。它的职责是展示与交互，**业务逻辑零存在**：数字格式化走 `lib/format.ts`，图表 JSON 由 Python 端产出，文案走字典。前端可以崩、可以慢，但绝不能替后端「做决定」。

## 核心概念

### 两种组件，四条通道

App Router 下组件分两种，数据流按此分界：

- **服务端组件（RSC）**：页面主体。只读取数经 `web/src/lib/api/` 直连 FastAPI（`API_ORIGIN` 只在服务端，浏览器看不到）——不跨域、无 CORS。
- **客户端组件**（`"use client"`）：交互工作区。浏览器发起的**变更/流式/下载**必须经 `web/src/app/api/` 的同源代理路由（`lib/proxy.ts`），浏览器永远只跟 Next 服务器说话。

四条通道对应 `proxy.ts` 的四个函数：`proxyJson`（JSON 增删改查，204 特判）、`proxyStream` / `proxyStreamGet`（SSE，**不缓冲**直接 pipe）、`proxyFile`（二进制原样透传——用 JSON 代理会把 PDF 解析坏）。每个代理路由是 5–17 行的薄转发；全部自动注入 `X-Locale` 头。

### RSC 只读通道的容错契约

`lib/api/client.ts` 的 `getJson<T>`：**任何失败（非 2xx、网络异常）都返回 `null`**，调用方渲染降级面板（`ApiOffline`）而不是崩页——API 没起时整个前端是「可读的骨架」。注意它虽名叫 client 实际跑在 RSC；它不能碰 `next/headers`（该模块也在客户端 bundle 里被引用运行时常量），所以需要本地化的 RSC 数据函数走「调用方显式传 locale」模式（参照 `getMonitoringFleetStatus(locale)`）。

## 应用骨架

`app/layout.tsx` 装配全局：

- **四个 next/font**：Geist Sans（正文拉丁）、Geist Mono + IBM Plex Mono（数字/表格等宽）、Fraunces（编辑级衬线标题；中文走 Songti/Noto Serif 回退栈）
- **Provider 嵌套**：`ClientProvider`（全局当前客户）→ `LocaleProvider`（语言）→ `AppShell`（侧栏+顶栏）
- healthBadge（后端健康灯）走 Suspense 插槽——健康检查慢不阻塞首屏

`AppShell`：10 项导航（overview…settings），`NavLink` 的副标签**始终显示另一种语言**（墨金双语品牌层，不是 bug 是设计）；移动端抽屉收起用 React 推荐的「渲染期调整态」模式。

`client-context.tsx` 的「当前客户」是全局概念：选中后注入优化器约束、IPS/顾问默认选中。实现是 `useSyncExternalStore` 包 localStorage：SSR 与首帧水合恒为 null（与服务端一致），水合后读本地值——**没有水合闪烁**。

## 页面地图

12 个路由页（壳 = 服务端取数的薄 page.tsx，交互全在客户端工作区组件）：

| 路由 | 职责 |
|---|---|
| `/` | 总览：行情跑马灯、监控告警横幅、客户速览、最近交付物、模块入口卡 |
| `/market` | 市场仪表盘：URL 驱动筛选（`?period=&categories=`），报价/分析/CME 三区各自 Suspense 流式 |
| `/optimizer` | 优化器壳：服务端取资产宇宙，解析 `?assets=` 与退休 LDI 深链后交给工作区 |
| `/retirement` | 退休规划壳：两阶段蒙特卡洛表单 |
| `/profiles` | 画像列表壳：支持 `?edit=<id>` 深链直接进编辑态 |
| `/profiles/[id]` | 客户枢纽：画像全景 + 派生指标 + 风险双轨分数 + 推荐配置 + 该客户交付物聚合 |
| `/advisor` | AI 顾问壳：SSE 流式生成归 `AdvisorWorkspace` |
| `/ips` | IPS 壳：LangGraph 异步任务工作流归 `IpsWorkspace` |
| `/deliverables` | 交付物中心：建议书+IPS 统一表格，行内 PDF/HTML/MD 导出 |
| `/deliverables/[type]/[id]` | 交付物阅读页：Markdown 渲染 + 导出 |
| `/monitoring` | 组合监控：漂移条/越带徽章/复衡交易/回测区 |
| `/settings` | 设置页：LLM 端点配置（db/env/none 三来源） |

## 数据层

`lib/api/` 按域分 9 个模块（market/portfolio/retirement/profiles/advisor/settings/ips/monitoring/backtest）+ `api.ts` barrel 重导出。类型定义镜像 API 的 Pydantic 模型（如 `OptimizeMethod` 6 值联合）。两个客户端镜像函数（`classifyRiskPreview`/`scoreFromAnswers`）只做实时预览——**服务端保存时重算权威值**，注释明写。

深链契约（`lib/optimizer-link.ts`）：退休页 → 优化器 LDI 通道的 URL 预填。**全有或全无**——只有 `method=surplus&source=retirement` 且 ytr/dy/income 齐全合法才预填，任何残缺整体忽略落回默认。

## 自研 i18n（P22）

没有用 next-intl/react-i18next，自研零依赖方案：

- **字典即 TypeScript 模块**：`dictionaries/en/` 聚合 18 个 namespace；`Dictionary = typeof en`——**类型真源在英文侧**；zh 字典声明为 `: Dictionary`，**缺 key 是编译错误**（tsc 层面强制双语同步）。
- **字典含插值函数**（如 `t.overview.clientAge(age)`），因此**不能作为 RSC props 序列化**——跨边界只传 `locale` 字符串，客户端从 `dictionaries` map 自取。这就是为什么 `locale-context.tsx` 直接在客户端 import 字典。
- **切换**：侧栏切换器 → `POST /api/locale` 写 cookie → `router.refresh()` 整树重渲。locale 由根布局服务端解析后传入，首屏与水合永远一致。
- 两条传输路径不要混：UI 文案走 cookie+字典；API 文案（错误、SSE 事件）走 `X-Locale` 头（第 5 章）。

## 渲染管线

- **`plot-chart.tsx`**：plotly 经动态 `import("plotly.js-dist-min")` 懒加载（服务端永不加载、独立分包）；注入墨金主题默认值（透明底、从 `getComputedStyle` 解析 `--font-mono` 实际字体族、发丝网格线）——**Python 显式设置的值优先**；`delete layout.width` 保证响应式；卸载 `Plotly.purge` 防泄漏。
- **Markdown**：`react-markdown` + `remark-gfm`，组件映射到主题样式（交付物阅读页、AI 报告正文）。
- **SSE 消费**（`lib/sse.ts`）：`fetch + ReadableStream` 手动分块（`\n\n` 分隔、`data: ` 行 JSON.parse）。**故意不用 EventSource——它不能 POST**（头注写明）。
- **思维链区**（`reasoning-section.tsx`）：reasoning 事件弱化样式流式渲染，生成中自动展开、结束自动折叠（FR-001）。

## 优化器工作区深潜

全站最复杂的客户端，拆成两个 hook + 若干面板：

- **`use-optimizer-form.ts`**：约 20 个字段的表单状态机 + `buildBody(): OptimizeRequest`。默认值：资产四件套（US_EQUITY/INTL_EQUITY/US_BOND/GOLD）、period 5y、nSim 200、cvar 0.95、BL τ=0.025 δ=2.5。`buildBody` 内做防御性归一（百分比→小数、`risk-parity` 强制 `allow_short:false`——UI 灰显之外的服务端前最后一道）。
- **`use-optimize-run.ts`**：执行侧。`resampled` 走异步任务（POST → 202 → SSE 进度），其余同步 POST。**挂载时按 sessionStorage 的 task_id 重连事件流**（404 → `TaskGoneError` 静默清句柄）；卸载 abort 流但服务端任务继续跑（第 1/5 章的 server 侧机制在此汇合）。
- 面板分工：`bl-config-panel`（τ/δ、等权/自定义市值权重、动态观点行）、`surplus-config-panel`（三通道；**故意不支持 custom 通胀预设**）、`optimizer-results`（指标瓷贴 + 两图 + 权重表条件列 + 三组合对比 + 联动回测）。
- UI 反直觉点：risk-parity 下 mode/allow-short 控件**不隐藏而是灰显禁用** + hint 文案——比藏起来更可学习。

## 设计系统「墨金私行」

`globals.css` 的 `@theme`（Tailwind v4）是唯一令牌源：

- **色板**：ink 曜石灰阶 5 档（背景层级）、gold 香槟金 6 档（品牌强调）、mist 暖雾 6 档（文本）、jade（涨/成功）/cinnabar（跌/风险）/steel（信息）各 3 档。禁止散落 slate/amber 等旧色值字面量（根 AGENTS.md 规则）。
- **字体三栈**：sans/mono/display，均带中文回退（PingFang/雅黑/Noto/宋体系）。
- **动效**：`ease-luxe`/`ease-silk` 两条缓动 + 6 个动画（fade-up/marquee 42s 跑马灯等）。
- **质感细节**：`body::before` 固定金色穹顶光晕（不随滚动重绘）；`body::after` 是 **z-index 70 的胶片噪点 SVG 层**（opacity 0.032、pointer-events:none）——悬于几乎所有内容之上，做截图/测试时要知道它存在；`.tnum` 数字等宽；细滚动条融入底色。
- **组件库** `components/ui/`：17 个组件条目（Button/Panel/Chip/Table/Icon…）+ barrel；`icon.tsx` 33 个细线图标（`IconName` 联合类型），**禁止 emoji**。

## 工程配置

- `next.config.ts` 极简：只有 `output: "standalone"`——Docker 自包含产物，运行时无 node_modules；`API_ORIGIN` 请求时读取，同一镜像可对任意 API 主机复用。
- `tsconfig.json`：strict、`@/*` 别名、include 覆盖测试文件——所以 `npm run typecheck` 含测试（`next build` 不覆盖）。
- 双测试 runner 分工：vitest（lib 单测 + 组件测试，jsdom）管单元；playwright（e2e 双进程编排：DEMO_MODE 后端 :8300 + `next start` :3300 + 临时 SQLite）管全栈。e2e 只跑 chromium、`workers: 1`（共享单后端单库）。

## 设计决策与取舍

- **为什么自研 i18n 而不用 next-intl？** 需求只有 en/zh 两个 locale + 插值函数；类型真源方案让「缺 key」从运行时错误提前到编译期。零依赖，零运行时库开销。
- **为什么只读走 RSC、变更走代理？** 只读数量大且接受服务端缓存语义；变更/流式要 cookie 注入与错误归一。RSC 直连砍掉了一整层浏览器→代理的只读转发。
- **为什么 `getJson` 永不抛错？** 自托管工作站的常态是「后端没起」——每个页面独立降级比整站白屏好。调用方用「全 null 才算离线」的判断。
- **为什么 plotly 主题在前端注入而不是 Python 端写死？** Python 端只产数据语义；视觉主题归前端——同一 figure 未来可换肤，且 Python 显式设置仍优先（接口契约不被主题覆盖）。

## 已知近似与边界

- `lib/api/profiles.ts` 的 `MARITAL_STATUS_OPTIONS`/`TAX_STATUS_OPTIONS` label 是硬编码中文（不走字典）；`TaskGoneError` 的 message 也是中文——与「文案全走字典」规则的已知例外。
- 客户端镜像函数（风险分级预览）与服务端权威重算并存——预览值可能与保存值不同，以服务端为准。
- `risk_level` 是「English / 中文」双语数据串，UI 按 locale 切一半显示（`localizedRiskLabel`）——数据层而非文案层的双语。
- e2e 用例数不能数 `test(`：smoke.spec 对 10 条路由循环生成，实际执行 17 个用例。
- IPS 的 EWH 港股在优化器宇宙无代理，监控页「在优化器分析」时被**静默跳过**（`OPTIMIZER_KEY_MAP` 注释）。

## 自检问题

1. RSC 只读通道和同源代理通道的分界是什么？为什么变更不能走 RSC？
2. `getJson` 为什么永不抛错？调用方怎么区分「无数据」和「API 挂了」？
3. 字典为什么不能作为 RSC props 传递？跨边界传的是什么？
4. zh 字典缺一个 key 会在什么时候、以什么形式失败？
5. `client-context` 为什么用 `useSyncExternalStore` 而不是 `useState` + `useEffect` 读 localStorage？（提示：水合一致性）
6. 优化器里 risk-parity 的 `allow_short` 有几道防线？（UI 灰显 + buildBody 归一 + API 422 + 引擎构造）
7. SSE 为什么不用 EventSource？
8. `body::after` 噪点层对 UI 测试截图有什么影响？

## 代码入口清单（推荐阅读顺序）

1. `web/src/app/layout.tsx` + `components/app-shell.tsx`——骨架
2. `web/src/lib/proxy.ts` + 任一 `app/api/**/route.ts`——代理通道
3. `web/src/lib/api/client.ts` + 一个域模块（如 `portfolio.ts`）——RSC 数据层
4. `web/src/lib/i18n/`（locale.ts → dictionaries/ → server.ts）+ `components/locale-context.tsx`——i18n 全链
5. `web/src/components/client-context.tsx`——useSyncExternalStore 范本
6. `web/src/components/optimizer/use-optimizer-form.ts` + `use-optimize-run.ts`——工作区状态机
7. `web/src/components/plot-chart.tsx`、`lib/sse.ts`、`lib/task-resume.ts`——渲染与流式
8. `web/src/app/globals.css` + `components/ui/`——设计系统
