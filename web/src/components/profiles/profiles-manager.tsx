"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type {
  InvestmentGoalInput,
  ProfileCompareResponse,
  ProfileDetailResponse,
  ProfilePayload,
  ProfileSummary,
  QuestionnaireResponse,
} from "@/lib/api";
import { detailToPayload } from "@/lib/api";
import { Button, ConfirmDialog, SectionHeader } from "@/components/ui";
import ProfileCompare from "./profile-compare";
import ProfileForm from "./profile-form";
import ProfileList from "./profile-list";
import { MAX_COMPARE } from "./shared";

const EMPTY_FORM: ProfilePayload = {
  name: "",
  age: 30,
  marital_status: "single",
  dependents: 0,
  financial: {
    annual_income: 0,
    annual_expenses: 0,
    investable_assets: 0,
    total_liabilities: 0,
    emergency_fund_months: 0,
  },
  goals: [],
  time_horizon_years: 10,
  is_multi_stage: false,
  liquidity_needs: 0,
  tax_status: "taxable",
  esg_preference: false,
  sector_restrictions: [],
  notes: "",
  risk_scores: { ability_score: 0, willingness_score: 0 },
  ability_answers: {},
  willingness_answers: {},
};

/**
 * 客户画像管理器 —— 客户端入口，持有全部状态并在 list / create / edit
 * 三种模式间切换。CRUD 经 Next 代理打到 FastAPI，操作后 router.refresh()
 * 重新拉取服务端渲染的列表。
 */
