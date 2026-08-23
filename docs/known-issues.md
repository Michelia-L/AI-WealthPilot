# Known Issues & Feature Backlog

项目已知问题、待办缺陷与功能需求记录。缺陷以 KI 编号，功能需求以 FR 编号，均按提出顺序排列。

---

## KI-001 · IPS 生成中途切页，回来后界面回到初始状态

**发现日期**：2026-07-26（v0.8.0）　**状态**：已修复（2026-07-26）　**优先级**：中

### 现象

在 IPS 生成页点击「生成」后（AI 生成耗时数十秒至数分钟），若中途切换到其他页面（如「市场」）再返回，页面回到未生成时的初始状态——进度时间线、事件流、完成结果全部消失，用户无法判断任务是否还在运行。

### 根因

**任务本身没有被切断，仍在后台正常运行。** 问题纯在前端状态生命周期：

- 后端：`POST /api/ips/generate` 返回 202 后，LangGraph 工作流以 in-process asyncio task 持续运行，事件写穿透到 `TaskRecord`（api/tasks.py），完成后 IPS 文档正常落盘（`data/ips/`），任务流支持重启回放（P12 基建）。
- 前端：`ips-workspace.tsx` 把 `task_id`、`running`、`steps`、`doneInfo` 全部放在 React `useState`（组件内存）中，未写入 URL / sessionStorage / localStorage。切页即卸载组件，任务句柄随之丢失；返回时重新挂载，无从得知曾有任务在跑。

### 影响

- 生成中的任务最终完成的 IPS 文档会静默出现在文档库/交付物中，用户可能重复点击生成，产生重复文档与重复 LLM 调用（DeepSeek token 浪费）。
- 长任务（多轮修订）期间用户不敢离开页面，工作流被钉死。

### 修复方案（候选）

**MVP（半天）——任务句柄持久化 + 重连：**

1. 点击生成后把 `task_id` 写入 `sessionStorage`（键如 `ips:activeTask`）。
2. 组件挂载时若发现存活句柄：调用 `GET /api/ips/tasks/{id}/events`——终态任务由 DB 完整回放（含 done + document_id），运行中任务接回实时队列续播。
3. 终态后清除句柄。

注意点：运行中任务走实时队列续播时，若旧消费者曾取走部分事件（切页前的进度），这些事件只在 DB 里——严格做法是「先回放 DB 事件、再续实时队列」按序号去重；MVP 可接受偶发的早期事件缺口（切页后无人消费时队列完整，常见路径无损）。同类问题同样存在于优化器异步任务（`/api/portfolio/tasks/[id]/events`），方案应共用。

**完整版（后续）——全局任务中心：**

侧边栏加运行中任务指示（「IPS 生成中 · 评审阶段」），任意页面可见、可点击回到对应工作区并自动重连；与 P12 的 TaskRecord 持久化天然衔接。

### 验证要点（修复后）

- 生成中途切到「市场」再返回：进度时间线从断点续播或从 DB 回放补全。
- 任务完成后返回页面：直接显示完成态与文档链接。
- 重复进入不产生重复生成请求。

### 修复记录（2026-07-26）

按 MVP 方案落地，IPS 与优化器异步任务共用：

- **后端**（`api/tasks.py`）：`publish` 为每个事件打上任务内自增 `seq`（写穿透持久化同步带序号）；运行中任务的事件流改为「先按序回放持久化日志、再续播实时队列并跳过 seq ≤ 已回放最大值的事件」——重连消费者拿到完整序列，不缺不重。终态任务仍纯 DB 回放。新增 3 个测试覆盖断线重连/完成后回放/无 seq 旧事件兼容（`tests/test_api_tasks_persistence.py`）。
- **前端**（`web/src/lib/task-resume.ts` + 两个工作台）：任务启动时把 `task_id` 存入 sessionStorage；组件挂载时检测到存活句柄即自动重连事件流、用同一套事件分发重建进度/结果；done/error 或 404（任务已不存在）时清除句柄；卸载仅断开流，服务端任务照常运行。
- **已验证**：DEMO_MODE 下端到端复现——生成中途切市场页再返回，9 个工作流节点完整恢复并正常显示入库信息；`pytest` 567 全绿、前端 lint/build 通过。


---

## KI-002 · 本地 e2e  smoke 测试依赖网络状态，偶发 page.goto 超时

**发现日期**：2026-08-23（P26 门禁期间）　**状态**：待修复　**优先级**：中

### 现象

