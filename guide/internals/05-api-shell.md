# 05 · API 传输壳与任务机制

## 目的与边界

本章讲 `api/`，它让 `src/` 的计算核心不依赖 HTTP。路由负责参数校验、调用核心并组装响应；API 层也拥有身份认证、持久化和后台任务生命周期。金融计算与量化规则仍由 `src/` 实现。

和第 1 章的分工是这样的，第 1 章沿一次优化请求走叙事，本章把壳本身的机制与边界讲全，端点地图、持久化、SSE 任务、缓存、i18n 都在其中。

## 核心概念

### 应用工厂与启动序列

`api/main.py` 的 `create_app()` 组装应用，`lifespan` 里按固定顺序做四件事。

1. `init_db()`，建 SQLite 表（幂等）
2. `maybe_auto_import()`，画像表为空时导入 Streamlit 时代的遗留 JSON（首次启动便利）
3. `reconcile_interrupted_tasks()`，把上次停机遗留的 `running` 任务记录置为 `failed`
4. demo 模式下种子虚构客户「林晓兰」（仅当画像表为空；幂等，不覆盖真实数据）

一个隐形的正确性细节藏在 `api/__init__.py`。它把仓库根插到 `sys.path[0]`，所以 `main.py` 头部那行 `import api  # noqa: F401` 是有意留下的，**导入顺序即功能**。删掉它，`src.*` 导入就会在某些启动目录下失败。

### CORS 边界

默认只放 `http://localhost:3000` 和 `127.0.0.1:3000`（Next dev），`CORS_ORIGINS` 环境变量可覆盖。生产形态下浏览器只跟 Next 服务器说话（第 1 章的同源代理），CORS 只是开发期的安全带。

## 端点地图

端点按域分组见下表（`*` = SSE 流式）。除 health 行已写出完整路径外，路径统一带 `/api` 前缀；完整模型以运行中的 OpenAPI 为准。

| 域 | 文件 | 端点数 | 端点 |
|---|---|---|---|
| 身份 | `routers/auth.py` | 4 | `POST /auth/login`、`POST /auth/demo`、`GET /auth/me`、`POST /auth/logout` |
| 行情 | `routers/market.py` | 4 | `GET /market/universe`、`/market/quotes`、`/market/risk-free-rate`、`/market/analytics` |
| CME | `routers/cme.py` | 1 | `GET /cme`（API 层**零缓存**，src 已有三级降级） |
| 组合 | `routers/portfolio.py` | 6 | `GET /portfolio/asset-classes`、`/portfolio/recommendation`、`POST /portfolio/backtest`、`POST /portfolio/optimize`、`POST /portfolio/optimize/async`（202）、`GET /portfolio/tasks/{id}/events`* |
| 监控 | `routers/monitoring.py` | 6 | `GET /monitoring/status`、`/monitoring/{doc_id}`、`/monitoring/{doc_id}/backtest`、`POST /monitoring/advice`*、`GET/POST /monitoring/{doc_id}/holdings` |
| 退休 | `routers/retirement.py` | 2 | `GET /retirement/cme-suggestion`、`POST /retirement/simulate` |
| 画像 | `routers/profiles.py` | 9 | CRUD 五件 + `/profiles/questionnaire`、`/profiles/compare`、`/profiles/import`、`/profiles/import/upload` |
| 顾问 | `routers/advisor.py` | 8 | `GET /advisor/status`、`POST /advisor/report/stream`*、报告库 CRUD + pdf/export |
| IPS | `routers/ips.py` | 6 | `POST /ips/generate`（202）、`GET /ips/tasks/{id}/events`*、文档库 list/detail + pdf/export |
| 设置 | `routers/settings.py` | 3 | `GET/PUT /settings/llm`、`POST /settings/llm/models` |
| 元 | `main.py` | 1 | `GET /api/health` |

## 请求生命周期

### 身份认证边界

`api/auth.py` 的 `get_current_principal` 从 Bearer token 解析当前身份。token 本身不包含用户 ID 或角色；服务端计算摘要，查询 `auth_sessions`，检查到期时间，再查询 `users` 检查用户是否存在、是否启用。客户端提交的用户 ID、角色或 cookie 不参与身份判定。

密码登录和显式 Demo 登录都签发同一种数据库会话，退出永久删除当前会话，重启后未到期会话仍有效。`is_active=False` 和关闭 `DEMO_MODE` 都只暂停认证，不删除会话；恢复后，未过期且未退出的旧 token 会重新有效。安全性禁用账号所需的全部会话撤销属于后续工作，不能用翻转标志替代。

