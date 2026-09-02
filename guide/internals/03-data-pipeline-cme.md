# 03 · 数据管道与 CME

## 目的与边界

本章讲系统的输入层，覆盖 `src/data/`（行情、利率、波动率的获取与归一化）和 `src/portfolio/` 里的 CME 侧（`cme_engine.py` / `cme_cache.py` / `cme_models.py` / `forward_returns.py`），外加 `src/config.py` 的常量表导读。

这一层只负责产出干净的输入，也就是价格帧、收益帧、无风险利率、收益率曲线和 CME 报告。**它不含任何组合逻辑**，从不决定钱怎么配。它要保证的是另外几个问题都有明确答案，喂给引擎的数据是什么、从哪来、失败时降级成什么。

## 核心概念

### 降级哲学

贯穿全层的原则只有一条，**外部数据源的失败几乎从不向上抛异常**，只记 warning 并降级到下一级，全灭时用静态兜底。例外有两处，参数错误（未知 ticker 或 period 时抛 `ValueError`）和 `yield_curve.rate_at` 拿到空曲线。这两处属于调用方传错，不算数据故障。

动机很直接，一个自托管工作站不能因为雅虎抽风就让页面报错。每个函数失败后降级成什么都是显式设计，见下文各节。

### 两套资产宇宙

代码里有两个并存、几乎不相交的资产清单，都在 `src/config.py`。

- **`ASSET_UNIVERSE`（17 个 ticker）**是市场看板用的观察宇宙，含指数（^GSPC、^VIX）、汇率（CNY=X）、商品期货等**不可交易**标的，跨 13 个 category。
- **`DEFAULT_ASSET_CLASSES`（15 个 key）**是优化器用的**可交易**宇宙，全部是 ETF 代理（SPY/EFA/…/BTC-USD/511010.SS）。

两者唯一的交集是 BTC-USD。CME 还有第三套自己的映射 `IPS_ASSET_CLASS_TICKERS`（7 个类别）。写文档或改代码时，先想清楚在说哪一套。

## 行情主层 `market_data.py`

### 多源路由（`fetch_price_history`）

入口签名是 `fetch_price_history(tickers, period, interval, base_currency, adjust_currency)`。路由按下面的顺序走。

1. **DEMO_MODE 最早早退**。命中即返回合成数据（`demo_market.py`，见后文），整个路由层不执行。
2. **CN 路由**。ticker 在 `TUSHARE_TICKER_MAP`（当前只有 000300.SS）**且**日线 **且** tushare token 已配置，走 `_fetch_cn_routed` 级联，顺序是 **Tushare Pro → akshare → yfinance**，首个成功者优先。
3. 其余 ticker 直接走 yfinance。

级联之间的成败判定交给 `_assert_fresh` 做**新鲜度校验**，不走异常捕获。akshare、sina 这类抓取型源会不报错却返回一周前的旧快照，异常捕获拦不住这种情况，所以判定标准定为最新交易日距今 ≤ 12 天，12 天刻意超过中国最长假期。两路结果 `pd.concat` 后按请求顺序重排列，只丢全 NaN 行。

### FX 换算（`_fetch_price_history_yf`）

目标是把所有资产折算到基准币（`BASE_CURRENCY = "CNY"`），让 CME 表和组合收益同币种。有两个要点。

- **报价方向不统一**。Yahoo 的 `{CCY}=X` 汇率里，仅 EUR/GBP/AUD/NZD 表示每单位兑多少 USD（乘），其余都表示每 USD 兑多少单位（除）。`FX_USD_PER_UNIT` 常量表记录这四个例外，其中 AUD/NZD 当前没有对应资产，是预留。
- **两步换算**。非 USD 资产先换算到 USD，再（若基准币非 USD）换算到 CNY；货币标记为 `"Index"` 或 `"Rate"` 的资产（如 ^VIX、CNY=X 自身）两步都跳过。

汇率列单独做 `ffill().bfill()` 处理交易日错位，**资产价格列不填充**，缺失如实保留给下游（这正是 KI-003 的入口，见第 2 章 CVaR 的 complete-case 处理）。

### 无风险利率降级链（`fetch_risk_free_rate_detailed`）

返回 `(rate, source_label)` 二元组，来源如实披露。分两条腿走。

- **USD** 腿是 FRED DGS3MO（需 `FRED_API_KEY`）→ yfinance `^IRX`（fast_info 失败再试 history）→ 静态 0.045。
- **CNY** 腿是 akshare 中债 1 年期国债收益率 → 静态 0.02。

设计承诺是**永不抛异常**，每级失败只记 warning。优化器收益经 FX 折算成 CNY，所以 Sharpe 的 rf 刻意取 CNY 腿（见 `api/routers/market.py` 注释），口径一致。

### 并发报价与基金 AUM

