"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * Markdown renderer for LLM-generated reports (advisor, IPS).
 * 组件映射到「墨金私行」主题 —— 衬线标题、雾灰正文、金色锚点。
 */
export default function Markdown({ children }: { children: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        h1: (p) => (
          <h1
            className="font-display mt-8 mb-4 text-2xl text-mist-100"
            {...p}
          />
        ),
        h2: (p) => (
          <h2
            className="font-display mt-8 mb-3 border-b border-white/[0.07] pb-2.5 text-xl text-mist-100"
            {...p}
          />
        ),
        h3: (p) => (
          <h3 className="mt-6 mb-2 text-base font-semibold text-mist-200" {...p} />
        ),
        h4: (p) => (
          <h4 className="mt-4 mb-2 text-sm font-semibold text-mist-200" {...p} />
        ),
        p: (p) => <p className="mb-3 text-sm leading-7 text-mist-300" {...p} />,
        ul: (p) => (
          <ul className="mb-3 list-disc space-y-1.5 pl-5 text-sm text-mist-300" {...p} />
        ),
        ol: (p) => (
          <ol className="mb-3 list-decimal space-y-1.5 pl-5 text-sm text-mist-300" {...p} />
        ),
        li: (p) => <li className="leading-6" {...p} />,
        strong: (p) => <strong className="font-semibold text-mist-100" {...p} />,
        a: (p) => (
          <a
            className="text-gold-400 underline decoration-gold-500/40 underline-offset-2 transition-colors hover:text-gold-300"
            target="_blank"
            rel="noreferrer"
            {...p}
          />
        ),
        blockquote: (p) => (
          <blockquote
            className="mb-3 border-l-2 border-gold-500/50 pl-4 text-sm text-mist-400 italic"
            {...p}
          />
        ),
        code: ({ className, children, ...p }) => (
          <code
            className={`rounded bg-ink-800 px-1.5 py-0.5 font-mono text-xs text-gold-200 ${className ?? ""}`}
            {...p}
          >
            {children}
          </code>
        ),
        pre: (p) => (
          <pre
            className="mb-3 overflow-x-auto rounded-lg border border-white/[0.06] bg-ink-950 p-3.5 text-xs"
            {...p}
          />
        ),
        table: (p) => (
          <div className="mb-3 overflow-x-auto">
            <table className="w-full text-left text-xs" {...p} />
          </div>
        ),
        thead: (p) => (
          <thead
            className="bg-ink-800/60 text-[11px] tracking-wide text-mist-300 uppercase"
            {...p}
          />
        ),
        th: (p) => <th className="px-3 py-2 font-medium" {...p} />,
        td: (p) => (
          <td className="tnum border-t border-white/[0.05] px-3 py-2 text-mist-300" {...p} />
        ),
        hr: () => <hr className="my-6 border-white/[0.07]" />,
      }}
    >
      {children}
    </ReactMarkdown>
  );
}
