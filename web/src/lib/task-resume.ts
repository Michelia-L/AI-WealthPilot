/**
 * Active background-task handles (sessionStorage). Workspaces save the task id
 * when a task starts so they can reconnect to its SSE stream after client-side
 * navigation unmounts them — the server-side task runs independently and its
 * events are persisted, so reconnecting replays the full sequence.
 */

/** Kinds of async workspaces that support resume. */
export type TaskKind = "ips" | "portfolio";

/** Thrown when the server no longer knows a saved task id (404). */
export class TaskGoneError extends Error {
  constructor() {
    super("任务不存在或服务已重启");
    this.name = "TaskGoneError";
  }
}

function storageKey(kind: TaskKind): string {
  return `wealthpilot:active-task:${kind}`;
}

export function saveActiveTask(kind: TaskKind, taskId: string): void {
  try {
    sessionStorage.setItem(storageKey(kind), taskId);
  } catch {
    // sessionStorage unavailable — resume is best-effort
  }
}

export function loadActiveTask(kind: TaskKind): string | null {
  try {
    return sessionStorage.getItem(storageKey(kind));
  } catch {
    return null;
  }
}

export function clearActiveTask(kind: TaskKind): void {
  try {
    sessionStorage.removeItem(storageKey(kind));
  } catch {
    // ignore
  }
}