export default function ProfilesManager({
  initialProfiles,
  questionnaire,
  initialEdit = null,
}: {
  initialProfiles: ProfileSummary[] | null;
  questionnaire: QuestionnaireResponse | null;
  /** 深链（/profiles?edit=<id>）服务端预取的编辑目标，挂载即进入编辑模式。 */
  initialEdit?: { id: number; payload: ProfilePayload } | null;
}) {
  const router = useRouter();
  const [mode, setMode] = useState<"list" | "create" | "edit">(
    initialEdit ? "edit" : "list"
  );
  const [editingId, setEditingId] = useState<number | null>(
    initialEdit?.id ?? null
  );
  const [form, setForm] = useState<ProfilePayload>(
    initialEdit?.payload ?? EMPTY_FORM
  );
  const [restrictionsText, setRestrictionsText] = useState(
    initialEdit?.payload.sector_restrictions.join(", ") ?? ""
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [selected, setSelected] = useState<number[]>([]);
  const [comparing, setComparing] = useState(false);
  const [compareResult, setCompareResult] = useState<ProfileCompareResponse | null>(null);
  const [pendingDelete, setPendingDelete] = useState<{
    id: number;
    name: string;
  } | null>(null);

  function toggleSelect(id: number) {
    setSelected((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id);
      if (prev.length >= MAX_COMPARE) return prev; // API caps at MAX_COMPARE
      return [...prev, id];
    });
  }

  async function runCompare() {
    setComparing(true);
    setError(null);
    setCompareResult(null);
    try {
      const res = await fetch(`/api/profiles/compare?ids=${selected.join(",")}`);
      const data = await res.json();
      if (!res.ok) {
        throw new Error(typeof data.detail === "string" ? data.detail : "对比失败");
      }
      setCompareResult(data as ProfileCompareResponse);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setComparing(false);
    }
  }

  const set = <K extends keyof ProfilePayload>(key: K, value: ProfilePayload[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));
  const setFin = (key: keyof ProfilePayload["financial"], value: number) =>
    setForm((prev) => ({ ...prev, financial: { ...prev.financial, [key]: value } }));

  /** Toggle a questionnaire answer; clicking the selected option clears it. */
  const setAnswer = (
    track: "ability_answers" | "willingness_answers",
    questionKey: string,
    optionKey: string
  ) =>
    setForm((prev) => {
      const answers = { ...prev[track] };
      if (answers[questionKey] === optionKey) delete answers[questionKey];
      else answers[questionKey] = optionKey;
      return { ...prev, [track]: answers };
    });

  function startCreate() {
    setForm(EMPTY_FORM);
    setRestrictionsText("");
    setEditingId(null);
    setError(null);
    setMode("create");
  }

  async function startEdit(id: number) {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/profiles/${id}`);
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "加载失败");
      const payload = detailToPayload(data as ProfileDetailResponse);
      setForm(payload);
      setRestrictionsText(payload.sector_restrictions.join(", "));
      setEditingId(id);
      setMode("edit");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    setBusy(true);
    setError(null);
    const payload: ProfilePayload = {
      ...form,
      name: form.name.trim(),
      sector_restrictions: restrictionsText
        .split(/[,，]/)
        .map((s) => s.trim())
        .filter(Boolean),
    };
    try {
      const res = await fetch(
        mode === "edit" ? `/api/profiles/${editingId}` : "/api/profiles",
        {
          method: mode === "edit" ? "PUT" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }
      );
      const data = await res.json();
      if (!res.ok) {
        const detail = data.detail;
        throw new Error(
          typeof detail === "string"
            ? detail
            : Array.isArray(detail)
              ? detail.map((d: { msg?: string }) => d.msg ?? "校验失败").join("；")
              : `保存失败（HTTP ${res.status}）`
        );
      }
      setMode("list");
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function confirmRemove() {
    const target = pendingDelete;
    if (!target) return;
    setPendingDelete(null);
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/profiles/${target.id}`, { method: "DELETE" });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(typeof data.detail === "string" ? data.detail : "删除失败");
      }
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function importLegacy() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await fetch("/api/profiles/import", { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "导入失败");
      setNotice(
        `导入完成：发现 ${data.files_found} 个 JSON 文件，新增 ${data.imported} 条，跳过 ${data.skipped} 条。`
      );
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const setGoal = <K extends keyof InvestmentGoalInput>(
    idx: number,
    key: K,
    value: InvestmentGoalInput[K]
  ) =>
    setForm((prev) => ({
      ...prev,
      goals: prev.goals.map((g, i) => (i === idx ? { ...g, [key]: value } : g)),
    }));

  return (
    <>
      <SectionHeader
        eyebrow="Client Profiling"
        title="客户画像"
        description="IPS 框架客户信息管理：双轨风险评估取 min(能力, 意愿) 得出最终风险等级。"
        actions={
          mode === "list" ? (
            <Button icon="plus" onClick={startCreate}>
              新建画像
            </Button>
          ) : undefined
        }
      />

      {mode !== "list" ? (
        <ProfileForm
          mode={mode}
          form={form}
          restrictionsText={restrictionsText}
          onRestrictionsChange={setRestrictionsText}
          set={set}
          setFin={setFin}
          setAnswer={setAnswer}
          setGoal={setGoal}
          questionnaire={questionnaire}
          busy={busy}
          error={error}
          onSave={save}
          onCancel={() => setMode("list")}
        />
      ) : (
        <>
          <ProfileList
            profiles={initialProfiles}
            selected={selected}
            onToggleSelect={toggleSelect}
            comparing={comparing}
            onCompare={runCompare}
            busy={busy}
            notice={notice}
            error={error}
            onImport={importLegacy}
            onEdit={startEdit}
            onDelete={(p) => setPendingDelete({ id: p.id, name: p.name })}
            onCreate={startCreate}
          />
          {compareResult && (
            <ProfileCompare
              result={compareResult}
              onClose={() => setCompareResult(null)}
            />
          )}
        </>
      )}

      <ConfirmDialog
        open={pendingDelete !== null}
        danger
        title="删除客户画像"
        description={
          pendingDelete
            ? `确定删除画像「${pendingDelete.name}」？此操作不可撤销。`
            : undefined
        }
        confirmLabel="删除"
        onConfirm={confirmRemove}
        onCancel={() => setPendingDelete(null)}
      />
    </>
  );
}
