/** Shared panel shown when the FastAPI backend is unreachable. */
export function ApiOffline({ resource }: { resource: string }) {
  return (
    <div className="rounded-xl border border-amber-900/60 bg-amber-950/30 p-6 text-sm text-amber-200/90">
      <p className="font-medium">无法获取 {resource} — API 服务未响应。</p>
      <p className="mt-2 text-amber-200/70">
        请先启动后端：
        <code className="mx-1 rounded bg-amber-900/50 px-1.5 py-0.5 font-mono text-xs">
          uvicorn api.main:app --port 8000
        </code>
        或
        <code className="mx-1 rounded bg-amber-900/50 px-1.5 py-0.5 font-mono text-xs">
          docker compose up
        </code>
      </p>
    </div>
  );
}
