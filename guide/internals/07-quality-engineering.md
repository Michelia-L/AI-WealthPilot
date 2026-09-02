# 07 · 质量与可复现性工程

## 目的与边界

收官章讲质量层，`tests/`、CI、Dependabot、e2e、版本钉、容器都在这一层。这一层**不产任何业务功能**，它决定的是一件事，改了代码敢不敢合。本章要回答的是，这个项目的质量具体是哪几道闸门，各自防什么。

## 核心概念 · 质量哲学三条

1. **门禁只硬在 CI**。本地开发要快（`pytest -q` 不带覆盖率参数直接跑），强制门在 `.github/workflows/ci.yml`，本地命令是 CI 的人工子集。
2. **测试零网络**。yfinance、LLM、FRED、tushare、akshare 一律打桩，e2e 靠 DEMO_MODE 夹具回放 + 合成行情，同样零网络。测试套件在任何网络环境下结果一致。
3. **外部调用一律 monkeypatch**。不真实调用外部服务，连开发者本地 `.env` 里的真实 token 也会被 conftest 主动隔离（见下）。

## 测试套件（`tests/`）

### 分域地图

53 个 `test_*.py`、968 个测试函数（`grep -c "def test_"` 实测；pytest 实际收集 991 条，参数化会展开）。按域划分如下。

| 域 | 文件数 | 覆盖对象 |
|---|---|---|
| API 路由层（`test_api_*`） | 23 | 经 `TestClient` 打端点，外部依赖全打桩 |
| `src/portfolio` 量化引擎 | 14 | 纯计算单元的数值/边界断言 |
| `src/data` 数据管道 | 8 | 网络层全 monkeypatch，测级联降级与解析 |
| `src/agents` AI 智能体 | 7 | LLM 调用打桩；golden fixtures 校验回放夹具 |
| `src/visualization` | 1 | Plotly JSON 结构断言 |

最大的几个文件是 `test_portfolio.py`（1190 行/62 例）、`test_advanced_portfolio.py`（1054/57）、`test_cme_engine.py`（994/40）、`test_ips_workflow.py`（979/32）、`test_black_litterman.py`（937/55）。

### conftest 的 autouse 隔离（`tests/conftest.py`）

`isolate_storage_dirs`（autouse，每个测试自动执行）做五件事。

1. 三个存储目录（profiles/reports/ips）monkeypatch 到 `tmp_path`，测试永不污染开发者真实的 `data/`。
2. **两处 `TUSHARE_TOKEN` 清空**。`tushare_provider` 和 `yield_curve` 各自持有一份 import 时绑定的引用，必须分别 patch。开发者 `.env` 里的真实 token 不会泄漏进测试，付费接口绝不被真调。
3. `akshare_provider.is_available` 强制 False（可选依赖默认关闭）。
4. `DEMO_MODE` 强制 False。开发者 `.env` 若设了 `DEMO_MODE=1`，不会把整个套件静默切到夹具回放路径。
5. `api.db.engine` 指向 tmp SQLite（LLM 设置的 app_settings 表读它，防开发者真实的已存端点配置泄漏进测试）。

**`client` / `bare_client` 双 fixture**。`client` 默认注入 `X-Locale: zh`，让 i18n 改造（P22）之前的存量中文断言原样通过；`bare_client` 无头，走 API 默认英文路径。`_make_client` 里 engine 被 patch 两次（autouse 的 `unit.db` + `_make_client` 的 `test.db`），用 `client` 的测试以后者为准。原因在 `api/tasks.py` 的任务持久化直接解析 `api.db.engine`，不走依赖注入，所以两处都要指到同一个 tmp 库。

### monkeypatch 三模式

全套件 250 处 `monkeypatch.setattr`（37 个文件），有三种典型用法。

- **属性级替换**，如 `monkeypatch.setattr("api.routers.advisor.generate_advice_stream", fake)`。注意打的是 **router 模块里已导入的名字**，不是 `src.agents.advisor` 的原函数。
- **`unittest.mock.patch` 构造数据**，如手工构造 MultiIndex DataFrame 模拟 `yf.download` 返回。
- **假模块注入**，`test_yield_curve.py` 用 `sys`/`types` 构造伪模块模拟 tushare 的 `yc_cb` 接口（该接口需单独授权，绝不真调）。

