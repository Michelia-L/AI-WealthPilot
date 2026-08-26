# AI WealthPilot Internals

> 项目的「内部构造说明书」——不只讲是什么，更讲**为什么这么做、怎么实现的**。

## 这个站是什么

AI WealthPilot 是一个私人财富管理 AI 顾问工作站：量化组合引擎（六种优化方法）+ LangGraph 多智能体 IPS 流水线 + LLM 顾问 + Next.js 前端。

主仓库的 [README](https://github.com/Michelia-L/AI-WealthPilot#readme) 面向「用户」：功能是什么、怎么跑起来。本站面向「想理解内部构造的人」（包括作者自己）：每个模块为什么存在、实现思路是什么、做设计决策时权衡了什么、已知的近似与边界在哪里。

## 内容地图

- **[Internals 指南](internals/index.md)**——核心内容，按子系统分七章逐模块讲解，每章附自检问题。持续写作中。
- **[工程台账](known-issues.md)**——缺陷与需求的真实记录（KI/FR 编号），含已解决条目的根因与修复方式。
- **[IPS 参考](ips_reference/ips_template_structure.md)**——IPS 文档模板结构与示例，供 LLM 生成与读者参考。

## 阅读约定

- 引用代码一律用「路径 + 符号名」（如 `src/portfolio/optimizer.py` 的 `_solve_cvar_lp`），不引用行号——行号会腐化，符号名基本稳定。
- 每个数字、每条断言都以代码为准。如果发现文档与代码不一致，**以代码为准**并欢迎提 issue。