密码哈希每个 API 进程最多并发两次，槽位满时立即返回本地化 503 与 `Retry-After: 1`，不在共享 AnyIO 工作线程中排队等待，也不增加账号失败计数。有空余槽位时，密码错误或账号冷却返回统一 401；认证请求的 422 不回显输入。账号级五次失败冷却仍可能被攻击者用于阻断已知用户登录；对外部署前的联合限流和永久撤销需求记录在仓库 `docs/known-issues.md` 的 KI-004。

当前只有 `/api/auth/me` 和 `/api/auth/logout` 使用身份依赖，既有业务 API 尚未接入。principal 只含 `user_id`、`email`、`is_demo`；组织、角色、客户归属及对象授权属于后续 issue。创建用户不会使其取得某个客户画像的归属，Web 工作站也尚未接入登录。使用说明见仓库中的 [身份配置文档](https://github.com/Michelia-L/AI-WealthPilot/blob/main/docs/identity-auth.md)。

### 校验顺序即语义优先级

以 `POST /portfolio/optimize` 为例（第 1 章走过）。

1. 先解析语言，`get_request_locale(request)` 读 `X-Locale` 头，未知/缺失一律回退英文
2. 再解析 profile（不存在 → 404）并检查方法约束（BL 无观点 / ERC 做空 → 422），**全部在取行情之前**
3. 最后取数与求解。src 层抛出的异常按类型翻译，`KeyError` → 404，`ValueError` → 422，`TokenBudgetExceeded` → 专属 422 分支（带 spent/budget 的本地化文案）

**路由声明顺序是正确性的一部分**。`/monitoring/status` 必须声明在 `/{document_id}` 之前，因为 `"status"` 满足 document_id 的字符集，注册晚了会被路径参数吞掉返回 404（代码注释明写）。`profiles` 的 `/questionnaire`、`/compare` 同理。

### 同步路由跑线程池

所有端点用普通 `def` 声明（非 `async def`），FastAPI 把同步路由放进线程池跑，因为底层 yfinance/计算是阻塞 I/O（`market.py` docstring 明示）。异步任务端点（`async def`）只负责建任务和订阅流，重计算走 `loop.run_in_executor`。

## 契约层（`api/schemas.py`）

Pydantic 模型集中在一个文件，按身份、meta/行情、优化、退休、画像、顾问、IPS、监控、LLM 设置等域分组。有几处设计值得说。

- **CME 契约与引擎共享同一份模型**。`CMEReport` 直接 import 自 `src/portfolio/cme_models.py`，schema 与引擎不可能漂移（模块 docstring 明示此意图）。
- 约束集中在 Field。`OptimizeRequest.method` 是 6 值 Literal，`n_simulations ∈ [50,2000]`，`annual_fee_rate ∈ [0, 0.10]`；`SurplusConfigInput` 等用 `model_validator` 做跨字段校验。
- **已知漂移案例**。`OptimizeRequest.expected_return_source` 的 Field description 仍写「black-litterman is incompatible with 'cme'」，但代码早已把 CME 向量作为 BL 先验传入，**以代码为准**（这处文案欠账已记入台账候选）。

## SQLite 持久化（`api/db.py`）

以下表都走 SQLModel。身份表通过现有 `init_db()` 增量创建，不重写旧画像或自动分配归属。

| 表 | 模型 | 设计 |
|---|---|---|
| `users` | `UserRecord` | UUID 身份、唯一规范化 email、加盐密码哈希、启用/Demo 标志、登录失败计数与冷却截止时间；不包含组织与角色 |
| `auth_sessions` | `AuthSessionRecord` | 随机 token 的 SHA-256 摘要、用户 ID、创建/到期时间；不存明文 token |
| `client_profiles` | `ProfileRecord` | **JSON 列存完整 `asdict(ClientProfile)`**，dataclass 形状归 src/ 所有，可自由演进；`name`/`updated_at` 等索引列冗余出列表 UI 要过滤/排序的字段。`user_id` 为多用户未来预留，当前恒 NULL |
| `background_tasks` | `TaskRecord` | 内存任务注册表的写穿透镜像，`task_id` 主键、`kind`（ips/optimize）、`status`、`meta_json`、**`events_json` 纯文本 JSON 列**（事件词汇表归路由所有，可随任务类型演进） |
| `app_settings` | `AppSettingRecord` | KV 表，存 FR-002 的 LLM 端点配置（`llm_base_url`/`llm_api_key`/`llm_model`） |
| `holding_snapshots` | `HoldingSnapshotRecord` | 按 IPS 文档保存完整估值快照；同日修订追加记录 |

工程上有两个细节。`connect_args={"check_same_thread": False}`，因为 FastAPI 在线程池里跑同步路由。engine 在**导入时**创建，import `api.db` 即解析 DB URL，测试经 `AIWP_DB_URL` 环境变量或 monkeypatch 重定向。

## SSE 任务机制（DB 侧）

第 1 章讲了断线重连的叙事，这里补机制细节（`api/tasks.py`，239 行）。

- **写穿透顺序**。`publish()` 给事件盖从 1 开始的 `seq`，**先写库**（read-modify-write `events_json`，截断保留最后 500 条；终态 done/error 同时翻转行状态并写 `finished_at`）**再入内存队列**，这样 SSE drain 看到终态时它已持久化。
- **重连去重**。先回放持久化日志并记录 `max_seq`，再 drain 活队列，跳过 `seq ≤ max_seq`，无缺口无重复。无 seq 的旧事件按 seq 0 处理。
- **终态从存储回放**。已完成任务的活队列早被第一个消费者排空，再读会挂起，所以终态任务重放直接读 SQLite。
- **开机和解**。`reconcile_interrupted_tasks()` 把遗留 `running` 置 `failed`，回放时在尾部合成一条本地化的「任务被中断」事件。
- **持久化失败只记日志不抛出**，DB 坏了不许弄死计算任务本身。

这里没有 Celery/Redis，任务在进程内跑，这套机制覆盖断线重连和重启回放的真实需求。**边界**是任务注册表单进程，多 worker 部署时任务只活在创建它的进程里。

## TTL 缓存（`api/cache.py`）

`TTLCache` 是进程内线程安全缓存，41 行，入口是 `get_or_set(key, ttl, factory)`。**factory 在锁外执行**，慢取数不阻塞其他读者，代价是并发下可能重复计算（可接受）。缓存无容量上限、无后台清理，条目只在被访问且过期时被覆盖。注释里明示，多进程部署须换共享存储（Redis）。

全包共 10 个实例，行情报价 300s、分析 300s、无风险利率 3600s ×2、价格帧 300s、回测 600s ×2、收益率曲线 3600s、基金 AUM 86400s、监控 fleet 86400s。两个模式值得单独说。

- **主动失效**。曲线/AUM 缓存取到 None 时立即 `invalidate`，不让降级结果钉满整个 TTL，下一请求重试。
- **日期进 key**。fleet 状态的缓存 key 含 `date.today()`，每日首次请求自动重算的懒语义，没有定时器。

## i18n 消息表（`api/i18n.py`）

消息表按 auth、holdings、common、advisor 等域分组，每 key 提供中英文。`msg(key, locale, **fmt)` 的语义有两条。

- 未知 key **抛 `KeyError`**，让缺失条目在测试里响亮失败。
- 未知 locale **静默回退英文**，两种未知情况的处理故意相反。

红线在路由层，路由内禁止内联中文，新文案必须双语进表。`src/` 侧的计算函数把双语文案内置在各自模块（`views.py` 的 `_VIEW_STRINGS`、`ips_workflow.py` 的 `_SAA_STRINGS` 等），原因是 src 不得 import api，这些是文档化的有意例外。还有一处已知例外，retirement/market 路由有少数内联**英文** detail，规则约束的是中文，英文未强制入表。

## 画像转换与遗留迁移

- **`profile_convert.py`** 做 API payload ↔ 存储 JSON ↔ src dataclass 的三向转换。核心规则是**问卷答案优先于手动滑杆分**，某轨答案非空时用 src 规则推导并覆盖，空答案保留手动回退。`_safe_ratio` 把 inf/nan 转成 None，因为 JSON 无法承载 inf，有负债无资产的 +inf 哨兵在 API 响应里变成 None。
- **`migrate_profiles.py`** 把 Streamlit 时代的 `data/profiles/*.json` 导入 SQLite。幂等键是 `(name, created_at)` 二元组，重跑不产生重复行；`maybe_auto_import()` 仅在画像表为空时执行。注意它 import `profiler` 用的是**模块属性引用**（`profiler.PROFILES_DIR`），刻意避开 from-import，这样测试的 monkeypatch 才能生效。

## demo 模式在 API 层

- 启动时若画像表为空，种子虚构客户「林晓兰」（数据与 demo 夹具对齐，同客户、同 SAA 上下文）。
- 三个 LLM 流式端点在 demo 下整体换成夹具回放（`demo_mode.py`），端点外壳/SSE 协议不变；无 LLM key 也不返 503。
- `GET /advisor/status` 与 `GET /settings/llm` 会暴露 `demo` 标志，前端据此显示演示水印。
- `POST /auth/demo` 显式取得共享虚构身份的会话，首次调用才创建该身份。Demo 模式不会自动把匿名请求视为已登录，也不把身份绑定到演示画像。

## `api/Dockerfile`

- 构建上下文是**仓库根**（API 直接 import `src/`），只 COPY `src/`、`api/`、`docs/ips_reference/`；运行时数据靠 `./data` volume，不烘进镜像。
- **CJK 字体契约**。Debian 的 fonts-noto-cjk 是 CFF 轮廓，fpdf2 2.8.7 渲染乱码，故装 WenQuanYi Micro Hei（TrueType）并软链到 `ips_storage._find_cjk_font` 探测的固定路径 `.../noto/NotoSansCJK-Regular.ttc`。CI 的 python job 里有同样两步，**改任何一边都要同步另一边**（隐式契约，注释明写）。

## 设计决策与取舍

- **为什么继续使用 SQLite？** 本地工作站的现有数据都存放在一个文件中，身份与会话可复用同一持久化入口。用户表的引入没有完成多用户隔离；画像 `user_id` 仍待归属模型接入。
- **为什么事件存纯文本 JSON 列不建关系表？** 事件词汇表归各任务类型所有且会演进，关系表会把每次演进变成 migration。JSON 列用读方负责解析换掉 schema 刚性。
- **为什么模型集中一个文件，不按域分文件？** API 契约集中可查，各消费方复用同一份模型。
- **为什么 fleet 每日重检用日期进 key，不用定时任务？** 没有调度器依赖，进程重启天然安全；代价是当日首次请求略慢（懒语义）。

## 已知近似与边界

- 身份认证目前只保护身份查询和退出；既有业务路由仍未认证，尚无角色、组织或对象级授权。
- 任务注册表单进程；持久化事件只保留最后 500 条。
- TTL 缓存无容量上限。缓存键空间有界（ticker 组合有限），当前无内存压力，但理论上无主动清理。
- `expected_return_source` 的 schema 描述过期（以代码为准）。
- retirement/market 两处内联英文 detail 未入 i18n 表（规则只禁中文内联）。
- `_seed_demo_profile` 只在 demo 模式且表空时插入，已在库的真实客户永远不会被覆盖。

## 自检问题

1. `api/main.py` 顶部那个 `import api` 为什么不能删？
2. 启动序列的四件事顺序是什么？如果 `reconcile_interrupted_tasks` 跑到 `init_db` 前面会怎样？
3. 为什么 `/monitoring/status` 必须先于 `/{document_id}` 注册？
4. `publish()` 为什么先写库再入队列？顺序反了会怎样？
5. 已完成的任务重放为什么从 SQLite 读，不读内存队列？
6. `TTLCache` 的 factory 为什么在锁外执行？代价是什么？
7. `client_profiles` 为什么用 JSON 列 + 冗余索引列，不走全关系表？
8. i18n 里未知 key 抛错、未知 locale 回退，两种相反处理各自的理由是什么？

## 代码入口清单（推荐阅读顺序）

1. `api/main.py`，启动序列、路由挂载与认证输入错误脱敏
2. `api/db.py`，身份、会话、画像和其他持久化模型
3. `api/tasks.py`，SSE 任务的写穿透与回放（本章含金量最高）
4. `api/cache.py`，41 行，读完即懂
5. `api/i18n.py`，消息表与 `msg()` 语义
6. `api/routers/portfolio.py`，最复杂的路由（校验顺序、TTL 缓存、异步任务）
7. `api/profile_convert.py` / `migrate_profiles.py`，转换与迁移
8. `api/schemas.py` 按域抽查 + `api/Dockerfile`
9. `api/auth.py` / `api/routers/auth.py` / `api/create_user.py`，身份依赖、会话端点和本地用户创建