SSE 解析有共享 helper `_parse_sse`（`test_api_advisor.py`），按 `data: {json}\n\n` 分块，新增 SSE 端点测试复用它。`tests/` 没有 `__init__.py`，但存在跨测试文件的 import，靠的是从仓库根以 `python -m pytest` 运行的命名空间包语义（用裸 `pytest` 入口的可用性未验证，别这么跑）。

## CI 三 job（`.github/workflows/ci.yml`）

push 到 main 与所有 PR 触发，三个 job 并行。

| Job | 步骤链 | 防什么 |
|---|---|---|
| **python** | setup 3.12（pip 缓存 key 到两个 requirements）→ 先升 pip/setuptools（避免 pip-audit 审计到解释器自带工具链）→ 装 dev 依赖 → **ruff check → ruff format --check（lint 先行 fail fast）** → 装 CJK 字体 → pytest 带覆盖率门 → 传 coverage.xml → pip-audit | 代码风格、回归、覆盖率退化、依赖 CVE |
| **web** | setup-node 24（npm 缓存 key 到 lockfile）→ `npm ci` → lint → typecheck → vitest → build | 前端 lint/类型/单测/构建 |
| **e2e** | 双环境 setup → `npm ci` → `npm run build` → 装 chromium → `npm run test:e2e`（失败时传 playwright-report） | 全栈集成回归 |

这里有两个要点。

- **CJK 字体是 CI 与 Docker 的隐式契约**。python job 装 `fonts-wqy-microhei` 并软链冒充 `NotoSansCJK-Regular.ttc`，与 `api/Dockerfile` 完全同构（IPS PDF 测试渲染中文，fpdf2 对 Debian 正版 Noto CJK 的 CFF 轮廓渲染乱码）。**改任何一边都要同步另一边**。
- **覆盖率门只在 CI**。`--cov-fail-under=87`，注释写明口径，实测 92%（2026-08 的 pin 集）减 5pp 余量，日常改动不踩线，真实退化逃不掉。本地 `pytest -q` 不跑覆盖率。

## Dependabot 与 pip-audit 的分工

`dependabot.yml` 管三个生态，pip（`/`）、npm（`/web`）、github-actions（`/`），都是**周更**。注释明写分工，**pip-audit 负责 gate 住有 CVE 的 pin，Dependabot 负责有修复版本时递 bump PR**，一个挡风险，一个送修复。bump PR 同样过全套 CI 门禁。

## e2e 编排（`web/playwright.config.ts`）

`webServer` 数组拉起**两个进程**。

1. `python -m uvicorn api.main:app --port 8300`，env 注入 `DEMO_MODE=1`（LLM 回放夹具 + 合成行情，零网络）和 `AIWP_DB_URL`，后者指向 `os.tmpdir()` 下带时间戳的 SQLite（**每轮新文件**，aborted run 的残留 DB 绝不泄漏状态）。
2. `npm run start -p 3300`，**生产构建**（需先 `npm run build`），env 注入 `API_ORIGIN` 指向 8300。

`workers: 1` + `fullyParallel: false`，共享单后端单 SQLite；`reuseExistingServer: !CI`，本地可复用已起的服务。后端用裸 `python` 拉起，所以本地跑 e2e 前必须先 `source .venv/bin/activate`（WSL/Linux 的坑，AGENTS.md 有记）。

有个反直觉的点，e2e 用例数不能数 `test(`，8 个声明实际跑 **17 个用例**（`smoke.spec.ts` 对 10 条路由循环生成）。

## 版本钉与行尾

- **Python 3.12 四处一致**。`.python-version`、ruff `target-version = "py312"`、CI setup-python、`api/Dockerfile` 的 `python:3.12-slim`。
- **Node 24 三处一致**。`web/.nvmrc`、CI setup-node、`web/Dockerfile` 的 `node:24-alpine`。`web/package.json` 的 `engines: >=22` 只是**下界**声明（开发/CI/Docker 实际统一 24）。
- **`.gitattributes`** 里 `* text=auto eol=lf` 做全平台 LF 归一化，另列二进制白名单（pdf/png/ttc/db 等），WSL 内 git 配 `core.autocrlf=false` 与之配套。
- **依赖锁定的不对称**（P26 结论）。Python 全量 `==` 精确 pin，**无 lock 文件**，锁定语义由 pin + CI pip-audit 承担；Node 大多 `^` 范围，真正锁定靠 `package-lock.json` + `npm ci`。两套模式各自自洽，不要互相套用。