- `get_latest_quotes` 把 17 个 ticker 的 `fast_info` 抓取放进 `ThreadPoolExecutor(max_workers=8)` 并发执行。串行的话，高延迟网络下每个要约 1 秒。KI-002 把市场页冷启动从 14.2s 降到 2.9s，见台账。单 ticker 失败返回 None，静默跳过。
- `fetch_fund_aum` 取 `Ticker.info["totalAssets"]` 当资产类别市值的粗略代理，给 BL 均衡先验用。策略是**全有或全无**，任一 ticker 缺数据（指数、CN 上市基金常见）整组就返回 None，调用方退化等权。

### `compute_returns` 的口径

`method="log"` 用对数收益，`"simple"` 用简单收益。`compute_correlation_matrix` 刻意用简单收益，注释给的解释是截面更直观。`dropna(how="all")` 只丢全空行，混合交易日历的 NaN 行会存活下来。这是数据层的既定行为，容忍责任在使用方。

## CN 两级 provider 与中债曲线

### `tushare_provider.py` / `akshare_provider.py`

两者是同一契约的付费实现和免费实现。

- **懒初始化**。tushare 的 `pro_api` 客户端首次调用才建，akshare 的 `is_available()` 就是一次 import 尝试，**包不装，整条 CN 中间层静默消失**。
- **覆盖极小**。两边各只有 1 条映射（`000300.SS`），不要写成「CN 资产走 Tushare」这种笼统表述。
- 未知 ticker 或 period 抛 `ValueError`；上游空响应补成全 NaN 列，路由层的 `_assert_fresh` 会识别并降级。
- period 表是**自然日**口径（1y=366），与 `demo_market.py` 的交易日口径（1y=260）不同，跨层引用时注意。

### `yield_curve.py` · 中债收益率曲线

服务 LDI 负债折现。级联哲学与行情层相同，分两级，Tushare Pro `yc_cb`（**单独授权的接口**，权限不够就静默降级）→ akshare `bond_china_yield`。两侧统一归一化为 `{期限年: 小数利率}`。akshare 侧的期限是中文标签，`_AK_TENOR_COLUMNS` 共 8 档，从 3 月→0.25 到 30 年→30.0。

`rate_at(curve, t)` 做线性插值。低于最短或高于最长期限时**持平外推**，不外推斜率，端点外推斜率是经典的曲线事故源。空曲线抛 `ValueError`，这是本层少数会抛异常的函数。历史曲线接口把两侧都 pivot 成同构的日期 × 期限帧，负债久期点可以直接拿它估波动（第 2 章 LDI 的曲线法）。

### `implied_volatility.py` · IV 代理

`IV_PROXY_MAP` 把 10 个 ETF 映射到两个 IV 指数，股票类（SPY/EFA/EEM/ASHR/EWH）全部代理到 **^VIX**，债券类（AGG/TLT/HYG/EMB/TIP）全部代理到 **^MOVE**。另有 6 个资产被显式注释置 None，包括黄金、REITs、商品、现金、BTC、000300.SS，均无可靠 IV 指数。

**已知粗糙处（代码注释自认）**。A 股（ASHR）、港股（EWH）用 VIX 代理是「proxied by VIX」这个级别的近似，并非市场惯例映射。同一 IV 指数一次调用内只取一次（去重缓存）。取不到就返回 None，由 CME 引擎退回历史波动率，混合逻辑不在这层。

## DEMO_MODE 合成行情（`demo_market.py`）

这是 KI-002 的交付物，让整个应用（市场页/优化器/监控/回测）零网络可跑。确定性设计的每一条都有理由。

- **种子**。`_ticker_seed` 取 ticker 字符串的 SHA-256 前 8 字节，不能用内建 `hash()`，后者按进程加盐，跨次运行不稳定。
- **锚定日**。`REFERENCE_END` 硬编码，所有序列结束于固定日期，与真实时钟无关，e2e 快照永不漂移。
- **GBM 参数**。`_CATEGORY_PARAMS` 按 13 个类别给出（年化漂移, 年化波动, 起始价），同类别不同 ticker 的起始价乘一个 `[0.6, 1.4)` 区间内的确定性随机系数。
- **Itô 修正**。`daily_mu = (drift − 0.5·vol²)/252`，这是对数空间的修正，让对数增长率的实现值等于名义漂移。
- **波动率指数截断**在 `[9, 85]`。真实波动率会均值回归，纯 GBM 会漂到荒谬水平，注释承认这是权宜之计。
- **刻意不模拟相关性**。各 ticker 用独立种子，写文档或演示时不应声称合成数据有真实的相关结构。

## 前视收益（`forward_returns.py`）

CME 的 building-blocks 前视预期收益。四类资产对应四个模型。

