"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useSyncExternalStore } from "react";
import { usePathname } from "next/navigation";
import type { ProfileSummary } from "@/lib/api";

interface ClientContextValue {
  clientId: number | null;
  clientName: string | null;
  ready: boolean;
  taskScope: string;
  select: (id: number, name: string) => void;
  clear: () => void;
}

const ClientContext = createContext<ClientContextValue | null>(null);
const subscribeReady = () => () => {};

/** Store only an ID, scoped to the signed-in user and workspace in this tab. */
function createStore(scope: string) {
  const key = `wealthpilot.activeClient:${scope}`;
  const listeners = new Set<() => void>();
  let snapshot: number | null | undefined;
  return {
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => { listeners.delete(listener); };
    },
    getSnapshot() {
      if (snapshot !== undefined) return snapshot;
      try {
        const value = Number(sessionStorage.getItem(key));
        snapshot = Number.isSafeInteger(value) && value > 0 ? value : null;
      } catch { snapshot = null; }
      return snapshot;
    },
    write(id: number | null) {
      snapshot = id;
      try {
        if (id === null) sessionStorage.removeItem(key);
        else sessionStorage.setItem(key, String(id));
      } catch { /* Keep selection in memory when storage is unavailable. */ }
      listeners.forEach((listener) => listener());
    },
  };
}

const serverSnapshot = () => null;

export function ClientProvider({ children, profiles, scope }: {
  children: React.ReactNode;
  profiles: ProfileSummary[];
  scope: string;
}) {
  const store = useMemo(() => createStore(scope), [scope]);
  const storedId = useSyncExternalStore(store.subscribe, store.getSnapshot, serverSnapshot);
  const ready = useSyncExternalStore(subscribeReady, () => true, () => false);
  const pathname = usePathname();
  const routeId = pathname.match(/^\/profiles\/(\d+)\/?$/)?.[1];
  // A profile deep link is authoritative. Never expose stale or foreign IDs/names.
  const id = routeId ? Number(routeId) : storedId;
  const active = profiles.find((profile) => profile.id === id);
  useEffect(() => {
    if (!ready) return;
    if (routeId || (storedId !== null && !profiles.some((p) => p.id === storedId))) {
      store.write(active?.id ?? null);
    }
  }, [ready, routeId, storedId, profiles, active?.id, store]);
  const select = useCallback((id: number) => {
    if (profiles.some((profile) => profile.id === id)) store.write(id);
  }, [profiles, store]);
  const clear = useCallback(() => store.write(null), [store]);
  const value = useMemo<ClientContextValue>(() => ({
    clientId: active?.id ?? null,
    clientName: active?.name ?? null,
    ready,
    taskScope: `${scope}:${active?.id ?? "manual"}`,
    select,
    clear,
  }), [active, ready, scope, select, clear]);
  return <ClientContext.Provider value={value}>{children}</ClientContext.Provider>;
}

export function useClient(): ClientContextValue {
  const ctx = useContext(ClientContext);
  if (!ctx) throw new Error("useClient must be used within ClientProvider");
  return ctx;
}
