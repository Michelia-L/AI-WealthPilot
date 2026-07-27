"use client";

import type {
  InvestmentGoalInput,
  ProfilePayload,
  QuestionnaireResponse,
} from "@/lib/api";
import { MARITAL_STATUS_OPTIONS, TAX_STATUS_OPTIONS } from "@/lib/api";
import { useT } from "@/components/locale-context";
import {
  Button,
  Field,
  Icon,
  Input,
  NumInput,
  Panel,
  Segmented,
  Textarea,
  Toggle,
} from "@/components/ui";
import type { IconName } from "@/components/ui";
import RiskQuestionnaire from "./questionnaire";

const GOAL_PRIORITY_OPTIONS = [
  { value: "high" },
  { value: "medium" },
  { value: "low" },
] as const;

/** 分区眉标 —— 小字 eyebrow + 金色细线图标。 */
function SectionTitle({
  icon,
  children,
}: {
  icon: IconName;
  children: React.ReactNode;
}) {
  return (
    <h3 className="flex items-center gap-2 text-[11px] font-medium tracking-[0.14em] text-mist-500 uppercase">
      <Icon name={icon} size={13} className="text-gold-400" />
      {children}
    </h3>
  );
}

function NumField({
  label,
  value,
  onChange,
  min = 0,
  max,
  step = 1,
}: {
  label?: string;
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
}) {
  return (
    <Field label={label}>
      <NumInput
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Math.max(min, parseFloat(e.target.value) || 0))}
      />
    </Field>
  );
}

/**
 * 新建/编辑画像表单 —— 五个分区：基本信息、财务状况、投资目标（动态行）、
 * 投资约束与偏好、风险问卷。所有状态由 ProfilesManager 持有，本组件只负责呈现。
 */
