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

      const layout: Record<string, unknown> = {
        ...figure.layout,
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