本地（有网络但走代理）跑 `npm run test:e2e`，smoke 的路由渲染测试偶发 `page.goto: Test timeout of 30000ms exceeded`——失败测试的页面快照显示内容其实已完整渲染，是 `load` 事件未在 30s 内触发。同一套代码在 CI（无网络）全绿。

### 根因

实测定位（2026-08-23，DEMO_MODE 探针后端 + curl 计时）：

- **DEMO_MODE 只覆盖 LLM 端点**，行情链路（quotes/analytics）在 e2e 中仍走真实 yfinance——「零网络依赖」对行情页不成立。
- **`/market/quotes` 冷启动是唯一长杆**：`get_latest_quotes` 对 17 个 ticker **串行**调用 `yf.Ticker(t).fast_info`（实测合计约 12s），外加 `_attach_sparks` 一次批量下载（约 2s），**冷响应实测 14.2s**；对照 `/market/analytics`（单次批量 `yf.download`）冷 2.0s，暖缓存命中均为毫秒级。
- **挂起机制**：`/market` 页三个数据节走 Suspense 流式渲染，文档流要等全部边界解析完才关闭，浏览器 `load` 事件随之延迟；`page.goto` 默认等 `load`，30s 超时时内容其实已渲染完（失败快照佐证）。`/`（总览）同样引用 quotes 组件，故同病。
- **为何 CI 绿、本地抽签**：yfinance 无显式超时配置；GitHub runner 直连雅虎快（秒级），本地经代理时延抖动大——代理快时 14s 能过 30s 线，慢时越线即失败。进程内存级 TTLCache（`api/cache.py`）导致每次 e2e 运行新进程必冷启动，无法跨进程预热。

### 候选方向

- **A（性能治本，生产同益）**：`get_latest_quotes` 串行 fast_info 改批量/并发（`yf.Tickers` 或线程池），冷启动 14s→2s 级——市场页冷加载本身就是真实性能问题。
- **B（hermetic 治本）**：DEMO_MODE 扩展到行情层，quotes/analytics 回放内置夹具（参照 CME 的 `data/cache/cme` 文件缓存模式），e2e 真零网络且仍覆盖有数据渲染。
- **C（对齐 CI 语义）**：行情链路加离线开关（如 `AIWP_OFFLINE_MARKET=1`），e2e 直接走降级路径；smoke 契约本就是「页面不崩」，但会损失有数据时的渲染覆盖。
- **D（治标）**：playwright webServer 启动后先预热 `/market/quotes` 再开跑，或 smoke 的 `goto` 放宽 `waitUntil`/`timeout`；代理极慢时仍会挂。
- 临时缓解：失败后重跑（同进程缓存即热）。

推荐 A+B 组合：A 修真实性能缺陷，B 让 e2e 彻底脱网。

---

## FR-001 · AI 生成过程实时显示思维链

**提出日期**：2026-07-26　**状态**：已实现（2026-07-26，v0.9.0）　**优先级**：中（体验增强）

### 需求

AI 顾问/调仓建议等流式生成等待数十秒，期间只看着正文逐字出现。希望实时看到模型的思维链（reasoning / thinking）内容—— DeepSeek reasoner 类模型在流式响应里通过 `delta.reasoning_content` 单独下发推理过程——让等待过程可感知、有「AI 在为你工作」的在场感。

### 设计要点

- **后端**：`src/agents/advisor.py` 的流式生成循环目前只读 `delta.content`；扩展为同时读 `delta.reasoning_content`，SSE 协议新增事件类型 `{"type":"reasoning","text":...}`（与现有 `token` 事件并行），终端 done 事件可加 `reasoning_tokens` 计数（`usage.completion_tokens_details`）。`src/agents/rebalance_advisor.py` 同样。PydanticAI/LangGraph 的 IPS 流水线走结构化输出，思维链透出方式不同，MVP 不含 IPS。
- **前端**：报告正文上方加可折叠「思考过程」区，reasoning 事件以弱化样式（mist 色、较小字号）流式渲染，正文照常；生成结束后思维链默认折叠、可展开回看。无推理内容的模型（deepseek-chat 类）该区域不渲染——优雅降级。
- **token 口径**：reasoning tokens 计入账单但不出现在正文，UI 展示时可单列「思考 N tokens」。

### 依赖与注意

- 与 FR-002 联动：自定义端点模型不一定支持 reasoning_content，协议按可选字段设计。
- 演示模式 fixture 可补一份 reasoning 样例流，保持演示路径一致。

