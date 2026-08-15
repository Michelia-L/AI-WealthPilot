"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type {
  OptimizeMethod,
  OptimizeRequest,
  OptimizeResponse,
} from "@/lib/api";
import { readSseStream } from "@/lib/sse";
import {
  TaskGoneError,
  clearActiveTask,
  loadActiveTask,
  saveActiveTask,
} from "@/lib/task-resume";
import { useT } from "@/components/locale-context";

/**
 * Execution side of the optimizer workspace: sync/async run, SSE progress
 * streaming, and resuming an unfinished task on mount (the server-side task
 * keeps running across page switches; we reconnect by the task_id persisted
 * in sessionStorage and the backend replays the persisted event log).
 */
export function useOptimizeRun({
  buildBody,
  method,
}: {
  buildBody: () => OptimizeRequest;
  method: OptimizeMethod;
}) {
  const t = useT();

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<OptimizeResponse | null>(null);
  const [progressLabel, setProgressLabel] = useState<string | null>(null);

  // 当前事件流的取消句柄：切页卸载时断开（服务端任务独立运行，重挂载后凭
  // sessionStorage 里的 task_id 重连，后端会从持久化事件完整回放）。
  const streamAbort = useRef<AbortController | null>(null);

  /** Open the task event stream and pump it; resolves with the final result. */
  const streamTaskEvents = useCallback(
    async (
      taskId: string,
      signal: AbortSignal,
      onOpen?: () => void
    ): Promise<OptimizeResponse> => {
      const eventsRes = await fetch(`/api/portfolio/tasks/${taskId}/events`, {
        signal,
      });
      if (!eventsRes.ok || !eventsRes.body) {
        if (eventsRes.status === 404) {
          clearActiveTask("portfolio");
          throw new TaskGoneError();
        }
        const err = await eventsRes.json().catch(() => null);
        throw new Error(
          err && typeof err.detail === "string"
            ? err.detail
            : t.optimizer.progressUnavailable
        );
      }
      onOpen?.();
      let finalResult: OptimizeResponse | null = null;
      let streamError: string | null = null;
      await readSseStream(eventsRes.body, (event) => {
        if (event.type === "node") {
          setProgressLabel(String(event.label ?? ""));
        } else if (event.type === "done") {
          finalResult = event.result as OptimizeResponse;
          clearActiveTask("portfolio");
        } else if (event.type === "error") {
          streamError = String(event.message ?? t.optimizer.optimizeFailed);
          clearActiveTask("portfolio");
        }
      });
      if (streamError) throw new Error(streamError);
      if (!finalResult) throw new Error(t.optimizer.streamEnded);
      return finalResult;
    },
    [t]
  );

  // 挂载时恢复未完成的任务（切页返回的场景）：重连事件流重建进度与结果。
  useEffect(() => {
    const taskId = loadActiveTask("portfolio");
    if (!taskId) return;
    const controller = new AbortController();
    streamAbort.current = controller;
    void (async () => {
      try {
        const result = await streamTaskEvents(taskId, controller.signal, () => {
          // fetch 返回后的异步边界里再 setState，避免 effect 内同步 setState
          setLoading(true);
          setError(null);
          setProgressLabel(null);
        });
        setResult(result);
      } catch (e) {
        if (e instanceof TaskGoneError || controller.signal.aborted) return;
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
          setProgressLabel(null);
        }
      }
    })();
    return () => controller.abort();
  }, [streamTaskEvents]);

  // 卸载时断开事件流（任务在服务端继续，句柄保留供重连）
  useEffect(() => () => streamAbort.current?.abort(), []);

  /** Resampled MVO path: async task + SSE progress (minute-level compute). */
  async function runAsync(
    body: OptimizeRequest,
    signal: AbortSignal
  ): Promise<OptimizeResponse> {
    const res = await fetch("/api/portfolio/optimize/async", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(
        typeof data.detail === "string"
          ? data.detail
          : t.optimizer.createTaskFailed(res.status)
      );
    }
    saveActiveTask("portfolio", String(data.task_id));
    return streamTaskEvents(String(data.task_id), signal);
  }

  async function run() {
    const controller = new AbortController();
    streamAbort.current?.abort();
    streamAbort.current = controller;
    setLoading(true);
    setError(null);
    setProgressLabel(null);
    try {
      const body = buildBody();
      if (method === "resampled") {
        setResult(await runAsync(body, controller.signal));
      } else {
        const res = await fetch("/api/portfolio/optimize", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const data = await res.json();
        if (!res.ok) {
          throw new Error(
            typeof data.detail === "string"
              ? data.detail
              : t.optimizer.requestFailed(res.status)
          );
        }
        setResult(data as OptimizeResponse);
      }
    } catch (e) {
      if (controller.signal.aborted) return;
      setError(e instanceof Error ? e.message : String(e));
      setResult(null);
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false);
        setProgressLabel(null);
      }
    }
  }

  return { loading, error, result, progressLabel, run };
}
