"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import type { HoldingSnapshotHistory, HoldingSnapshotInput } from "@/lib/api";
import { useT } from "@/components/locale-context";
import { fmtLocal, fmtPct } from "@/lib/format";
import { Button, Field, Input, NumInput, Panel, Select, Table, TD, TH, THead, TR, Textarea } from "@/components/ui";

type EntryRow = {
  id: number; asset: string; method: "amount" | "units";
  amount: string; quantity: string; price: string; cost: string; costDate: string;
};
const blankRow = (id: number, asset: string): EntryRow => ({
  id, asset, method: "amount", amount: "", quantity: "", price: "", cost: "", costDate: "",
});

export default function HoldingsWorkspace({ history }: { history: HoldingSnapshotHistory }) {
  const t = useT();
  const c = t.monitoring.holdings;
  const router = useRouter();
  const [refreshing, startTransition] = useTransition();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [asOf, setAsOf] = useState("");
  const [rows, setRows] = useState<EntryRow[]>([blankRow(0, history.assets[0]?.asset_class ?? "")]);
  const [selected, setSelected] = useState("");
  const [json, setJson] = useState("");
  const pending = saving || refreshing;
  const snapshot = history.snapshots.find((s) => String(s.id) === selected) ?? history.snapshots[0];
  const previous = history.snapshots.find((s) => s.id === snapshot?.previous_snapshot_id);
  const money = (n: number | null | undefined) => n == null ? "—" : n.toLocaleString(undefined, { maximumFractionDigits: 2 });
  const name = (asset: string) => {
    const option = history.assets.find((a) => a.asset_class === asset);
    return t.market.cmeAssetClassName(option?.key ?? null, asset);
  };

  function update(id: number, values: Partial<EntryRow>) {
    setRows((current) => current.map((r) => r.id === id ? { ...r, ...values } : r));
    setSaved(false);
  }

  async function save(payload: unknown) {
    setSaving(true); setError(""); setSaved(false);
    try {
      const response = await fetch(`/api/monitoring/${encodeURIComponent(history.document_id)}/holdings`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok) {
        setError(typeof result.detail === "string" ? result.detail : c.failed);
        return;
      }
      setSaved(true);
      setSelected(String(result.id));
      startTransition(() => router.refresh());
    } catch {
      setError(c.failed);
    } finally { setSaving(false); }
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    const payload: HoldingSnapshotInput = {
      as_of: asOf, base_currency: history.base_currency,
      holdings: rows.map((r) => ({
        asset_class: r.asset,
        ...(r.method === "amount"
          ? { market_value: r.amount === "" ? null : Number(r.amount) }
          : { quantity: r.quantity === "" ? null : Number(r.quantity), unit_price: r.price === "" ? null : Number(r.price) }),
        cost_basis: r.cost === "" ? null : Number(r.cost), cost_basis_date: r.costDate || null,
      })),
    };
    void save(payload);
  }

  function downloadTemplate() {
    const template = {
      as_of: asOf || new Date().toISOString().slice(0, 10), base_currency: history.base_currency,
      holdings: history.assets.map((a) => ({ asset_class: a.asset_class, market_value: 0, cost_basis: null, cost_basis_date: null })),
    };
    const url = URL.createObjectURL(new Blob([JSON.stringify(template, null, 2)], { type: "application/json" }));
    const link = document.createElement("a");
    link.href = url; link.download = "holdings-template.json"; link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <Panel>
      <h2 className="text-lg font-medium text-mist-100">{c.title}</h2>
      <p className="mt-2 text-xs leading-5 text-mist-400">{c.hint}</p>
      <form onSubmit={submit} className="mt-5 space-y-4">
        <fieldset disabled={pending} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={c.asOf}><Input type="date" required value={asOf} onChange={(e) => setAsOf(e.target.value)} /></Field>
            <Field label={c.currency}><Input readOnly value={history.base_currency} /></Field>
          </div>
          {rows.map((r, index) => (
            <fieldset key={r.id} className="rounded-xl border border-white/[0.08] p-4">
              <legend className="px-2 text-xs text-mist-400">{c.asset} {index + 1}</legend>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <Field label={c.asset}><Select value={r.asset} onChange={(e) => update(r.id, { asset: e.target.value })}>
                  {history.assets.map((a) => <option key={a.asset_class} value={a.asset_class}>{name(a.asset_class)}</option>)}
                </Select></Field>
                <Field label={c.method}><Select value={r.method} onChange={(e) => update(r.id, { method: e.target.value as EntryRow["method"] })}>
                  <option value="amount">{c.amount}</option><option value="units">{c.units}</option>
                </Select></Field>
                {r.method === "amount" ? (
                  <Field label={c.amount}><NumInput required min="0" step="any" value={r.amount} onChange={(e) => update(r.id, { amount: e.target.value })} /></Field>
                ) : <>
                  <Field label={c.quantity}><NumInput required min="0" step="any" value={r.quantity} onChange={(e) => update(r.id, { quantity: e.target.value })} /></Field>
                  <Field label={c.price}><NumInput required min="0" step="any" value={r.price} onChange={(e) => update(r.id, { price: e.target.value })} /></Field>
                </>}
                <Field label={c.cost}><NumInput min="0" step="any" value={r.cost} onChange={(e) => update(r.id, { cost: e.target.value })} /></Field>
                <Field label={c.costDate}><Input type="date" required={r.cost !== ""} max={asOf || undefined} value={r.costDate} onChange={(e) => update(r.id, { costDate: e.target.value })} /></Field>
              </div>
              <Button variant="ghost" size="sm" className="mt-2" disabled={rows.length === 1} onClick={() => setRows((current) => current.filter((row) => row.id !== r.id))}>{c.remove}</Button>
            </fieldset>
          ))}
          <div className="flex flex-wrap gap-3">
            <Button variant="secondary" disabled={rows.length >= history.assets.length} onClick={() => setRows((current) => [
              ...current, blankRow(Math.max(...current.map((r) => r.id)) + 1, history.assets.find((a) => !current.some((r) => r.asset === a.asset_class))?.asset_class ?? ""),
            ])}>{c.add}</Button>
            <Button type="submit">{pending ? c.saving : c.save}</Button>
          </div>
        </fieldset>
      </form>
      <details className="mt-5 border-t border-white/[0.08] pt-4">
        <summary className="cursor-pointer text-sm text-mist-200">{c.importTitle}</summary>
        <p className="my-3 text-xs text-mist-400">{c.importHint}</p>
        <Button variant="secondary" size="sm" onClick={downloadTemplate}>{c.template}</Button>
        <Field label={c.importData} className="my-3"><Textarea value={json} onChange={(e) => setJson(e.target.value)} className="min-h-40 font-mono" /></Field>
        <Button disabled={pending || !json.trim()} onClick={() => {
          let payload: unknown;
          try { payload = JSON.parse(json); } catch { setError(c.importFailed); setSaved(false); return; }
          void save(payload);
        }}>{c.importSave}</Button>
      </details>
      {error && <p role="alert" className="mt-4 text-sm text-cinnabar-300">{error}</p>}
      {saved && <p role="status" className="mt-4 text-sm text-jade-300">{c.saved}</p>}
      <section className="mt-6 space-y-4 border-t border-white/[0.08] pt-5">
        <h3 className="text-sm font-medium text-mist-100">{c.history}</h3>
        <p className="text-xs leading-5 text-mist-400">{c.comparisonHint}</p>
        {!snapshot ? <p className="text-sm text-mist-400">{c.empty}</p> : <>
          <Field label={c.choose}><Select value={String(snapshot.id)} onChange={(e) => setSelected(e.target.value)}>
            {history.snapshots.map((s) => <option key={s.id} value={s.id}>{s.as_of} · #{s.id} · {fmtLocal(s.created_at)}</option>)}
          </Select></Field>
          <div className="flex flex-wrap gap-4 text-xs text-mist-400">
            <span>{c.created}: {fmtLocal(snapshot.created_at)}</span>
            <span>{c.total}: {snapshot.base_currency} {money(snapshot.total_market_value)}</span>
            {previous && <span>{c.previous}: {previous.as_of} · #{previous.id} · {c.change}: {money(snapshot.total_market_value_change)}</span>}
          </div>
          <Table className="min-w-[900px]">
            <THead><tr>{[c.asset, c.amount, c.quantity, c.price, c.cost, c.costDate, c.weight, c.change, c.weightChange].map((label) => <TH key={label}>{label}</TH>)}</tr></THead>
            <tbody>{snapshot.holdings.map((h) => <TR key={h.asset_class}>
              <TD>{name(h.asset_class)}</TD><TD>{money(h.market_value)}</TD><TD>{money(h.quantity)}</TD>
              <TD>{money(h.unit_price)}</TD><TD>{money(h.cost_basis)}</TD><TD>{h.cost_basis_date ?? "—"}</TD>
              <TD>{fmtPct(h.weight, 1)}</TD><TD>{money(h.market_value_change)}</TD>
              <TD>{h.weight_change == null ? "—" : `${(h.weight_change * 100).toFixed(1)}pp`}</TD>
            </TR>)}</tbody>
          </Table>
        </>}
      </section>
    </Panel>
  );
}