### 实现记录（2026-07-26）

- **后端**：`generate_advice_stream` / `generate_rebalance_advice_stream` 改为产出事件 dict——`delta.reasoning_content` → `{"type":"reasoning","text":...}`，`delta.content` → `{"type":"token",...}`；`stream_options={"include_usage": True}` 捕获用量，`done` 事件新增 `reasoning_tokens`（无推理为 0）。路由对旧式字符串产出宽容包装，存量测试缝不动。`stream_advice()` 适配新协议（仅透传正文）。IPS 流水线按设计不含。
- **演示模式**：新增共享 fixture `demo_fixtures/advisor_reasoning.txt`（林晓兰场景思维链），两条 demo 流先回放 reasoning 事件再回放正文，done 带虚构 reasoning_tokens。
- **前端**：新组件 `web/src/components/reasoning-section.tsx`（弱化样式流式渲染、生成中自动展开/结束自动折叠、可手动开关、显示思考 tokens），接入 AI 顾问与调仓建议；无推理内容的模型不渲染（优雅降级）。
- **已验证**：真实 DeepSeek 端到端——思维链实时流入「思考过程」区，596 pytest 全绿。

---

## FR-002 · 设置页：自定义 OpenAI 兼容端点与模型

**提出日期**：2026-07-26　**状态**：已实现（2026-07-26，v0.9.0）　**优先级**：中高（解锁多模型生态）

### 需求

新增「设置」页面。用户输入 OpenAI API 兼容的 endpoint（base_url）与 api key，后端通过兼容协议的 `GET /models` 拉取可用模型列表，用户从中选择要用的模型并保存。此后 AI 顾问 / IPS / 调仓建议全部走用户自定义的端点与模型（DeepSeek、通义、OpenAI、本地 vLLM/Ollama 等任何 OpenAI 兼容服务均可）。

### 设计要点

- **配置解析优先级**：DB 设置 > 环境变量默认。新增 `app_settings` SQLite 表（key-value，`api/db.py`），键 `llm_base_url` / `llm_api_key` / `llm_model`；`src/agents/` 内统一一个 `get_llm_config()` 解析器（advisor、rebalance_advisor、IPS workflow、CME 评论等所有 LLM 消费方共用），`is_api_configured()` 改为感知 DB 设置。
- **端点**：
  - `GET /api/settings/llm` → 当前配置（**api key 脱敏**：`sk-****1234`）
  - `PUT /api/settings/llm` → 保存（base_url / api_key / model；空 key 表示清除回退 env）
  - `POST /api/settings/llm/models` → 用提交的 base_url+key 调 `{base_url}/models` 返回模型 id 列表（超时与错误映射为中文提示）
- **前端**：新 `/settings` 页（侧边栏新条目，sliders 图标已有）：当前配置卡片 → 表单（endpoint、key 密码框）→「拉取模型列表」→ 下拉选择 → 保存；保存后 status 接口联动刷新。零新依赖。
- **安全**：key 明文存本地 SQLite（个人本地应用可接受，README 写明）；任何响应/日志不泄露完整 key；SSE/测试一律 monkeypatch `/models` 请求。
- **测试**：settings CRUD + 脱敏、models 拉取（mock httpx/openai）、解析器优先级（DB 覆盖 env）、is_api_configured 双源感知、422/503 路径。

### 依赖与注意

- 完成后 FR-001 的 reasoning 显示按目标模型能力自动生效/降级。
- 演示模式不受影响（DEMO_MODE 仍优先生效）。
- 注意 IPS 流水线的 PydanticAI 模型构造点与 advisor 的 OpenAI client 构造点不同，二者都要走 `get_llm_config()`，避免只改一半。

### 实现记录（2026-07-26）

- **存储**：`api/db.py` 新增 `app_settings` KV 表（create_all 幂等，零迁移）。
- **解析器**：`src/agents/llm_config.py` `get_llm_config()` 调用时解析，DB > env 逐字段回退；四个 LLM 消费点全部改走它（advisor `_get_client`/`is_api_configured`、rebalance、IPS `_get_model`、IPS 审计元数据）；DeepSeek 专属 `thinking:disabled` extra_body 仅对 deepseek 端点附加。
- **端点**：`GET/PUT /api/settings/llm`（key 脱敏 `sk-****1234`）、`POST /api/settings/llm/models`（10s 超时，连接/认证/其他错误映射中文 502）。
- **前端**：`/settings` 页（当前配置卡 + 端点/Key/模型表单 + 拉取模型列表 + 保存/清除）+ 侧边栏「设置」条目 + 同源代理路由。
- **已验证**：真实 DeepSeek `/models` 拉取 → 保存（db 源）→ 清除（回退 env）全链路 PASS；586+10 pytest 全绿。

