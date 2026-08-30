# guide/ — Internals 文档站与写作纪律

`guide/` 是 MkDocs 站点源（配置在仓库根 `mkdocs.yml`，`docs_dir: guide`；本文件经 `exclude_docs` 排除出站点构建）。与 `docs/` 的分工：`docs/` 放工程记录（`known-issues.md`、`migration-nextjs.md`、`ips_reference/`、`images/`），`guide/` 只放文档站内容。

## 命令

```bash
mkdocs serve            # 本地预览（仓库根，激活 .venv）
mkdocs build --strict   # 提交前必跑；未收录进 nav 的页面、坏链接都会报错
```

push main 经 `.github/workflows/docs.yml` 自动部署到 GitHub Pages。依赖 pin 在 `requirements-dev.txt`（mkdocs-material + jieba，jieba 负责构建期中文分词，勿删）。

## 结构

- `index.md`：站点首页；`internals/`：Internals 指南（核心内容，七章路线图见 `internals/index.md`）；`diagrams/`：SVG 架构图（**双消费方**：本站章节 + README，移动需同步 README）；`javascripts/`：MathJax 接线脚本。
- 新增页面必须同步 `mkdocs.yml` 的 `nav`（否则 strict 构建失败）。
- `docs/` 侧的资产有外部引用方，动之前先查：`ips_reference/` 被 `api/Dockerfile` COPY 进镜像；`images/` 被 README 引用。

## Internals 写作纪律

- 每个数字、每条断言以代码为准；发现文档与代码漂移时**以代码为准并修文档**。
- 引代码用「路径 + 符号名」（如 `api/tasks.py` 的 `stream_task_events`），**不引行号**——行号会腐化。
- 中文优先；英文版暂缓。文案遵守根 AGENTS.md 的务实规则（无包装性修饰词）。
- 每章统一结构：目的与边界 → 核心概念 → 逐模块讲解 → 设计决策与取舍 → 已知近似与边界 → 自检问题（5-8 个）→ 代码入口清单。
- 写完一章更新 `internals/index.md` 路线图状态。

## 已知陷阱

- **站内搜索自动化验证**：搜索按 `keyup` 触发，Playwright 等工具输入中文走 `insertText` 不产生 keyup——需补按 End 等键才执行查询。勿把该测试假象当成功能缺陷（2026-08 实测浪费过一小时）。
- `search_index.json` 由浏览器按 URL 缓存，改配置重测搜索时先确认索引是新的（磁盘文件为准）。
