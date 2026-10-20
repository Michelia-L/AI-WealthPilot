import { Badge, EmptyState, Panel, type BadgeTone } from "@/components/ui";
import type { GoalFundingPlan } from "@/lib/api/goals";
import { fmtMoney, fmtPct } from "@/lib/format";
import type { Dictionary } from "@/lib/i18n/dictionaries";

const STATUS_TONE: Record<string, BadgeTone> = {
  covered: "gold",
  covered_with_savings: "steel",
  growth_required: "mist",
  needs_funding: "cinnabar",
};

function Metric({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap justify-between gap-x-4 gap-y-1">
      <dt className="text-mist-400">{label}</dt>
      <dd className="font-mono text-mist-100">{children}</dd>
    </div>
  );
}

/** Render backend estimates without recomputing financial rules in the browser. */
export default function GoalFundingCards({
  goals,
  t,
}: {
  goals: GoalFundingPlan[];
  t: Dictionary["goalTracking"];
}) {
  if (!goals.length)
    return <EmptyState icon="target" title={t.noGoals} hint={t.noGoalsHint} />;
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {goals.map((goal, index) => {
        const progress = goal.progress;
        // Cap only the visual bar; preserve coverage above 100% in the label.
        const barPercent = progress
          ? Math.min(100, Math.max(0, progress.funding_ratio * 100))
          : 0;
        return (
          <Panel key={index}>
            <article aria-label={goal.name}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <h3 className="min-w-0 break-words font-display text-xl text-mist-100">
                  {goal.name}
                </h3>
                <Badge>
                  {t.priority} · {Object.hasOwn(t.priorities, goal.priority)
                    ? t.priorities[goal.priority as keyof typeof t.priorities]
                    : goal.priority}
                </Badge>
              </div>
              <dl className="mt-5 space-y-3 text-sm">
                <Metric label={t.target}>{fmtMoney(goal.target_amount, "")}</Metric>
                <Metric label={t.horizon}>{t.years(goal.years)}</Metric>
              </dl>
              {progress ? (
                <>
                  <div className="mt-5 border-t border-white/[0.06] pt-4">
                    <div className="mb-2 flex flex-wrap justify-between gap-3 text-sm">
                      <span className="text-mist-400">{t.coverage}</span>
                      <span className="font-mono text-gold-300">
                        {fmtPct(progress.funding_ratio, 1)}
                      </span>
                    </div>
                    <div
                      role="progressbar"
                      aria-label={`${goal.name} · ${t.coverage}`}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-valuenow={barPercent}
                      aria-valuetext={fmtPct(progress.funding_ratio, 1)}
                      className="h-2 overflow-hidden rounded-full bg-ink-800"
                    >
                      <div
                        className="h-full rounded-full bg-gold-500"
                        style={{ width: `${barPercent}%` }}
                      />
                    </div>
                    <dl className="mt-4 space-y-3 text-sm">
                      <Metric label={t.budgetSource}>
                        {t.budgetSources[progress.allocation_method]}
                      </Metric>
                      <Metric label={t.budget}>
                        {fmtMoney(progress.allocated_assets, "")}
                      </Metric>
                      <Metric label={t.annualContribution}>
                        {fmtMoney(progress.annual_contribution, "")}
                      </Metric>
                      <Metric label={t.gap}>
                        {fmtMoney(progress.funding_gap, "")}
                      </Metric>
                      <Metric label={t.requiredReturn}>
                        {progress.required_return === null
                          ? t.unsolvedReturn
                          : fmtPct(progress.required_return, 2)}
                      </Metric>
                      <Metric label={t.zeroReturnYears}>
                        {progress.years_to_target_at_zero_return === null
                          ? t.beyondProjectionRange
                          : progress.years_to_target_at_zero_return === 0
                            ? t.alreadyCovered
                            : t.years(progress.years_to_target_at_zero_return)}
                      </Metric>
                    </dl>
                  </div>
                  <div className="mt-5">
                    <Badge tone={STATUS_TONE[progress.status]}>
                      {t.statuses[progress.status]}
                    </Badge>
                  </div>
                </>
              ) : (
                <p className="mt-5 text-sm leading-6 text-mist-400">{t.incomplete}</p>
              )}
            </article>
          </Panel>
        );
      })}
    </div>
  );
}