---

## Backlog

### ~~P22-i18n-1 · RSC 数据层 `web/src/lib/api.ts` 未注入 `X-Locale`~~（已解决）

**解决方式（2026-07-26）**：`getJson` 增加可选 `locale?: string` 参数并透传 `X-Locale` 头；`getMonitoring` / `getMonitoringFleetStatus` / `getBacktest` 三个受影响函数同步加参，三个 RSC 调用点（`app/page.tsx`、`app/monitoring/page.tsx`、`backtest-section.tsx`）自行 `getLocale()` 传入。zh cookie 用户的监控备注恢复中文。

**为什么不自动读 cookie**：`lib/api.ts` 同时在客户端模块图（`dashboard-controls.tsx`、`retirement-workspace.tsx` 从它导入 `PERIOD_OPTIONS` / `SIMULATION_OPTIONS` 等运行时常量），任何对 `lib/i18n/server.ts`（`next/headers`）的引用——包括 `typeof window` 守卫的动态 `import()`——都会让 Turbopack 把 `next/headers` 打进客户端图，构建直接报错（实测日志佐证）。故 locale 只能由 RSC 调用方显式传入；**新增 RSC 数据函数如需本地化文案，遵循同样的"调用方传 locale"模式**。彻底解法是拆 server-only 数据层（约 15 个 import 改动），暂不必要。

### ~~P22-i18n-2 · 回测/BL 观点/风险约束的 src 异常文案仍仅中文~~（已解决）

**解决方式（2026-08-01）**：按 monitoring 同款模式落地——src 模块内双语表 + `locale: str = "zh"` 参数（zh 保持既有中文逐字，测试里的中文字面断言靠默认值兼容），路由经 `get_request_locale(request)` 透传：

- `src/portfolio/backtest.py`：7 条异常、全部 `notes`（费率截断/费后口径/剔除资产/压力测试跳过）、3 个压力情景名（`STRESS_SCENARIOS` 改为 key + `_STRESS_NAMES` 双语表）、组合/基准标签与费用来源标签双语化；`run_backtest`/`_normalized`/`_drop_sparse_assets`/`_run_stress_scenarios` 加 `locale` 参数。组合回测缓存键补 `:{locale}`（与监控回测既有约定一致）。
- `src/portfolio/views.py`：`ViewProcessor(asset_names, locale)`；3 条 `ValueError` + 3 类警告双语化；未知资产的错误探测从「匹配警告文本」改为直接检测（与 locale 解耦）。`optimizer.apply_views(views, locale)` 透传。
- `src/portfolio/risk_constraints.py`：`caps_for_tolerance(tolerance_level, locale)`。
- 顺带双语化两处英文-only 路由文案：`portfolio.bl_requires_view`、`portfolio.min_assets`（入 `api/i18n.py`）。
- **同日顺带关闭：风险问卷混排**。`src/agents/profiler.py` 的 `RISK_ABILITY/WILLINGNESS_QUESTIONS` 题目/选项改为 `{zh, en}` 结构（删除半截的 `question_en` 残留）；`GET /profiles/questionnaire` 按请求 locale 出单语言文本；前端 `getQuestionnaire(locale)`（RSC 调用方传 locale，`router.refresh()` 后自动重取）。算分只读 option key/score，不受影响。
- 新增测试：问卷 zh/en 端点、backtest 引擎 en（异常/notes/情景名）、监控回测 en 端对端、ViewProcessor 双 locale、caps_for_tolerance en、异步优化 en 422。

### ~~P22-i18n-3 · LLM 相关产物不随 locale 切换~~（已解决 2026-08-22；原条目内容已过期，重写为实际状态记录）

**实际状态**：「生成时定语言」架构在 Phase 22 已落地，本条早年记录的缺口（约 250 条模板串、prompt、SAA 校验文案）实际早已完成或在本轮闭环：

