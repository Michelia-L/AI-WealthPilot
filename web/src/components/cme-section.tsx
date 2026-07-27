import { getCme } from "@/lib/api";
import { fmtPct } from "@/lib/format";
import { getDict } from "@/lib/i18n/server";
import { ApiOffline } from "@/components/api-offline";
import { Badge, type BadgeTone } from "./ui/chip";
import Panel from "./ui/panel";
import { Table, THead, TH, TR, TD } from "./ui/table";

const CACHE_STATUS_TONE: Record<string, BadgeTone> = {
  fresh: "jade",
  cached: "steel",
  stale: "gold",
  fallback: "cinnabar",
};

const REGIME_TONE: Record<string, BadgeTone> = {
  low: "jade",
  normal: "steel",
  elevated: "gold",
  high: "cinnabar",
};

/**
 * Capital Market Expectations table, computed by the Python CME engine
 * (historical stats blended with implied volatility).
 */
export async function CmeSection() {
  const t = await getDict();
  const data = await getCme();

  if (!data) {
    return <ApiOffline resource={t.market.offlineCme} />;
  }

  const { report } = data;

  return (
    <section>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <h2 className="font-display text-xl text-mist-100">
          {t.market.cmeTitle}{" "}
          <span className="font-sans text-sm font-normal text-mist-500">
            CME
          </span>
        </h2>
        <Badge tone={CACHE_STATUS_TONE[data.cache_status] ?? "cinnabar"} dot>
          {data.cache_status}
        </Badge>
        <span className="text-xs text-mist-500">
          {t.market.cmeMeta(
            report.as_of_date,
            fmtPct(report.risk_free_rate),
            report.risk_free_rate_source,
            report.data_lookback_years
          )}
        </span>
      </div>

      <Panel pad={false} innerClassName="overflow-hidden">
        <Table className="min-w-[760px]">
          <THead>
            <tr>
              <TH>{t.market.thAssetClass}</TH>
              <TH className="text-right">{t.market.thExpectedReturn}</TH>
              <TH className="text-right">{t.market.thAnnVol}</TH>
              <TH className="text-right">{t.market.thBlendedVol}</TH>
              <TH className="text-right">{t.market.thSharpe}</TH>
              <TH className="text-right">{t.market.thMaxDrawdown}</TH>
              <TH className="text-right">{t.market.thVolRegime}</TH>
            </tr>
          </THead>
          <tbody>
            {report.asset_classes.map((a) => (
              <TR key={a.ticker}>
                <TD>
                  <div className="font-medium text-mist-100">{a.name}</div>
                  <div className="font-mono text-xs text-mist-500">
                    {a.ticker}
                  </div>
                </TD>
                <TD className="text-right font-mono">
                  {fmtPct(a.expected_return)}
                </TD>
                <TD className="text-right font-mono">{fmtPct(a.volatility)}</TD>
                <TD className="text-right font-mono">
                  {fmtPct(a.blended_volatility)}
                </TD>
                <TD className="text-right font-mono">
                  {a.sharpe_ratio.toFixed(2)}
                </TD>
                <TD className="text-right font-mono text-cinnabar-400">
                  {fmtPct(a.max_drawdown)}
                </TD>
                <TD className="text-right">
                  {a.volatility_regime ? (
                    <Badge tone={REGIME_TONE[a.volatility_regime] ?? "steel"}>
                      {a.volatility_regime}
                    </Badge>
                  ) : (
                    <span className="text-mist-600">—</span>
                  )}
                </TD>
              </TR>
            ))}
          </tbody>
        </Table>
      </Panel>
    </section>
  );
}
