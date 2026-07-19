"use client";

import { useEffect, useRef, useState } from "react";
import { cx } from "@/lib/cx";

interface RevealProps {
  children: React.ReactNode;
  /** 进场延迟（毫秒），用于交错编排 */
  delay?: number;
  className?: string;
}

/**
 * 滚动进场 —— IntersectionObserver 触发一次性的沉稳上浮淡入，
 * 仅使用 transform / opacity，不重排布局。
 */
export default function Reveal({ children, delay = 0, className }: RevealProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [shown, setShown] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setShown(true);
          io.disconnect();
        }
      },
      { threshold: 0.06 }
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      style={{ transitionDelay: `${delay}ms` }}
      className={cx(
        "transition-all duration-700 ease-luxe",
        shown ? "translate-y-0 opacity-100" : "translate-y-5 opacity-0",
        className
      )}
    >
      {children}
    </div>
  );
}