- **文档渲染**：`ips_storage.export_ips_markdown/pdf` 与 `report_storage` 各导出函数均有 `locale="zh"` 参数与双语字典（`_MD_LABELS`/`_IPS_PDF_LABELS`），文档骨架跟随查看时 locale。
- **LLM prompt**：5 个 IPS 角色 + advisor + rebalance 全部有 `_EN` 变体，经 `get_system_prompt`/`_system_prompt`/`_build_messages` 选派；正文语言由生成时 locale 决定（经 `IPSWorkflowState.locale` / 函数参数透传）。
- **本轮（2026-08-22）闭环的剩余缺口**：
  - `ips_workflow.py` 节点异常 `error_message`（硬编码英文，漏进 SSE error 事件）→ 收进 `_SAA_STRINGS` 双语表（`generation_error`/`revision_error`）。
  - `portfolio_recommender` rationale 与 `get_recommended_allocation_text` 加 `locale` 参数，`/api/portfolio/recommendation` 路由透传（zh 档维持既有双语逐字，en 档纯英文）。
  - DEMO_MODE 新增 4 个英文夹具（`*_en` 后缀，占位名 Evelyn Lin），三个 demo 回放入口按 locale 选夹具——修复了「en 界面回放中文报告」的违和。
  - 顺手项：`report_storage.get_export_formats(locale)`、IPS PDF 流动性节货币符号由写死 `¥` 改为按 `currency_policy.base_currency` 推导（对齐 Markdown 行为）、IPS PDF 补 latin-1 降级（对齐 report PDF）。
- **语义契约（测试锁定，维持不变）**：zh 档产物为中英双语，en 档为纯英文；LLM 正文保持生成时语言，文档骨架跟随查看时语言。

**仍按设计保留**（非缺陷，有真实英文需求时再立项）：

- profiler 的其余硬编码双语串：行为偏差（`identify_behavioral_biases`）、画像对比洞察（`_generate_comparison_insights`/`format_comparison_report`）、`format_ratio` 的「∞ (无资产但有负债)」（经 `build_derived` 透出到画像详情页）。风险等级标签（`RISK_LEVEL_LABELS`）作为持久化数据保持双语存储，前端经 `localizedRiskLabel` 按 locale 显示，属既有设计。
- 存储记录（`data/ips/`、`data/reports/`）无语言字段：en 请求查看 zh 生成的文档会得到「英文骨架 + 中文正文」的混合体，属已知取舍；如需「按生成语言渲染」提示再单独立项。
- ~~DEMO_MODE 英文 IPS 夹具的资产类别名为英文，监控/回测的 `_SAA_KEYWORDS` 只覆盖部分英文关键词，en 演示链路下游映射不完整（走既有容错路径，不崩溃）。~~（已解决 2026-08-22，P25：别名表上单源化为 `config.ASSET_CLASS_ALIASES`（双语关键词，有序首中），`monitoring._SAA_KEYWORDS` 由其展平派生、`ips_workflow._fuzzy_asset_match` 改为按类别键命中，en 夹具 SAA 名与 CME 中文名全部命中映射。）

### ~~P24-llm-1 · LLM 调用链缺乏质量与成本治理~~（已解决 2026-08-22，P24）

**问题**：IPS 多智能体工作流（单次最多 ~16 次 LLM 调用）无 eval 基线、无 token 计量、无超时/重试边界、无断连取消、无成本上限——断线或失控的评审-修订循环会静默烧钱。

**解决方式**：

- **eval 基线**：`tests/test_ips_golden_fixtures.py` 金标准夹具（14 条）+ LangGraph 全图假 LLM 测试（pydantic-ai `TestModel`，零网络），质量回归可测。
- **token 计量**：`IPSWorkflowState.llm_usage` 逐节点记录（`_usage_entry`/`_aggregate_usage`），聚合进审计追踪 `generation_metadata.token_usage` 并由 `generate_ips()` 顶层透出。
- **调用边界**：OpenAI client 显式 `LLM_REQUEST_TIMEOUT=600s` / `LLM_MAX_RETRIES=2`（schema 重试仍归 PydanticAI）。
- **断连取消**：advisor/rebalance 流式生成器 try/finally + `stream.close()`，路由 `runner.close()` 经 PEP 380 传播，SSE 断连即停 LLM 消耗。
- **预算闸**：每任务 `LLM_TASK_TOKEN_BUDGET=250K`，`TokenBudgetExceeded` 在 generate/review/revise 三节点调用前检查并 re-raise；`api/routers/ips.py` 专属 SSE error 分支 + i18n `ips.token_budget_exceeded` 双语文案。

### ~~P25-risk-1 · 风险波动带与权益上限双源漂移~~（已解决 2026-08-22，P25）

