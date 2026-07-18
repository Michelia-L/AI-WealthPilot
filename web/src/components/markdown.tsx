"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * Markdown renderer for LLM-generated reports (advisor, IPS).
 * Components are mapped to the app's slate/amber dark theme — no
 * typography plugin, explicit classes keep the look consistent.
 */
export default function Markdown({ children }: { children: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        h1: (p) => <h1 className="mb-4 mt-6 text-xl font-bold text-slate-100" {...p} />,
        h2: (p) => (
          <h2 className="mb-3 mt-6 border-b border-slate-800 pb-2 text-lg font-semibold text-slate-100" {...p} />
        ),
        h3: (p) => <h3 className="mb-2 mt-4 text-base font-semibold text-slate-200" {...p} />,
        h4: (p) => <h4 className="mb-2 mt-3 text-sm font-semibold text-slate-200" {...p} />,
        p: (p) => <p className="mb-3 text-sm leading-6 text-slate-300" {...p} />,
        ul: (p) => <ul className="mb-3 list-disc space-y-1 pl-5 text-sm text-slate-300" {...p} />,
        ol: (p) => <ol className="mb-3 list-decimal space-y-1 pl-5 text-sm text-slate-300" {...p} />,
        li: (p) => <li className="leading-6" {...p} />,
        strong: (p) => <strong className="font-semibold text-slate-100" {...p} />,
        a: (p) => (
          <a className="text-amber-400 underline hover:text-amber-300" target="_blank" rel="noreferrer" {...p} />
        ),
        blockquote: (p) => (
          <blockquote className="mb-3 border-l-2 border-amber-500/50 pl-4 text-sm italic text-slate-400" {...p} />
        ),
        code: ({ className, children, ...p }) => (
          <code
            className={`rounded bg-slate-800 px-1 py-0.5 font-mono text-xs text-amber-200 ${className ?? ""}`}
            {...p}
          >
            {children}
          </code>
        ),
        pre: (p) => (
          <pre className="mb-3 overflow-x-auto rounded-lg border border-slate-800 bg-slate-950 p-3 text-xs" {...p} />
        ),
        table: (p) => (
          <div className="mb-3 overflow-x-auto">
            <table className="w-full text-left text-xs" {...p} />
          </div>
        ),
        thead: (p) => <thead className="bg-slate-800/60 text-slate-300" {...p} />,
        th: (p) => <th className="px-3 py-2 font-medium" {...p} />,
        td: (p) => <td className="border-t border-slate-800 px-3 py-2 text-slate-300" {...p} />,
        hr: () => <hr className="my-4 border-slate-800" />,
      }}
    >
      {children}
    </ReactMarkdown>
  );
}
