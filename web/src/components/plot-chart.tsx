"use client";

import { useEffect, useRef } from "react";
import type { PlotlyFigure } from "@/lib/api";

interface PlotChartProps {
  figure: PlotlyFigure;
  height?: number;
}

/**
 * Thin client wrapper around plotly.js. The library is loaded lazily via
 * dynamic import (never on the server, code-split from the main bundle);
 * `Plotly.react` handles efficient updates on prop changes.
 *
 * 主题层：在不改 Python 端的前提下注入「墨金私行」布局默认值
 * （透明底、等宽字体、发丝网格线），Python 侧显式设置的值优先。
 */
export default function PlotChart({ figure, height = 520 }: PlotChartProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let disposed = false;
    const el = ref.current;
    if (!el) return;

    (async () => {
      const mod = await import("plotly.js-dist-min");
      const Plotly = mod.default ?? mod;
      if (disposed || !ref.current) return;

      const figureLayout = figure.layout ?? {};
      // 解析 next/font 生成的实际字体族，供 Plotly 的 SVG 文本使用
      const monoFont =
        getComputedStyle(document.documentElement)
          .getPropertyValue("--font-mono")
          .trim() || "ui-monospace, monospace";

      const axisDefaults = {
        gridcolor: "rgba(255,255,255,0.06)",
        zerolinecolor: "rgba(255,255,255,0.12)",
        linecolor: "rgba(255,255,255,0.16)",
      };

      const layout: Record<string, unknown> = {
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        font: { family: monoFont, color: "#94918a", size: 11 },
        ...figureLayout,
        xaxis: { ...axisDefaults, ...(figureLayout.xaxis ?? {}) },
        yaxis: { ...axisDefaults, ...(figureLayout.yaxis ?? {}) },
        autosize: true,
        height,
      };
      // Figures coming from Python may pin a fixed width — drop it so the
      // chart fills its container (responsive config handles resizes).
      delete layout.width;

      await Plotly.react(ref.current, figure.data, layout, {
        responsive: true,
        displaylogo: false,
      });
    })();

    return () => {
      disposed = true;
      void import("plotly.js-dist-min").then((mod) => {
        const Plotly = mod.default ?? mod;
        Plotly.purge(el);
      });
    };
  }, [figure, height]);

  return <div ref={ref} className="w-full" style={{ height }} />;
}