**问题**：风险等级→目标波动带存在两份来源且数值已漂移——validate_saa 校验与生成器 prompt 一致（4-8/8-12/10-15/13-18/16-25%），而 `portfolio_recommender.RISK_VOLATILITY_MAP` 停留在旧口径（5-8/…/18-22%，且该常量已无消费方）；一致性评审 prompt 的权益上限（30/45/60/75/90）比优化器真实执行的 `risk_constraints.RISK_LEVEL_CAPS`（15/30/50/70/90）松，评审口径与执行口径脱节。

**解决方式**：规范波动带单源化为 `config.RISK_VOLATILITY_BANDS`，validate_saa 校验、推荐器插值、prompt 组合三方共读；删除死常量 `RISK_VOLATILITY_MAP`，`_get_target_volatility` 改为规范带上分段线性插值（段界仍 `RISK_SCORE_BREAKPOINTS`，端点契约 1.0→4%、5.0→25%）；prompt 数字改为 `__VOL_BANDS__`/`__EQUITY_CAPS__` 占位符，在 `get_system_prompt()` 统一注入；一致性评审权益上限收紧对齐执行口径。**有意的行为变化**：推荐器 moderate 目标 0.13→0.125、aggressive 区间 18-22%→16-25%；评审变严、执行不变。

### ~~P26-repro-1 · 运行时版本口径漂移与全局 RNG 未收口~~（已解决 2026-08-23，P26）

**问题**：两套可复现性缺口——其一，运行时版本三方/四方漂移：Python 在 CI 与本地为 3.12 而 `api/Dockerfile` 是 3.11-slim；Node 在 CI 为 20、`web/Dockerfile` 为 22-alpine、本地为 24，且无 `.nvmrc`/`engines`/`.python-version` 锚点。其二，量化引擎的随机路径走 NumPy 全局 RNG 且不可播种：`optimizer.py` 的 `random_portfolios`（Dirichlet）与两条 resampled MVO 路径（multivariate_normal），加上 `charts.py` 蒙特卡洛路径图的展示抽样——同输入无法复现同输出（对照：`simulator.py` 已是 `default_rng(seed)` 规范管道，CVaR 走 HiGHS LP 确定性求解）。

**解决方式**：

- **版本口径收敛**：`api/Dockerfile` → `python:3.12-slim`；CI 两处 `node-version: 24`；`web/Dockerfile` 三处 `node:24-alpine`；新增 `web/.nvmrc`（24）与根 `.python-version`（3.12）；`web/package.json` 加 `engines.node >=22`（底限声明，开发/CI/Docker 实际统一 24）；`@types/node` 升 `^24`（lockfile 同步）；README 双语先决条件同步为 Node.js 22+。
- **RNG 收口**：`PortfolioOptimizer.__init__` 新增 `seed: Optional[int] = None`，持 `self._rng = np.random.default_rng(seed)`；`random_portfolios` 的 Dirichlet、`_resampled_optimize` 与 `resampled_efficient_frontier` 的 multivariate_normal 三处全局调用改走 `self._rng`；`__main__` demo 块改局部 `default_rng(42)`；`BlackLittermanOptimizer` 透传 seed（BL 先验/后验数学本身确定性）；`plot_monte_carlo_paths` 加可选 `seed`。至此 src/ 下全局 `np.random.*` 调用清零。**行为不变**：seed 默认 None 保持既有非复现行为，未透传到 API（如需用户指定种子再单独立项）。
- **复现测试**：`tests/test_advanced_portfolio.py::TestSeededReproducibility`（5 条）——同 seed 两次 resampled 最大夏普/重抽样前沿/随机组合逐位一致，不同 seed 对照不同，默认 None 回归。
- **迁移卫生核查结论**（WSL 迁入验收）：全仓 CRLF 扫描仅 `data/sample/.gitkeep` 一处行尾污染（已还原）；`data/` 仅 `sample/.gitkeep` 被跟踪，`.gitignore`/`.gitattributes`（LF 规范化）覆盖正确；pip 双 requirements 全 pin + npm lockfile/`npm ci` 链路完整，均无需改动。
- **顺带修复**：`web/Dockerfile` 的 `COPY --from=builder /app/public` 在仓库无 `web/public/` 目录时直接失败（潜在缺陷，CI 不跑 docker build 故从未暴露）——补 `web/public/.gitkeep` 兜底，两套镜像实测构建通过。另记录 KI-002（本地 e2e 受代理网速影响偶发 smoke 超时，待修复）。
