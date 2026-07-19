# AI WealthPilot — Web Frontend

「墨金私行」设计系统下的私人财富管理工作台。Next.js（App Router）+ Tailwind CSS v4，服务端组件经同源代理调用 FastAPI 后端，SSE 承载流式生成。

## 开发

```bash
npm install
npm run dev        # http://localhost:3000（需后端运行于 :8000）
npm run lint
npm run build
```

- 后端地址通过 `API_ORIGIN` 环境变量覆盖（默认 `http://localhost:8000`，Docker Compose 注入 `http://api:8000`）。
- 后端启动方式见仓库根目录 README。

## 结构

- `src/app/` — 路由：`/` 总览驾驶舱、`/market` 市场仪表盘、`/optimizer`、`/retirement`、`/profiles`（含 `/profiles/[id]` 客户枢纽）、`/advisor`、`/ips`、`/deliverables` 交付物中心（含 `/deliverables/[type]/[id]` 查看器）、`/monitoring` 组合监控；`src/app/api/` 为 FastAPI 的同源代理（JSON / SSE / 文件流）。
- `src/components/ui/` — 设计系统组件库（Button、Panel、Chip、Segmented、Table、Icon 等），令牌定义在 `src/app/globals.css`（`@theme`）。
- `src/components/` — 应用外壳（app-shell）、客户上下文（client-context）、各页面工作区组件。
- `src/lib/` — 类型化 API 客户端、SSE 读取器、格式化工具。

> 注意：本项目的 Next.js 版本与训练语料中的旧版有破坏性差异，改动路由/字体/数据 API 前先查 `node_modules/next/dist/docs/`（见 AGENTS.md）。
