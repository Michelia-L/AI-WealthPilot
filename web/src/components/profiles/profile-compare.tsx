"use client";

import type { BiasItem, ProfileCompareResponse } from "@/lib/api";
import { fmtLocal, fmtMoney, fmtPct } from "@/lib/format";
import { useLocale, useT } from "@/components/locale-context";
import {
  Badge,
  Button,
  Icon,
  Panel,
  Table,
  TD,
  TH,
  THead,
  TR,
} from "@/components/ui";
import type { BadgeTone } from "@/components/ui";
import { RiskBadge } from "./shared";

const SEVERITY_TONES: Record<string, BadgeTone> = {
  high: "cinnabar",
  medium: "gold",
  low: "steel",
};

/** 单个行为偏差点：双语名称/描述 + 严重度徽章 + 建议。 */
function BiasCard({ bias }: { bias: BiasItem }) {
  return (
    <div className="rounded-xl border border-white/[0.06] bg-ink-850/50 p-4">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-mist-200">{bias.name}</span>
        <Badge tone={SEVERITY_TONES[bias.severity] ?? "mist"}>
          {bias.severity}
        </Badge>
      </div>
      <p className="mt-2 text-xs leading-relaxed text-mist-400">
        {bias.description}
      </p>
      <p className="mt-2 flex items-start gap-1.5 text-xs leading-relaxed text-gold-300/90">
        <Icon name="sparkle" size={12} className="mt-0.5" />
        {bias.recommendation}
      </p>
    </div>
  );
}

/** 画像对比结果 —— 汇总表 + 关键洞察 + 每客户行为偏差分析。 */
export default function ProfileCompare({
  result,
  onClose,
}: {
  result: ProfileCompareResponse;
  onClose: () => void;
}) {
  const t = useT();
  const { locale } = useLocale();
  return (
    <Panel>
      <div className="flex items-center justify-between">
        <h3 className="font-display text-lg text-mist-100">
          {t.profiles.compareTitle}{" "}
          <span className="font-sans text-sm font-normal text-mist-500">
            — {result.profiles.map((p) => p.name).join(" vs ")} ·{" "}
            {fmtLocal(result.comparison_date)}
          </span>
        </h3>
        <Button variant="ghost" size="sm" icon="x" onClick={onClose}>
          {t.common.close}
        </Button>
      </div>

      <div className="mt-5">
        <Table className="min-w-[720px]">
          <THead>
            <tr>
              <TH>{t.profiles.colClient}</TH>
              <TH className="text-right">{t.profiles.colRiskScore}</TH>
              <TH>{t.profiles.colRiskLevel}</TH>
              <TH className="text-right">{t.profiles.colNetWorth}</TH>
              <TH className="text-right">{t.profiles.fieldAnnualIncome}</TH>
              <TH className="text-right">{t.profiles.colSavingsRate}</TH>
              <TH className="text-right">{t.profiles.colEmergencyFund}</TH>
              <TH className="text-right">{t.profiles.colBiasCount}</TH>
            </tr>
          </THead>
          <tbody>
            {result.profiles.map((p) => {
              const s = p.financial_summary;
              return (
                <TR key={p.id}>
                  <TD className="font-medium text-mist-100">{p.name}</TD>
                  <TD className="text-right font-mono">
                    {s.risk_score > 0 ? s.risk_score.toFixed(1) : "—"}
                  </TD>
                  <TD>
                    <RiskBadge
                      level={s.risk_level}
                      locale={locale}
                      unassessed={t.profiles.unassessed}
                    />
                  </TD>
                  <TD className="text-right font-mono">
                    {fmtMoney(s.net_worth)}
                  </TD>
                  <TD className="text-right font-mono">
                    {fmtMoney(s.annual_income)}
                  </TD>
                  <TD className="text-right font-mono">
                    {fmtPct(s.savings_rate, 1)}
                  </TD>
                  <TD className="text-right font-mono text-xs">
                    {t.profiles.monthsValue(s.emergency_fund_months)}
                  </TD>
                  <TD className="text-right font-mono">
                    {p.bias_count > 0 ? (
                      <span className="text-gold-300">{p.bias_count}</span>
                    ) : (
                      <span className="text-jade-400">0</span>
                    )}
                  </TD>
                </TR>
              );
            })}
          </tbody>
        </Table>
      </div>

      {result.insights.length > 0 && (
        <div className="mt-6">
          <h4 className="mb-2 text-[11px] font-medium tracking-[0.14em] text-mist-500 uppercase">
            {t.profiles.keyInsights}
          </h4>
          <ul className="space-y-1.5">
            {result.insights.map((insight, i) => (
              <li
                key={i}
                className="flex items-start gap-2 text-xs leading-relaxed text-mist-400"
              >
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-gold-400" />
                {insight}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-6 space-y-4">
        <h4 className="text-[11px] font-medium tracking-[0.14em] text-mist-500 uppercase">
          {t.profiles.biasAnalysis}
        </h4>
        {result.profiles.map((p) => (
          <div key={p.id}>
            <div className="mb-2 flex items-baseline gap-2">
              <span className="text-sm font-medium text-mist-200">{p.name}</span>
              {p.bias_count === 0 && (
                <span className="flex items-center gap-1 text-xs text-jade-400">
                  <Icon name="check" size={12} />
                  {t.profiles.noBiasesDetected}
                </span>
              )}
            </div>
            {p.bias_count > 0 && (
              <div className="grid gap-2 md:grid-cols-2">
                {p.biases.map((b) => (
                  <BiasCard key={b.bias_type} bias={b} />
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </Panel>
  );
}
