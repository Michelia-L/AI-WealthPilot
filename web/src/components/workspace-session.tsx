"use client";

import { useState } from "react";
import Button from "@/components/ui/button";
import { useT } from "@/components/locale-context";
import { LocaleSwitcher } from "@/components/app-shell";
import type { WorkspaceSession } from "@/lib/session";

export default function WorkspaceSessionControl({
  session,
  gate = false,
}: {
  session: WorkspaceSession | null;
  gate?: boolean;
}) {
  const t = useT();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);

  async function submit(body: Record<string, unknown>) {
    setBusy(true);
    setError(false);
    try {
      const res = await fetch("/api/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error();
      try {
        localStorage.removeItem("wealthpilot.activeClient");
      } catch { /* Storage may be disabled; the session still changed. */ }
      window.location.reload();
    } catch {
      setError(true);
      setBusy(false);
    }
  }

  const fields = "w-full rounded-lg border border-white/10 bg-ink-900 px-3 py-2 text-mist-100";
  return (
    <section className={gate ? "mx-auto my-24 w-full max-w-sm space-y-5 px-5" : "mt-3 space-y-2"}>
      {gate && (
        <>
          <h1 className="font-display text-2xl text-mist-100">{t.auth.title}</h1>
          <LocaleSwitcher />
        </>
      )}
      {!session ? (
        <form className="space-y-4" onSubmit={(event) => {
          event.preventDefault();
          const data = new FormData(event.currentTarget);
          void submit({ action: "login", email: data.get("email"), password: data.get("password") });
        }}>
          <label className="block text-sm text-mist-300">
            {t.auth.email}
            <input className={fields} name="email" type="email" autoComplete="username" required disabled={busy} />
          </label>
          <label className="block text-sm text-mist-300">
            {t.auth.password}
            <input className={fields} name="password" type="password" autoComplete="current-password" required disabled={busy} />
          </label>
          <Button type="submit" disabled={busy}>{t.auth.login}</Button>
          <Button variant="secondary" disabled={busy} onClick={() => void submit({ action: "demo" })}>
            {t.auth.demo}
          </Button>
        </form>
      ) : (
        <>
          {session.organizations.length === 0 ? (
            <p className="text-sm text-mist-300">{t.auth.noOrganization}</p>
          ) : session.organizations.length === 1 && session.organizationId ? (
            <p className="text-sm text-mist-300">{session.organizations[0].name}</p>
          ) : (
            <label className="block text-sm text-mist-300">
              {t.auth.organization}
              <select
                className={fields}
                aria-label={t.auth.organization}
                value={session.organizationId ?? ""}
                disabled={busy}
                onChange={(event) => void submit({ action: "organization", organization_id: event.target.value })}
              >
                <option value="" disabled>{t.auth.chooseOrganization}</option>
                {session.organizations.map((org) => <option key={org.id} value={org.id}>{org.name}</option>)}
              </select>
            </label>
          )}
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => void submit({ action: "logout" })}>
            {t.auth.logout}
          </Button>
        </>
      )}
      {error && <p role="alert" className="text-sm text-cinnabar-300">{t.auth.failed}</p>}
    </section>
  );
}
