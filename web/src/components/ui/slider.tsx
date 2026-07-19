"use client";

import { cx } from "@/lib/cx";

interface SliderProps {
  label?: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (value: number) => void;
  format?: (value: number) => string;
  className?: string;
}

/** 滑杆 —— 年龄、收益率、模拟次数等连续数值输入。 */
export default function Slider({
  label,
  value,
  min,
  max,
  step = 1,
  onChange,
  format,
  className,
}: SliderProps) {
  return (
    <div className={className}>
      {label && (
        <div className="mb-2 flex items-baseline justify-between">
          <span className="text-xs text-mist-400">{label}</span>
          <span className="tnum font-mono text-sm text-gold-300">
            {format ? format(value) : value}
          </span>
        </div>
      )}
      <input
        type="range"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(e) => onChange(Number(e.target.value))}
        className={cx(
          "h-1.5 w-full cursor-pointer appearance-none rounded-full bg-ink-700/80 outline-none",
          "[&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:border [&::-webkit-slider-thumb]:border-gold-300/60 [&::-webkit-slider-thumb]:bg-gold-400 [&::-webkit-slider-thumb]:shadow-[0_0_14px_rgb(201_164_92/0.45)] [&::-webkit-slider-thumb]:transition-transform [&::-webkit-slider-thumb]:duration-300 [&::-webkit-slider-thumb]:hover:scale-110",
          "[&::-moz-range-thumb]:h-4 [&::-moz-range-thumb]:w-4 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:border [&::-moz-range-thumb]:border-gold-300/60 [&::-moz-range-thumb]:bg-gold-400"
        )}
      />
    </div>
  );
}
