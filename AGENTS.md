# AI WealthPilot — Agent Guide

AI WealthPilot 是面向私人财富管理研究与决策支持的开源工作站。核心由 Python 量化引擎、FastAPI 传输层、Next.js 前端，以及基于 LangGraph 的 AI/IPS 工作流组成。LLM 接入采用 OpenAI-compatible 配置；环境变量可使用 DeepSeek，运行时也可通过应用设置覆盖 endpoint / model / API key。

本文件只放全仓长期有效的规则和导航。进入 `web/` 或 `guide/` 工作前，还必须阅读该目录下更具体的 `AGENTS.md`；更深层规则在冲突时优先。

## 工作原则

- **先读后改**：先确认相关代码、测试、配置和最近的局部 `AGENTS.md`，再修改。
- **以代码事实为准**：README、guide、注释或历史 issue 与当前实现冲突时，以可验证的代码和测试为准，并同步修正文档。
- **第一性原理**：从用户目标、系统边界和验证结果出发，不因为旧实现或旧文档存在就默认它仍合理。
- **最小必要改动**：解决当前问题，不顺手扩张范围；公共抽象只有在重复模式已经明确时再引入。
- **提交匿名**：提交信息、PR 描述和解释性文本中不添加 co-author，也不暴露 Agent 身份。
- **文案务实**：README / docs / 用户文案只写可验证事实。避免“机构级、企业级、工业级、极致、赋能、world-class、cutting-edge、seamless”等无法由代码或测试支撑的包装词。
- **维护指令分层**：几乎影响所有任务的规则放这里；只影响某个子树的规则放最近的子目录 `AGENTS.md`。

## 产品与数据边界

- 本项目用于 research、education、technical evaluation 与 decision support。不要把输出描述为持牌投资建议、监管认证、保证收益或已执行交易。
- 组合权重、IPS、再平衡金额和退休模拟均是模型输出或建议性结果；除非代码明确实现，否则不得暗示下单、托管、税务处理或经纪账户同步。
- Demo fixture、synthetic market data、回放报告和样例客户不得用于宣称真实历史业绩、真实客户结果或实时 LLM 质量。
- 用户画像、API key、token、连接串和其他敏感配置不得写入日志、测试夹具、提交内容、截图或用户可见错误信息。新增调试输出前先检查是否会暴露这些字段。
- Live LLM 请求会向配置的模型服务发送完成任务所需的画像或报告上下文；新增 LLM 路径时保持最小数据传递原则，并复用统一配置入口。

## 架构地图

- **`src/`：领域与计算核心。**
  - `src/portfolio/`：组合构建、风险、回测、退休与相关量化逻辑。
  - `src/data/`：市场数据适配与派生数据。
  - `src/agents/`：LLM 顾问、IPS 工作流、报告/IPS 存储与 demo fixture。
  - `src/visualization/`：Plotly 图表构建。
  - 金融模型、量化规则和可复用领域逻辑应放在 `src/`，不要复制到 API 或前端。
- **`api/`：传输、持久化和任务编排。** FastAPI 路由负责验证、调用 `src/`、组装响应；`api/db.py`、`api/tasks.py` 等可以拥有持久化与后台任务生命周期逻辑，但不要在这里重新实现量化/领域规则。Pydantic API 模型集中在 `api/schemas.py`。
- **`web/`：Next.js 应用。** Web 专属的数据访问、i18n、设计系统、测试与 Next.js 规则见 `web/AGENTS.md`。
- **`guide/`：MkDocs Internals 站点。** 写作纪律与构建要求见 `guide/AGENTS.md`。
- **`docs/`：工程记录与被代码/README 引用的资产。** 包括 known issues、迁移记录、IPS reference 和 screenshots；它不是 MkDocs `docs_dir`。

## API 与本地化

- 用户可见的 API 文案使用 `X-Locale`（`en` / `zh`，缺省 `en`）并统一走 `api/i18n.py`；路由里不要新增内联中文错误文案。
- 新增 API endpoint 时，通常同时需要：路由、`api/schemas.py` 中的模型，以及正常/404/422 等相关测试。
- `src/` 中会直接产出用户可见文本的计算函数，应显式接收 locale 或由上层传入，不要读取 Web cookie 或 Next.js 状态。

## LLM 与 Demo 模式

- 所有 LLM 消费方应复用 `src/agents/llm_config.py` 的统一配置解析，不要各自读取不同环境变量或硬编码 provider。
- 未配置可用 API key 时，纯量化功能仍应可运行；需要 LLM 的 live endpoint 应清晰失败，而不是静默伪造结果。
- `DEMO_MODE=1` 的核心演示路径使用确定性 fixture / synthetic market data，避免依赖外部 LLM，并尽量让 UI、优化器、监控和演示报告可复现。
- **不要把 `DEMO_MODE` 当作全局 network-isolation 开关。** 某些辅助数据路径仍可能尝试 provider 请求；若任务要求“完全离线”，必须逐路径验证并在测试中显式阻断网络。

