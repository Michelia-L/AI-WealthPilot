"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useSyncExternalStore,
} from "react";

interface ClientContextValue {
  clientId: number | null;
  clientName: string | null;
  select: (id: number, name: string) => void;
  clear: () => void;
}

const ClientContext = createContext<ClientContextValue | null>(null);
const STORAGE_KEY = "wealthpilot.activeClient";

interface ActiveClient {
  id: number;
  name: string;
}

/*
 * localStorage 作为外部 store，经 useSyncExternalStore 订阅：
 * SSR 与首帧水合返回 null（与服务端一致），水合后读取本地持久值。
 */
const listeners = new Set<() => void>();
let snapshot: ActiveClient | null | undefined; // undefined = 尚未读取

function getSnapshot(): ActiveClient | null {
  if (snapshot !== undefined) return snapshot;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    snapshot = raw ? (JSON.parse(raw) as ActiveClient) : null;
  } catch {
    snapshot = null;
  }
  return snapshot;
}

const getServerSnapshot = (): ActiveClient | null => null;

function subscribe(callback: () => void): () => void {
  listeners.add(callback);
  return () => {
    listeners.delete(callback);
  };
}

function write(next: ActiveClient | null) {
  snapshot = next;
  try {
    if (next) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    /* 持久化失败时仅保留内存态 */
  }
  listeners.forEach((l) => l());
}

/**
 * 全局客户上下文 —— 顾问工作站的"当前服务对象"。
 * 选择持久化到 localStorage，advisor / ips 等页面读取作为默认选中。
 */
export function ClientProvider({ children }: { children: React.ReactNode }) {
  const active = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  const select = useCallback((id: number, name: string) => {
    write({ id, name });
  }, []);

  const clear = useCallback(() => {
    write(null);
  }, []);

  const value = useMemo<ClientContextValue>(
    () => ({
      clientId: active?.id ?? null,
      clientName: active?.name ?? null,
      select,
      clear,
    }),
    [active, select, clear]
  );

  return (
    <ClientContext.Provider value={value}>{children}</ClientContext.Provider>
  );
}

export function useClient(): ClientContextValue {
  const ctx = useContext(ClientContext);
  if (!ctx) throw new Error("useClient must be used within ClientProvider");
  return ctx;
}