export default function ProfileForm({
  mode,
  form,
  restrictionsText,
  onRestrictionsChange,
  set,
  setFin,
  setAnswer,
  setGoal,
  questionnaire,
  busy,
  error,
  onSave,
  onCancel,
}: {
  mode: "create" | "edit";
  form: ProfilePayload;
  restrictionsText: string;
  onRestrictionsChange: (v: string) => void;
  set: <K extends keyof ProfilePayload>(key: K, value: ProfilePayload[K]) => void;
  setFin: (key: keyof ProfilePayload["financial"], value: number) => void;
  setAnswer: (
    track: "ability_answers" | "willingness_answers",
    questionKey: string,
    optionKey: string
  ) => void;
  setGoal: <K extends keyof InvestmentGoalInput>(
    idx: number,
    key: K,
    value: InvestmentGoalInput[K]
  ) => void;
  questionnaire: QuestionnaireResponse | null;
  busy: boolean;
  error: string | null;
  onSave: () => void;
  onCancel: () => void;
}) {
  const setRiskScore = (key: "ability_score" | "willingness_score", v: number) =>
    set("risk_scores", { ...form.risk_scores, [key]: v });
  const t = useT();

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h2 className="font-display text-xl text-mist-100">
          {mode === "edit"
            ? t.profiles.editFormTitle(form.name)
            : t.profiles.createProfile}
        </h2>
        <Button variant="ghost" size="sm" icon="x" onClick={onCancel}>
          {t.common.cancel}
        </Button>
      </div>

      <Panel>
        <SectionTitle icon="users">{t.profiles.sectionBasicInfo}</SectionTitle>
        <div className="mt-4 grid gap-4 md:grid-cols-4">
          <Field label={t.profiles.fieldName}>
            <Input
              value={form.name}
              placeholder={t.profiles.namePlaceholder}
              onChange={(e) => set("name", e.target.value)}
            />
          </Field>
          <NumField
            label={t.profiles.fieldAge}
            value={form.age}
            min={18}
            max={100}
            onChange={(v) => set("age", Math.min(100, v))}
          />
          <Field label={t.profiles.fieldMaritalStatus}>
            <Segmented
              value={form.marital_status}
              options={MARITAL_STATUS_OPTIONS.map((o) => ({
                value: o.value,
                label: t.profiles.maritalLabel(o.value),
              }))}
              onChange={(v) => set("marital_status", v)}
            />
          </Field>
          <NumField
            label={t.profiles.fieldDependents}
            value={form.dependents}
            max={20}
            onChange={(v) => set("dependents", v)}
          />
        </div>
      </Panel>

      <Panel>
        <SectionTitle icon="banknote">
          {t.profiles.sectionFinancials}
        </SectionTitle>
        <div className="mt-4 grid gap-4 md:grid-cols-3">
          <NumField
            label={t.profiles.fieldAnnualIncome}
            value={form.financial.annual_income}
            step={10000}
            onChange={(v) => setFin("annual_income", v)}
          />
          <NumField
            label={t.profiles.fieldAnnualExpenses}
            value={form.financial.annual_expenses}
            step={10000}
            onChange={(v) => setFin("annual_expenses", v)}
          />
          <NumField
            label={t.profiles.fieldInvestableAssets}
            value={form.financial.investable_assets}
            step={10000}
            onChange={(v) => setFin("investable_assets", v)}
          />
          <NumField
            label={t.profiles.fieldTotalLiabilities}
            value={form.financial.total_liabilities}
            step={10000}
            onChange={(v) => setFin("total_liabilities", v)}
          />
          <NumField
            label={t.profiles.fieldEmergencyFundMonths}
            value={form.financial.emergency_fund_months}
            step={0.5}
            onChange={(v) => setFin("emergency_fund_months", v)}
          />
        </div>
      </Panel>

      <Panel>
        <div className="flex items-center justify-between">
          <SectionTitle icon="target">{t.profiles.sectionGoals}</SectionTitle>
          <Button
            variant="ghost"
            size="sm"
            icon="plus"
            onClick={() =>
              set("goals", [
                ...form.goals,
                { name: "", target_amount: 0, years: 10, priority: "medium" },
              ])
            }
          >
            {t.profiles.addGoal}
          </Button>
        </div>
        {form.goals.length === 0 && (
          <p className="mt-4 text-xs text-mist-500">{t.profiles.noGoalsYet}</p>
        )}
        <div className="mt-4 space-y-3">
          {form.goals.map((g, i) => (
            <div
              key={i}
              className="grid items-end gap-3 md:grid-cols-[2fr_1fr_1fr_1fr_auto]"
            >
              <Field label={i === 0 ? t.profiles.fieldGoalName : undefined}>
                <Input
                  value={g.name}
                  placeholder={t.profiles.goalNamePlaceholder}
                  onChange={(e) => setGoal(i, "name", e.target.value)}
                />
              </Field>
              <NumField
                label={i === 0 ? t.profiles.fieldTargetAmount : undefined}
                value={g.target_amount}
                step={100000}
                onChange={(v) => setGoal(i, "target_amount", v)}
              />
              <NumField
                label={i === 0 ? t.profiles.fieldYears : undefined}
                value={g.years}
                max={80}
                onChange={(v) => setGoal(i, "years", v)}
              />
              <Field label={i === 0 ? t.profiles.fieldPriority : undefined}>
                <Segmented
                  size="sm"
                  value={g.priority}
                  options={GOAL_PRIORITY_OPTIONS.map((o) => ({
                    value: o.value,
                    label: t.profiles.priorityShort(o.value),
                  }))}
                  onChange={(v) => setGoal(i, "priority", v)}
                />
              </Field>
              <Button
                variant="ghost"
                size="sm"
                icon="trash"
                aria-label={t.profiles.deleteGoalAria}
                className="hover:text-cinnabar-300"
                onClick={() => set("goals", form.goals.filter((_, j) => j !== i))}
              />
            </div>
          ))}
        </div>
      </Panel>

      <Panel>
        <SectionTitle icon="sliders">
          {t.profiles.sectionConstraints}
        </SectionTitle>
        <div className="mt-4 grid gap-4 md:grid-cols-3">
          <NumField
            label={t.profiles.fieldTimeHorizon}
            value={form.time_horizon_years}
            min={1}
            max={60}
            onChange={(v) => set("time_horizon_years", Math.max(1, v))}
          />
          <NumField
            label={t.profiles.fieldLiquidityNeeds}
            value={form.liquidity_needs}
            step={10000}
            onChange={(v) => set("liquidity_needs", v)}
          />
          <Field label={t.profiles.fieldTaxStatus}>
            <Segmented
              value={form.tax_status}
              options={TAX_STATUS_OPTIONS.map((o) => ({
                value: o.value,
                label: t.profiles.taxLabel(o.value),
              }))}
              onChange={(v) => set("tax_status", v)}
            />
          </Field>
        </div>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <Field label={t.profiles.fieldSectorRestrictions}>
            <Input
              value={restrictionsText}
              placeholder={t.profiles.sectorRestrictionsPlaceholder}
              onChange={(e) => onRestrictionsChange(e.target.value)}
            />
          </Field>
          <div className="flex items-end pb-2">
            <Toggle
              checked={form.esg_preference}
              onChange={(v) => set("esg_preference", v)}
              label={t.profiles.esgPreferenceLabel}
            />
          </div>
        </div>
        <div className="mt-4">
          <Field label={t.profiles.fieldNotes}>
            <Textarea
              value={form.notes}
              onChange={(e) => set("notes", e.target.value)}
            />
          </Field>
        </div>
      </Panel>

      <Panel>
        <SectionTitle icon="shield">
          {t.profiles.sectionQuestionnaire}
        </SectionTitle>
        <div className="mt-4">
          <RiskQuestionnaire
            questionnaire={questionnaire}
            form={form}
            onAnswer={setAnswer}
            onRiskScoreChange={setRiskScore}
          />
        </div>
      </Panel>

      <div className="flex items-center gap-4">
        <Button onClick={onSave} disabled={busy || !form.name.trim()}>
          {busy
            ? t.common.saving
            : mode === "edit"
              ? t.profiles.saveChanges
              : t.profiles.createProfile}
        </Button>
        {error && (
          <span className="flex items-center gap-1.5 text-sm text-cinnabar-400">
            <Icon name="warning" size={14} />
            {error}
          </span>
        )}
      </div>
    </div>
  );
}
