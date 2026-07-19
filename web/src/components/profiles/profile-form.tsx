"use client";

import type {
  InvestmentGoalInput,
  ProfilePayload,
  QuestionnaireResponse,
} from "@/lib/api";
import { MARITAL_STATUS_OPTIONS, TAX_STATUS_OPTIONS } from "@/lib/api";
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
  { value: "high", label: "高" },
  { value: "medium", label: "中" },
  { value: "low", label: "低" },
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

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h2 className="font-display text-xl text-mist-100">
          {mode === "edit" ? `编辑画像 · ${form.name || "…"}` : "新建画像"}
        </h2>
        <Button variant="ghost" size="sm" icon="x" onClick={onCancel}>
          取消
        </Button>
      </div>

      <Panel>
        <SectionTitle icon="users">基本信息</SectionTitle>
        <div className="mt-4 grid gap-4 md:grid-cols-4">
          <Field label="姓名">
            <Input
              value={form.name}
              placeholder="例如：张三"
              onChange={(e) => set("name", e.target.value)}
            />
          </Field>
          <NumField
            label="年龄"
            value={form.age}
            min={18}
            max={100}
            onChange={(v) => set("age", Math.min(100, v))}
          />
          <Field label="婚姻状况">
            <Segmented
              value={form.marital_status}
              options={MARITAL_STATUS_OPTIONS}
              onChange={(v) => set("marital_status", v)}
            />
          </Field>
          <NumField
            label="受抚养人数"
            value={form.dependents}
            max={20}
            onChange={(v) => set("dependents", v)}
          />
        </div>
      </Panel>

      <Panel>
        <SectionTitle icon="banknote">财务状况</SectionTitle>
        <div className="mt-4 grid gap-4 md:grid-cols-3">
          <NumField
            label="年收入"
            value={form.financial.annual_income}
            step={10000}
            onChange={(v) => setFin("annual_income", v)}
          />
          <NumField
            label="年支出"
            value={form.financial.annual_expenses}
            step={10000}
            onChange={(v) => setFin("annual_expenses", v)}
          />
          <NumField
            label="可投资资产"
            value={form.financial.investable_assets}
            step={10000}
            onChange={(v) => setFin("investable_assets", v)}
          />
          <NumField
            label="总负债"
            value={form.financial.total_liabilities}
            step={10000}
            onChange={(v) => setFin("total_liabilities", v)}
          />
          <NumField
            label="应急基金（月数）"
            value={form.financial.emergency_fund_months}
            step={0.5}
            onChange={(v) => setFin("emergency_fund_months", v)}
          />
        </div>
      </Panel>

      <Panel>
        <div className="flex items-center justify-between">
          <SectionTitle icon="target">投资目标</SectionTitle>
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
            添加目标
          </Button>
        </div>
        {form.goals.length === 0 && (
          <p className="mt-4 text-xs text-mist-500">暂无目标，点击右上角添加。</p>
        )}
        <div className="mt-4 space-y-3">
          {form.goals.map((g, i) => (
            <div
              key={i}
              className="grid items-end gap-3 md:grid-cols-[2fr_1fr_1fr_1fr_auto]"
            >
              <Field label={i === 0 ? "目标名称" : undefined}>
                <Input
                  value={g.name}
                  placeholder="例如：退休"
                  onChange={(e) => setGoal(i, "name", e.target.value)}
                />
              </Field>
              <NumField
                label={i === 0 ? "目标金额" : undefined}
                value={g.target_amount}
                step={100000}
                onChange={(v) => setGoal(i, "target_amount", v)}
              />
              <NumField
                label={i === 0 ? "年限" : undefined}
                value={g.years}
                max={80}
                onChange={(v) => setGoal(i, "years", v)}
              />
              <Field label={i === 0 ? "优先级" : undefined}>
                <Segmented
                  size="sm"
                  value={g.priority}
                  options={GOAL_PRIORITY_OPTIONS}
                  onChange={(v) => setGoal(i, "priority", v)}
                />
              </Field>
              <Button
                variant="ghost"
                size="sm"
                icon="trash"
                aria-label="删除目标"
                className="hover:text-cinnabar-300"
                onClick={() => set("goals", form.goals.filter((_, j) => j !== i))}
              />
            </div>
          ))}
        </div>
      </Panel>

      <Panel>
        <SectionTitle icon="sliders">投资约束与偏好</SectionTitle>
        <div className="mt-4 grid gap-4 md:grid-cols-3">
          <NumField
            label="投资期限（年）"
            value={form.time_horizon_years}
            min={1}
            max={60}
            onChange={(v) => set("time_horizon_years", Math.max(1, v))}
          />
          <NumField
            label="流动性需求（金额）"
            value={form.liquidity_needs}
            step={10000}
            onChange={(v) => set("liquidity_needs", v)}
          />
          <Field label="税务状态">
            <Segmented
              value={form.tax_status}
              options={TAX_STATUS_OPTIONS}
              onChange={(v) => set("tax_status", v)}
            />
          </Field>
        </div>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <Field label="行业限制（逗号分隔）">
            <Input
              value={restrictionsText}
              placeholder="例如：烟草, 军工"
              onChange={(e) => onRestrictionsChange(e.target.value)}
            />
          </Field>
          <div className="flex items-end pb-2">
            <Toggle
              checked={form.esg_preference}
              onChange={(v) => set("esg_preference", v)}
              label="ESG 偏好（环境/社会/治理）"
            />
          </div>
        </div>
        <div className="mt-4">
          <Field label="备注">
            <Textarea
              value={form.notes}
              onChange={(e) => set("notes", e.target.value)}
            />
          </Field>
        </div>
      </Panel>

      <Panel>
        <SectionTitle icon="shield">风险问卷</SectionTitle>
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
          {busy ? "保存中…" : mode === "edit" ? "保存修改" : "创建画像"}
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
