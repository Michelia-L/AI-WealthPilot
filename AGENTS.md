# AI WealthPilot — Agent Guide

面向私人财富管理的 AI 顾问工作站：量化组合引擎（MVO / Resampled / Black-Litterman / Mean-CVaR / LDI 盈余优化 / 风险平价 ERC / GBM 蒙特卡洛；预期收益可切换历史样本 / CME 引擎口径 `expected_return_source`，BL 方法下该口径作为先验）+ LangGraph 多智能体 IPS 流水线 + DeepSeek 顾问智能体。

## 工作原则

- **第一性原理思考**：从真实需求、代码事实和验证结果出发；目标不清楚时先与用户讨论，不凭假设推进。
- **先读后改**：修改代码前，阅读相关代码与最新约束，遵循目录树中最近的 AGENTS.md（子目录的更具体约定优先）。
- **提交匿名**：提交信息不添加任何 co-author 署名；提交信息、PR 描述与任何解释性文本中不暴露 Agent 身份。
- **指令维护**：影响几乎所有任务的硬规则，更新到根 AGENTS.md；只影响特定目录的规则，更新到最近的子目录 AGENTS.md；指令更新保持聚焦，并有代码事实支撑。

## 架构约定（最重要）

- **`src/` 是计算核心**：量化引擎（`src/portfolio/`）、数据管道（`src/data/`）、AI 智能体（`src/agents/`）、图表构建（`src/visualization/`）。业务逻辑只能在这里。
- **`api/` 是薄传输壳**：FastAPI 路由只做参数校验、调用 `src/`、组装响应；禁止在路由里写业务逻辑。Pydantic 模型集中在 `api/schemas.py`。用户可见文案按请求头 `X-Locale`（en/zh，缺省 en）双语化：统一走 `api/i18n.py` 的 `msg(key, locale)`（zh=既有中文逐字），路由用 `get_request_locale(request)` 解析；路由里禁止内联中文。
- **`web/` 是 Next.js 前端**：只读数据走服务端组件 → `web/src/lib/api.ts`（经 `API_ORIGIN` 直连 FastAPI）；浏览器发起的变更/流式请求必须经 `web/src/app/api/` 的同源代理路由（`web/src/lib/proxy.ts`），不跨域、不暴露内网地址。
- **i18n（phase 22）**：locale 由 cookie `wp_locale`（`en`/`zh`，新访客默认 en）决定，侧栏切换器经 `POST /api/locale` 写 cookie 后 `router.refresh()`。UI 文案集中在 `web/src/lib/i18n/dictionaries/{en,zh}/`（namespace 分文件 + index 聚合；zh 声明为 `Dictionary` 类型，**缺 key 编译即失败**——新增文案必须双语同步）。服务端组件用 `getDict()`/`dictionaries`（另一语言用 `altLocale` 保留双语品牌副标签），客户端组件用 `useT()`。传输层：`proxy.ts` 四个函数自动注入 `X-Locale`；`lib/api.ts` 因在客户端模块图不能碰 `next/headers`，需要本地化文案的 RSC 数据函数走「调用方显式传 locale」模式（参照 `getMonitoringFleetStatus(locale)`）。
- **持久化**：客户画像与后台任务记录（SSE 事件写穿透，重启后和解 + 可回放；运行中任务断线重连先回放持久化日志、再按 `seq` 去重续播，见 `api/tasks.py`）在 SQLite（`api/db.py`），同库还有 `app_settings` 键值表（FR-002 的 LLM 端点配置 base_url/api_key/model）；报告 / IPS / CME 缓存是 `data/` 下的 JSON 文件存储（`src/agents/*_storage.py`）。

## 常用命令

```bash
# 后端（仓库根目录）
python -m uvicorn api.main:app --reload --port 8000

# 前端
cd web && npm run dev          # :3000

# 测试与质量门禁（改动后必跑）
python -m pytest -q            # 全套 Python 测试
cd web && npm test             # 前端 Vitest（lib 单测 + 组件测试）
cd web && npm run lint && npm run build

# 全栈 Docker
docker compose up --build
```

## 前端设计系统（「墨金私行」）

- 令牌集中在 `web/src/app/globals.css`（Tailwind v4 `@theme`）：ink/gold/mist/jade/cinnabar/steel、`font-display`、`tnum`、`ease-luxe`。禁止散落 `slate/amber/emerald/rose` 等旧色值字面量。
- 组件库在 `web/src/components/ui/`（Button、Panel、Chip、Table、Icon…），新页面优先复用；图标用 `ui/icon.tsx` 的细线图标，禁止 emoji。
- 图表经 `web/src/components/plot-chart.tsx` 渲染（主题层已注入），Python 端输出 Plotly JSON。
- **Next.js 16 与训练语料有破坏性差异**：动路由/字体/数据 API 前先查 `web/node_modules/next/dist/docs/`（见 `web/AGENTS.md`）。async request APIs（`params`/`searchParams` 是 Promise）。

## Python 约定

- 文档字符串/注释用英文；面向用户的错误文案（HTTPException detail、SSE 事件 message）中英双语，新增一律进 `api/i18n.py` 消息表走 `msg()`（src/ 计算函数产出的文案用 `locale: str = "zh"` 参数透传，参照 `src/portfolio/monitoring.py`）。
- 测试模式：外部调用（yfinance、LLM、FRED）一律 monkeypatch；API 测试用 `tests/conftest.py` 的 `client` fixture（默认带 `X-Locale: zh`；`bare_client` 无头=英文路径）；SSE 解析复用 `tests/test_api_advisor.py` 的 `_parse_sse`。
- 新增端点：路由 + `api/schemas.py` 模型 + 测试（404/422/正常链路）三件套。

## Git 规范

- Conventional Commits，英文：`feat:` / `fix:` / `docs:` / `test:` / `chore:`，主题行小写，阶段功能标注 `(phase N)`。
- 提交前确认：`python -m pytest -q`、`cd web && npm test`、`cd web && npm run lint && npm run build` 全绿。
- CI（`.github/workflows/ci.yml`）在 push/PR 时跑同样的两道工序（pytest 带 `--cov-fail-under=87` 覆盖率门禁与 pip-audit CVE 扫描）；推送前本地先过一遍。

## 环境

- `.env` 配 `DEEPSEEK_API_KEY`（AI 顾问 / IPS 必需）、`FRED_API_KEY`（可选，无风险利率首选源）、`TUSHARE_TOKEN`（可选，A 股映射指数与中债收益率曲线的付费主干源，未配置时自动降级 akshare / yfinance）。
- LLM 端点可在 /settings 页面改用任意 OpenAI 兼容服务：保存进 `app_settings` 表后按字段覆盖 env 默认（DB 非空值优先，见 `src/agents/llm_config.py` 的 `get_llm_config()`，所有 LLM 消费方统一走它）；清空 API Key 即删行回退 env。
- 未配置 DeepSeek key 时量化功能照常可用，LLM 端点返回 503；除非 `.env` 设 `DEMO_MODE=1`（phase 20 演示模式），此时三个 LLM 端点无条件回放 `src/agents/demo_fixtures/` 的虚构样例（`src/agents/demo_mode.py`），零网络调用，启动时若画像表为空还会种子一个虚构客户「林晓兰」。
