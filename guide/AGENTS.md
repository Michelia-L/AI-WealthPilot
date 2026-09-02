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

## 语言风格（写作时遵守，省去后置润色）

约束站点正文，不约束本文件与 `docs/` 工程记录。验收跑 `check_prose.py`（human-writing skill 自带，`~/.agents/skills/human-writing/scripts/`），failures 须清零。

- 正文禁破折号（—、——、–）：改逗号、句号或拆句。代码块、行内代码、链接内不受限。
- 冒号只用于引出直接原话；解释性、标签式写法改成完整句子（不写「**TTL**：300 秒」，写「**TTL** 为 300 秒」）。表格单元格同此规则。
- 标题内部分隔用「 · 」（如 `## 核心概念 · 三层架构`），不用冒号和破折号。
- 禁翻案腔（不是 A 而是 B、看似实则、与其说不如说），判断从正面下。
- 禁三连以上同构排比；禁名词化（进行了/实现了…的提升）；禁路标词（说白了、值得注意的是、需要指出的是）；禁宣传腔（精准、杜绝、确保、无缝、赋能、闭环；引代码原文除外）。
- 「」每章最多三四处；句长交错；不预告结构，结尾不升华。
- 数字保持阿拉伯原样，不约数化（与「以代码为准」同一条纪律的两面）。

## 已知陷阱

- **站内搜索自动化验证**：搜索按 `keyup` 触发，Playwright 等工具输入中文走 `insertText` 不产生 keyup——需补按 End 等键才执行查询。勿把该测试假象当成功能缺陷（2026-08 实测浪费过一小时）。
- `search_index.json` 由浏览器按 URL 缓存，改配置重测搜索时先确认索引是新的（磁盘文件为准）。
