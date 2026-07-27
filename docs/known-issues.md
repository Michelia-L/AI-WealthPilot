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

### P22-i18n-2 · 回测/BL 观点/风险约束的 src 异常文案仍仅中文

step 3 按授权范围只双语化了路由静态文案、SSE 消息与监控（`src/portfolio/monitoring.py`）备注。以下经 `detail=str(e)` 透出的 src 异常仍为中文（en 请求的 422/502 会带中文）：

- `src/portfolio/backtest.py`：`run_backtest` 的 6 条 `InsufficientDataError`/`ValueError`、约 10 条 `notes`、3 个压力测试情景名（"2020 新冠"等）与基准名"基准"。
- `src/portfolio/views.py`：BL 观点校验 7 条 `ValueError`（经 `_run_bl` → 422）。
- `src/portfolio/risk_constraints.py`：`caps_for_tolerance` 的"无法识别的风险等级"（经 `_resolve_risk_constraints` → 422）。

修复方向：与 monitoring 相同的模式——函数加 `locale: str = "zh"` 参数、模块内双语表，路由透传；注意 `test_backtest.py`/`test_black_litterman.py` 有大量中文字面断言，靠默认值保持兼容。

另外 LLM 相关产物按设计不随请求 locale 切换：IPS/报告文档（`src/agents/ips_storage.py`、`report_storage.py` 的 Markdown/PDF 渲染，约 250 条中文模板串）、LLM prompt（`ips_agents.py`、`advisor.py`、`rebalance_advisor.py`）、`src/agents/ips_workflow.py` 的 SAA 校验 error_message（约 15 条，会作为 SSE error message 透出）。如产品要求 en 用户全英文，需要单独立项（涉及文档生成语言策略，不只是传输层）。
