"use client";

import type { AssetClassInfo, BLViewInput } from "@/lib/api";
import { useT } from "@/components/locale-context";
import Button from "../ui/button";
import Icon from "../ui/icon";
import Panel from "../ui/panel";
import Slider from "../ui/slider";
import Toggle from "../ui/toggle";
import { NumInput, Select } from "../ui/field";
import Group from "./group";

interface BLConfigPanelProps {
  assets: string[];
  assetClasses: Record<string, AssetClassInfo>;
  blTau: string;
  setBlTau: (v: string) => void;
  blDelta: string;
  setBlDelta: (v: string) => void;
  equalWeights: boolean;
  setEqualWeights: (v: boolean) => void;
  marketWeights: Record<string, string>;
  setMarketWeights: React.Dispatch<
    React.SetStateAction<Record<string, string>>
  >;
  views: BLViewInput[];
  setViews: React.Dispatch<React.SetStateAction<BLViewInput[]>>;
}

/** Black-Litterman 配置面板 —— τ/δ、市值权重网格与动态观点行。 */
export default function BLConfigPanel({
  assets,
  assetClasses,
  blTau,
  setBlTau,
  blDelta,
  setBlDelta,
  equalWeights,
  setEqualWeights,
  marketWeights,
  setMarketWeights,
  views,
  setViews,
}: BLConfigPanelProps) {
  const t = useT();

  function addView() {
    setViews((prev) => [
      ...prev,
      {
        view_type: "absolute",
        asset_long: assets[0],
        asset_short: null,
        expected_return: 0.1,
        confidence: 70,
      },
    ]);
  }

  function updateView(i: number, patch: Partial<BLViewInput>) {
    setViews((prev) => prev.map((v, j) => (j === i ? { ...v, ...patch } : v)));
  }

  function removeView(i: number) {
    setViews((prev) => prev.filter((_, j) => j !== i));
  }

  return (
    <Panel innerClassName="space-y-5 p-5">
      <div className="text-[11px] font-medium tracking-[0.18em] text-gold-400/90 uppercase">
        {t.optimizer.blConfig}
      </div>

      <div className="grid gap-5 md:grid-cols-3">
        <Group label={t.optimizer.blTau}>
          <NumInput
            aria-label={t.optimizer.blTau}
            step="0.005"
            min="0.01"
            max="0.1"
            value={blTau}
            onChange={(e) => setBlTau(e.target.value)}
            className="w-28"
          />
        </Group>
        <Group label={t.optimizer.blDelta}>
          <NumInput
            aria-label={t.optimizer.blDelta}
            step="0.5"
            min="1"
            max="10"
            value={blDelta}
            onChange={(e) => setBlDelta(e.target.value)}
            className="w-28"
          />
        </Group>
        <Group label={t.optimizer.marketWeights}>
          <div className="pt-1.5">
            <Toggle
              checked={equalWeights}
              onChange={setEqualWeights}
              label={
                equalWeights ? t.optimizer.equalWeight : t.optimizer.customWeight
              }
            />
          </div>
        </Group>
      </div>

      {!equalWeights && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {assets.map((k) => (
            <div
              key={k}
              className="flex items-center gap-2 text-xs text-mist-400"
            >
              <span className="w-28 truncate">{assetClasses[k].name}</span>
              <NumInput
                aria-label={t.optimizer.marketWeightAria(assetClasses[k].name)}
                step="1"
                min="0"
                placeholder={(100 / assets.length).toFixed(0)}
                value={marketWeights[k] ?? ""}
                onChange={(e) =>
                  setMarketWeights((prev) => ({
                    ...prev,
                    [k]: e.target.value,
                  }))
                }
                className="w-20 px-2 py-1.5 text-xs"
              />
              %
            </div>
          ))}
        </div>
      )}

      <div>
        <div className="mb-2.5 flex items-center justify-between">
          <span className="text-[11px] font-medium tracking-[0.14em] text-mist-500 uppercase">
            {t.optimizer.investorViews(views.length)}
          </span>
          <Button variant="secondary" size="sm" icon="plus" onClick={addView}>
            {t.optimizer.addView}
          </Button>
        </div>

        {views.length === 0 && (
          <p className="text-xs leading-5 text-mist-500">
            {t.optimizer.viewsEmptyHint}
          </p>
        )}

        <div className="space-y-2">
          {views.map((v, i) => (
            <div
              key={i}
              className="flex flex-wrap items-center gap-2.5 rounded-xl border border-white/[0.06] bg-white/[0.02] p-3 text-sm"
            >
              <div className="w-24">
                <Select
                  aria-label={t.optimizer.viewTypeAria}
                  value={v.view_type}
                  onChange={(e) =>
                    updateView(i, {
                      view_type: e.target.value as "absolute" | "relative",
                    })
                  }
                  className="py-1.5 text-xs"
                >
                  <option value="absolute">{t.optimizer.viewAbsolute}</option>
                  <option value="relative">{t.optimizer.viewRelative}</option>
                </Select>
              </div>

              <div className="w-44 max-w-full">
                <Select
                  aria-label={t.optimizer.longAssetAria}
                  value={v.asset_long}
                  onChange={(e) => updateView(i, { asset_long: e.target.value })}
                  className="py-1.5 text-xs"
                >
                  {assets.map((k) => (
                    <option key={k} value={k}>
                      {assetClasses[k].name}
                    </option>
                  ))}
                </Select>
              </div>

              {v.view_type === "relative" && (
                <>
                  <span className="text-xs text-mist-500">
                    {t.optimizer.outperforms}
                  </span>
                  <div className="w-44 max-w-full">
                    <Select
                      aria-label={t.optimizer.shortAssetAria}
                      value={v.asset_short ?? ""}
                      onChange={(e) =>
                        updateView(i, { asset_short: e.target.value })
                      }
                      className="py-1.5 text-xs"
                    >
                      {assets
                        .filter((k) => k !== v.asset_long)
                        .map((k) => (
                          <option key={k} value={k}>
                            {assetClasses[k].name}
                          </option>
                        ))}
                    </Select>
                  </div>
                </>
              )}

              <span className="flex items-center gap-1.5 text-xs text-mist-400">
                {v.view_type === "absolute"
                  ? t.optimizer.expectedReturn
                  : t.optimizer.excessReturn}
                <NumInput
                  aria-label={t.optimizer.viewReturnAria}
                  step="1"
                  value={Math.round(v.expected_return * 100)}
                  onChange={(e) =>
                    updateView(i, {
                      expected_return:
                        (parseFloat(e.target.value) || 0) / 100,
                    })
                  }
                  className="w-20 px-2 py-1.5 text-xs"
                />
                %
              </span>

              <span className="flex items-center gap-2 text-xs text-mist-400">
                {t.optimizer.confidence}
                <Slider
                  value={v.confidence}
                  min={10}
                  max={100}
                  step={5}
                  onChange={(n) => updateView(i, { confidence: n })}
                  className="w-24"
                />
                <span className="tnum w-10 font-mono text-mist-200">
                  {v.confidence}%
                </span>
              </span>

              <button
                type="button"
                onClick={() => removeView(i)}
                aria-label={t.optimizer.deleteViewAria}
                className="ml-auto rounded-full p-1.5 text-mist-500 transition-colors duration-300 ease-luxe hover:bg-white/[0.05] hover:text-cinnabar-300"
              >
                <Icon name="x" size={14} />
              </button>
            </div>
          ))}
        </div>
      </div>
    </Panel>
  );
}
