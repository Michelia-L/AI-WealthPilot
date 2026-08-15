"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { readSseStream } from "@/lib/sse";
import {
  TaskGoneError,
  clearActiveTask,
  loadActiveTask,
  saveActiveTask,
} from "@/lib/task-resume";
import { useT } from "@/components/locale-context";

export interface ProgressStep {
  node: string;
  label: string;
}

export interface DoneInfo {
  document_id: string;
  status: string;
  revision_count: number;
}

/**
 * Generation state machine for the IPS workspace: run the LangGraph task,
 * pump its SSE stream into a progress timeline, and resume an unfinished
 * task on mount (the server-side task survives page switches; we reconnect
 * by the task_id persisted in sessionStorage).
 *
 * `onTaskOpen` lets the host clear any document being viewed when a task
 * stream (re)attaches.
 */
export function useIpsGeneration({
  selectedId,
  maxRevisions,
  onTaskOpen,
}: {
  selectedId: number | null;
  maxRevisions: number;
  onTaskOpen: () => void;
}) {
  const router = useRouter();
  const t = useT();
  const [running, setRunning] = useState(false);
  const [steps, setSteps] = useState<ProgressStep[]>([]);
  const [doneInfo, setDoneInfo] = useState<DoneInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  // 当前事件流的取消句柄：切页卸载时断开（服务端任务独立运行，重挂载后凭
  // sessionStorage 里的 task_id 重连，后端会从持久化事件完整回放）。
  const streamAbort = useRef<AbortController | null>(null);

  /** Apply one task event to the progress UI; done/error release the saved handle. */
  function applyTaskEvent(event: Record<string, unknown>) {
    if (event.type === "node") {
      setSteps((prev) => [...prev, { node: String(event.node), label: String(event.label) }]);
    } else if (event.type === "done") {
      setDoneInfo({
        document_id: String(event.document_id),
        status: String(event.status ?? ""),
        revision_count: Number(event.revision_count ?? 0),
      });
      clearActiveTask("ips");
    } else if (event.type === "error") {
      setError(String(event.message ?? t.ips.generateFailed));
      clearActiveTask("ips");
    }
  }

  /** Open the task event stream and pump it until done/error/abort. */
  async function streamTaskEvents(
    taskId: string,
    signal: AbortSignal,
    onOpen?: () => void
  ) {
    const eventsRes = await fetch(`/api/ips/tasks/${taskId}/events`, { signal });
    if (!eventsRes.ok || !eventsRes.body) {
      if (eventsRes.status === 404) {
        clearActiveTask("ips");
        throw new TaskGoneError();
      }
      const err = await eventsRes.json().catch(() => null);
      throw new Error(err && typeof err.detail === "string" ? err.detail : t.ips.progressUnavailable);
    }
    onOpen?.();
    await readSseStream(eventsRes.body, applyTaskEvent);
  }

  function resetForStream() {
    setRunning(true);
    setSteps([]);
    setDoneInfo(null);
    setError(null);
    onTaskOpen();
  }

  // 挂载时恢复未完成的任务（切页返回的场景）：重连事件流重建进度时间线。
  useEffect(() => {
    const taskId = loadActiveTask("ips");
    if (!taskId) return;
    const controller = new AbortController();
    streamAbort.current = controller;
    void (async () => {
      try {
        // fetch 返回后的异步边界里再 setState，避免 effect 内同步 setState
        await streamTaskEvents(taskId, controller.signal, resetForStream);
        router.refresh();
      } catch (e) {
        if (e instanceof TaskGoneError || controller.signal.aborted) return;
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!controller.signal.aborted) setRunning(false);
      }
    })();
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 仅挂载时恢复一次
  }, []);

  // 卸载时断开事件流（任务在服务端继续，句柄保留供重连）
  useEffect(() => () => streamAbort.current?.abort(), []);

  async function generate() {
    if (selectedId === null) return;
    const controller = new AbortController();
    streamAbort.current?.abort();
    streamAbort.current = controller;
    resetForStream();

    try {
      const res = await fetch("/api/ips/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profile_id: selectedId, max_revisions: maxRevisions }),
        signal: controller.signal,
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(typeof data.detail === "string" ? data.detail : t.ips.createTaskFailed(res.status));
      }

      saveActiveTask("ips", String(data.task_id));
      await streamTaskEvents(String(data.task_id), controller.signal);
      router.refresh();
    } catch (e) {
      if (!controller.signal.aborted) {
        setError(e instanceof Error ? e.message : String(e));
      }
    } finally {
      if (!controller.signal.aborted) setRunning(false);
    }
  }

  return { running, steps, doneInfo, error, setError, generate };
}