## 常用命令

以仓库中的 `.python-version`、`web/.nvmrc`、`requirements*.txt` 和 `web/package-lock.json` 为版本事实来源，不在本文件重复容易漂移的具体版本号。

```bash
# 后端开发（仓库根目录）
python -m uvicorn api.main:app --reload --port 8000

# 前端开发
cd web && npm run dev

# 全栈 Docker
docker compose up --build
```

## 验证策略

本地验证默认按影响范围选择，完整门禁由 CI 执行。开始前确定相关模块、调用方和风险边界；不要把每个 issue 都当作一次全栈回归。

- **Python / `src/` / `api/` 改动**：跑 `ruff check`、`ruff format --check` 和相关模块及调用边界的 pytest，例如 `python -m pytest -q tests/test_<module>.py`。鉴权/租户隔离、数据库迁移、跨模块核心逻辑或无法可靠界定影响面的改动，本地补跑 `python -m pytest -q`。覆盖率门禁默认交给 CI，不要求每次本地重复收集。
- **Web 改动**：选择相关 Vitest、类型检查、lint 和必要的 build；详细选择规则见 `web/AGENTS.md`。
- **跨层用户流程、same-origin proxy、SSE / background task、locale 切换、断线恢复等改动**：补跑相关 Playwright spec，例如 `cd web && npm run test:e2e -- e2e/locale.spec.ts`；共享会话、代理、导航或广泛用户流程变更跑完整 E2E。Playwright 配置会拉起独立 demo backend 和 web server。
- **`guide/` 内容或 MkDocs 配置改动**：跑 `mkdocs build --strict`；更多写作检查见 `guide/AGENTS.md`。
- **仅 README / 普通 `docs/` / AGENTS 指令改动**：做链接、路径和事实核对；`docs/ips_reference/` 被运行时读取，应按 Python 影响面验证。
- **CI 选择逻辑 / workflow 改动**：运行 `python3 -m unittest discover -s .github/scripts -p 'test_*.py'`，检查 Python lint/格式和 workflow 语法；修改门禁条件时验证失败、取消和跳过分支。完整应用检查交给本次 PR 的 CI。
- 已通过的检查可以复用，除非后续代码、依赖或配置变更使结果失效。只调整测试断言时重跑相关测试；不要无条件重新执行 build、全套 pytest、coverage 或 E2E。有失败或新的影响面证据时再扩大验证范围。

CI 在每个 PR 上运行选择逻辑和汇总门禁：普通文档跳过应用测试，站点内容跑 MkDocs，后端改动跑 Python + E2E，前端改动跑 Web + E2E；混合改动取并集。根目录依赖、CI 配置及未识别路径保守跑全套，main push 和手动运行也跑全套。具体路径规则以 `.github/scripts/ci_scope.py` 为准。

保留 Python coverage、pip-audit、Web production dependency audit 和现有应用检查；pytest 输出最慢测试供后续优化。同一 PR 的过时 CI 自动取消。`CI result` 检查选择逻辑成功且所有选中的 job 成功；配置分支保护时应将其设为 required check，已有应用 job 名称保持不变。命令和版本以 `.github/workflows/ci.yml` 为准。

## PR 交付与 CI 等待

- 一轮 review 中相关修复尽量合并验证后再 push，减少重复 CI。
- 默认交付点是完成相关本地验证并创建/更新 PR。读取一次当前 CI 状态，在交付中列出已跑检查、未跑的完整检查及 CI pending/通过/失败；pending 时结束交付，不反复轮询或为了等结果重复运行本地全套。
- 用户明确要求等待 CI、合并，或当前任务就是修复 CI 失败时，继续跟进到所需结果。长任务使用工具支持的等待机制，避免频繁短轮询；读取失败 job 的相关步骤日志，成功检查只汇总。
- 合并前必须确认最新提交的必需 CI 检查全部通过；本地测试或旧提交的绿灯不能替代该结果。

## Git 规范

- 使用 Conventional Commits，英文主题：`feat:` / `fix:` / `docs:` / `test:` / `chore:` 等；主题保持简洁、描述实际改动。
- **禁止直接 push `main`**。所有改动走 feature branch + PR，CI 全绿后再合并；文档、配置与 AGENTS.md 自身也一样。
- 不为满足形式而把无关改动塞进同一个 PR。若发现旁支问题，记录下来或另开 issue / PR。

## 目录专属规则

- `web/**`：先读 `web/AGENTS.md`。其中包含 Next.js 自动生成规则和 AI WealthPilot 的前端约束。
- `guide/**`：先读 `guide/AGENTS.md`。其中包含 MkDocs 结构、事实核对和 Internals 写作纪律。
