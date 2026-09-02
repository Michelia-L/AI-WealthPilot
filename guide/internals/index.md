# Internals 指南

这份指南逐模块讲解 AI WealthPilot 的目的、实现思路与设计决策。它面向想真正理解这个系统内部构造的读者，假定你会读代码。这里的价值是讲清代码**之外**的那部分，比如为什么这么切分、权衡了什么、边界在哪里。

## 章节路线图

| 章 | 标题 | 范围 | 状态 |
|---|---|---|---|
| 01 | [一次请求的完整旅程](01-request-journey.md) | 横切三层架构，从浏览器点击到图表渲染的每一跳 | ✅ |
| 02 | [量化引擎](02-quant-engine.md) | `optimizer.py` 六种优化方法逐一讲解（MVO / Resampled / BL / Mean-CVaR / LDI / ERC）、`optimize_service.py`、`views.py`、`risk_constraints.py`、`risk_metrics.py` | ✅ |
| 03 | [数据管道与 CME](03-data-pipeline-cme.md) | `market_data.py` 多源路由与 FX、CN provider 级联、`yield_curve.py`、`implied_volatility.py`、`demo_market.py`、`forward_returns.py`、CME 引擎三件套、`config.py` 常量导读 | ✅ |
| 04 | [AI 智能体层](04-ai-agents.md) | 画像评分、组合推荐、顾问报告、IPS LangGraph 流水线（9 节点 + 三向审查 + token 预算闸）、报告/IPS 存储与导出、demo 回放层 | ✅ |
| 05 | [API 传输壳与任务机制](05-api-shell.md) | 43 个端点地图、82 个 Pydantic 模型、SQLite 三表、SSE 任务写穿透与断线回放、TTL 缓存、双语消息表 | ✅ |
| 06 | [Web 前端](06-web-frontend.md) | 12 个页面、RSC 与同源代理的分界、自研 i18n 的类型约束设计、plot-chart 主题层、优化器工作区状态机、设计令牌 | ✅ |
| 07 | [质量与可复现性工程](07-quality-engineering.md) | 测试套件组织与隔离模式、CI 三job 与 87% 覆盖率门、Dependabot、e2e 双进程编排、版本钉与容器 | ✅ |

## 每章的统一结构

1. **目的与边界**，这个子系统负责什么、不负责什么
2. **核心概念**，理解代码所需的最小背景
3. **逐模块讲解**，实现思路，锚定到具体符号
4. **设计决策与取舍**，为什么不选看起来更常见的方案
5. **已知近似与边界**，系统的简化假设如实披露
6. **自检问题**，能脱稿回答这些问题，才算真正读懂了这章
7. **代码入口清单**，按推荐阅读顺序排列的文件列表