| 类别 | 模型 | 实现 |
|---|---|---|
| 股票/REIT | E(R) = 股息率 + 长期增长 | yfinance `dividendYield` + `CME_FORWARD_GROWTH_ASSUMPTIONS`（config 里的文档化假设，非数据） |
| 债券 | E(R) = YTM 代理 | 基金 `yield` 字段 → 退 `^TNX` 十年期收益率 |
| 黄金 | E(R) = 通胀假设 | 长期实际收益≈0 |
| 现金 | E(R) = 无风险利率 | 直接取 rf |

边界有这么几条。

- `FORWARD_RETURN_MAP` **只覆盖 7 个 ticker**，不在表内的一律返回 None，CME 回退历史均值。
- `_normalize_yield` 用的是启发式。yfinance 的 yield 字段编码不一致，**>0.2 一律当百分数除以 100**，若某标的真实收益率超 20% 就会被错误缩放（自认的近似）。
- 000300.SS 本身无股息数据，用 ASHR ETF 做收入代理（指数↔ETF 等价）。
- 前视收益按本地货币计，**汇率预期变动假设为零**（在 CME 方法论说明中披露）。

## CME 引擎（`cme_engine.py` + `cme_models.py` + `cme_cache.py`）

### 管线（`_compute_cme_fresh`）

取价（`adjust_currency=True`，全部折算 CNY，未对冲汇率敞口包含在内）→ 简单收益 → 动态无风险利率（CNY 腿）→ IV 抓取 → 前视收益 → 逐资产指标 → 相关矩阵。逐资产这一环，**不足 60 个收益观测点直接跳过**，这大约是 3 个月日线的最低统计要求。

两个混合公式如下（τ、ω 默认均 0.5，`config.py` 可调）。

\[
\sigma_{blended} = \tau \cdot \sigma_{IV} + (1-\tau)\cdot\sigma_{hist}
\]

\[
E(R) = \omega \cdot R_{forward} + (1-\omega)\cdot R_{hist}
\]

降级是**逐资产**的，某个资产的前视输入缺失只影响它自己（保留历史均值），不拖垮整份报告。波动率 regime 用 IV/HV 比率分四档（<0.8 为 low，0.8 到 1.2 为 normal，1.2 到 1.6 为 elevated，≥1.6 为 high）。

### 数据契约（`cme_models.py`）

`AssetClassCME` 有 13 个字段。注意 `expected_return` 已经是混合值，纯历史值另存于 `historical_return`。`volatility` 字段永远是**纯历史** σ，组合计算实际用的是 `blended_volatility`，字段名与用途的这个错位，读代码时容易踩。`CMEReport` 的相关矩阵**按资产中文显示名键控**（不是 ticker）。这份模型被 `api/schemas.py` 直接复用，CME 契约与引擎共享同一份定义，不可能漂移。

### 缓存（`cme_cache.py`）

CME 是战略级长期预测，不必每次重算。`CMECacheManager` 用双文件（报告 + 元数据），写入走临时文件 + 原子 rename（**明确不保证多进程并发**）。`compute_params_hash` 把回溯年数、通胀、ticker 表、τ、ω、基准币哈希成 MD5 截 8 位，参数变了缓存自动失效。三级降级依次是有效缓存 → stale 缓存兜底（stale-while-revalidate）→ 静态兜底文件（`docs/ips_reference/cme_fallback.json`），全灭才 `RuntimeError`。

### 参考组合（`reference_portfolio_suggestion` / `reference_allocation_for_level`）

- `reference_portfolio_suggestion` 把某套配置权重按 CME 的混合 μ、混合 σ 与相关矩阵合成组合级 μ_p/σ_p。**缺相关性的资产对按 0（不相关）处理**，注释自称「conservative and honest」（保守且诚实）。
- `reference_allocation_for_level` 由 `RISK_LEVEL_CAPS` 推导各风险等级的参考配置。cap 是上限，可以加超 100%（进取型 0.9+0.3=1.2），所以先把**风险预算封顶 95%**，再按 cap 比例切分。组内拆分是文档化的硬编码假设（权益 50/40/10、另类 75/25、防御 85/15）。
- 消费方是市场页 CME 卡片、IPS 流水线、退休页的参考组合建议这三处。IPS 流水线里 `format_cme_for_prompt` 负责注入 LLM 上下文，注意该函数是**纯中文硬编码**，不走 locale 机制。

## `config.py` 常量导读 + `utils.py`

`config.py`（403 行）是全项目的单一常量源，按主题分组。分组包括应用元信息（`APP_VERSION` 等）、资产宇宙三件套、利率与模拟默认、BL 三参数（τ=0.025 / δ= 2.5 / 置信度 70）、LLM 端点与预算（`LLM_TASK_TOKEN_BUDGET = 250K` 等，P24）、DEMO_MODE、CME 全套（回溯 5 年、通胀 2.5%、缓存 90 天、τ=ω=0.5、增长假设 4 条、参考配置 7 项、CME→优化器映射 6 条）、个人通胀预设三档、LDI 代理久期 4 条、Tushare 映射、`ASSET_CLASS_ALIASES`（7 类 35 别名，P25）、`RISK_VOLATILITY_BANDS` 五档（P25 单一事实源）。