## 容器

`docker-compose.yml` 双服务，有几个决策值得讲。

- **双端口绑 127.0.0.1**。注释明写原因，API 无任何鉴权，绝不能暴露到 LAN；要暴露须 override 并先加鉴权。这条安全边界是显式决策。
- `./data:/app/data` 卷让 CME 缓存/画像/报告留在宿主机，不烘进镜像。
- `web` 的 `API_ORIGIN=http://api:8000` 走 compose 内网；`depends_on: api: service_healthy`。
- `api/Dockerfile` 的构建上下文是仓库根（import `src/`），先装 CJK 字体（见 CI 节契约），`ENV PYTHONPATH=/app`。
- `web/Dockerfile` 走三阶段（deps/builder/runner），runner 只吃 standalone 输出 + static + public，运行时无 `node_modules`，`node server.js` 启动。

## 设计决策与取舍

- **为什么覆盖率门只硬在 CI？** 本地迭代要快，门放 CI 既强制执行又不拖慢本地循环。代价是可能本地绿但 CI 红，可以接受，因为 CI 是合入前最后一道。
- **为什么 e2e 单 worker？** 两个进程共享一个 demo 后端 + 一个 SQLite，并行的收益小于状态竞争的风险。
- **为什么 Python 不用 lock 文件/uv？** 20+4 个 pin 的规模下，`==` pin + pip-audit + Dependabot 的组合已经提供了可复现、CVE 防护和更新通道，再引入 lock 工具，复杂度换不到对应收益（P26 评估结论）。
- **为什么 e2e 跑生产构建而不是 dev server？** dev 的编译行为与生产不同（lazy 编译、错误页差异），e2e 要验的是用户真实拿到的东西。

## 已知近似与边界

- 本地 `pytest` 不带覆盖率门（只 CI 有），本地全绿不等于覆盖率达标。
- `tests/` 不是 Python 包（无 `__init__.py`），跨文件 import 依赖从仓库根以 `python -m pytest` 运行。换目录或用裸 `pytest` 入口的可用性未验证。
- e2e 历史上曾有冷启动抽签失败（KI-002，quotes 串行取数超时），已通过并发化 + DEMO_MODE 合成行情根治，台账有完整记录。
- 覆盖率 87% 是按实测 92% 减 5pp 人为设定的，不是行业惯例值。

## 自检问题

1. conftest 的 autouse fixture 清了几样东西、分别防什么？（提示，想想为什么要清两处 TUSHARE_TOKEN）
2. `client` 和 `bare_client` 的分工是什么？为什么默认头要带 zh？
3. python job 的步骤顺序为什么把 ruff 放在 pytest 之前？
4. 覆盖率门的 87% 怎么来的？为什么只在 CI 存在？
5. pip-audit 和 Dependabot 各自负责什么？
6. e2e 的两个 webServer 进程各自是什么？为什么 workers=1？
7. Python 与 Node 的锁定策略为什么不一致？
8. compose 为什么把端口绑到 127.0.0.1？

## 代码入口清单（推荐阅读顺序）

1. `tests/conftest.py`，97 行，隔离模式的完整范本
2. `tests/test_api_advisor.py`（`_parse_sse` + `configured` fixture），API 测试模式参照
3. `tests/test_demo_market.py` + `test_ips_golden_fixtures.py`，合成数据与金标准
4. `.github/workflows/ci.yml`，三 job 全文
5. `web/playwright.config.ts`，双进程编排
6. `docker-compose.yml` + 两个 Dockerfile，部署面
7. `pyproject.toml`、`requirements*.txt`、`.python-version`、`web/.nvmrc`、`.gitattributes`，钉与规

## 全指南结语

七章走完，这个系统的地图就齐了。第 1 章给全图，第 2 章是数学心脏，第 3 章管输入，第 4 章管 AI，第 5 章管传输，第 6 章管呈现，本章管敢不敢改。写作时每个数字都对回过代码；读的时候如果发现漂移，**以代码为准**，并按 `guide/AGENTS.md` 的纪律修文档。