有两个反直觉的地方。

- `load_dotenv(override=True)`，所以 **.env 文件优先于真实环境变量**，与环境变量优先的常见约定相反。
- `DEEPSEEK_*`/`LLM_*` 只是 env 默认值，运行时可能被 SQLite `app_settings` 覆盖（`llm_config.py`，第 4 章）。

`utils.py` 只有一个函数 `sanitize_filename`，做正则 `[^\w\-]` 清洗。**Python 3 的 `\w` 是 Unicode 感知的，中文字符会被保留**，中文客户名清洗后仍是中文，这是有意的隐含特性。

## 设计决策与取舍

- **为什么付费源优先、免费源兜底、静态值垫底？** 这是按数据质量与可用性排的序。Tushare 结构化但需 token；akshare 免费但属于抓取型，会静默陈旧，所以配了新鲜度校验；yfinance 全球覆盖但 CN 资产质量一般；静态兜底保证应用永远起得来。
- **为什么 FX 只填汇率列不填价格列？** 汇率缺日是技术性问题（周末/假日无报价），填充无害。资产价格缺失是真实信息（停牌/日历错位），填充会伪造收益，后者如实留给下游决定（KI-003 的 complete-case 就是下游的一种回答）。
- **为什么 CME 缓存用参数哈希而不是只看 TTL？** 参数变了（比如换了资产表或基准币），90 天 TTL 内的旧缓存就是错的，哈希让失效自动发生。
- **为什么 demo 数据锚定固定日期？** e2e 快照与演示截图要求跨时间可复现，代价是 demo 的最近行情永远是那一天。

## 已知近似与边界

- `_normalize_yield` 的 >0.2 启发式会把真实收益率超 20% 的标的错误缩放。
- ASHR/EWH 的 IV 用 ^VIX 代理，是粗糙近似。
- `EWH`（港股）有意不进 `CME_TICKER_TO_OPTIMIZER_ASSET`，未覆盖资产退回样本均值并披露，所以这是有意的处理而非遗漏。
- 黄金前视收益=通胀假设、现金=rf，都是 stylized 模型，不当作预测。
- 静态兜底值（rf 4.5%/2%、CME fallback JSON）会随时间陈旧。它们是保证应用能启动的保险丝，不代表当前市场观点。
- `rate_at` 端点持平外推；长于 30 年的负债久期按 30 年利率计。
- demo 合成序列间无相关性。
- `format_cme_for_prompt` 与 CME 方法论说明是纯中文硬编码（与第 4 章其他模块的 locale 机制不一致，是已知的历史形态）。

## 自检问题

1. `fetch_price_history` 的路由顺序是什么？`_assert_fresh` 为什么用新鲜度而不是异常来判断降级？
2. Yahoo 的汇率报价方向为什么分两组？`"Index"`/`"Rate"` 哨兵在 FX 换算里起什么作用？
3. 无风险利率的两条腿各有几级降级？为什么优化器用 CNY 腿？
4. `compute_returns` 的 `dropna(how="all")` 与第 2 章 CVaR 的 `dropna()` 分别丢什么行？
5. demo 合成数据的确定性由哪三个机制保证（种子/锚定日/类别参数）？它刻意不模拟什么？
6. 前视收益四个资产类别的模型各是什么？哪个 ticker 有模型覆盖、哪个没有？
7. CME 报告里 `expected_return` 与 `historical_return`、`volatility` 与 `blended_volatility` 的区别？
8. CME 缓存的三级降级和参数哈希各自防什么问题？
9. `ASSET_UNIVERSE` 和 `DEFAULT_ASSET_CLASSES` 为什么是两份？交集是什么？

## 代码入口清单（推荐阅读顺序）

1. `src/config.py`，常量表全图（先建立词汇表）
2. `src/data/market_data.py`，行情主层（路由/FX/降级链）
3. `src/data/tushare_provider.py` + `akshare_provider.py`，CN 两级（对照读，同一契约）
4. `src/data/yield_curve.py`、`src/data/implied_volatility.py`，利率与波动率两条专线
5. `src/data/demo_market.py`，合成数据（最短的一章，111 行）
6. `src/portfolio/forward_returns.py`，前视收益模型
7. `src/portfolio/cme_engine.py`（`compute_cme` → `_compute_cme_fresh` → 两个 reference 函数）→ `cme_models.py` → `cme_cache.py`
8. `src/utils.py`，一个函数，30 行
