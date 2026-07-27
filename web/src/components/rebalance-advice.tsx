"use client";

import { useRef, useState } from "react";
import { readSseStream } from "@/lib/sse";
import { useT } from "@/components/locale-context";
import { useClient } from "./client-context";
import Markdown from "./markdown";
import ReasoningSection from "./reasoning-section";
import { Button, EmptyState, Icon, Panel } from "./ui";

/**
 * AI 调仓建议（P12）—— 基于监控结果（漂移/越带/复衡交易）的
 * DeepSeek 流式解读。画像上下文取全局当前客户（若已选择）。
 */
export default function RebalanceAdvice({ documentId }: { documentId: string }) {
  const { clientId } = useClient();
  const t = useT();
  const [text, setText] = useState("");
  const [reasoning, setReasoning] = useState("");
  const [reasoningTokens, setReasoningTokens] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [started, setStarted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [usage, setUsage] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  async function generate() {
    setBusy(true);
    setStarted(true);
    setError(null);
    setText("");
    setReasoning("");
    setReasoningTokens(null);
    setUsage(null);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      const res = await fetch("/api/monitoring/advice", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ document_id: documentId, profile_id: clientId }),
        signal: ctrl.signal,
      });
      if (!res.ok || !res.body) {
        const data = await res.json().catch(() => null);
        throw new Error(
          data && typeof data.detail === "string"
            ? data.detail
            : t.monitoring.adviceRequestFailed(res.status)
        );
      }
      await readSseStream(res.body, (event) => {
        if (event.type === "token") {
          setText((prev) => prev + String(event.text ?? ""));
        } else if (event.type === "reasoning") {
          setReasoning((prev) => prev + String(event.text ?? ""));
        } else if (event.type === "done") {
          const rt = Number(event.reasoning_tokens ?? 0);
          if (rt > 0) setReasoningTokens(rt);
          const total = Number(event.total_tokens ?? 0);
          if (total > 0) {
            setUsage(
              `${event.model} · ${Number(event.prompt_tokens ?? 0).toLocaleString()} + ${Number(event.completion_tokens ?? 0).toLocaleString()} = ${total.toLocaleString()} tokens`
            );
          }
        } else if (event.type === "error") {
          setError(String(event.message ?? t.monitoring.adviceGenerateFailed));
        }
      });
    } catch (e) {
      if (!ctrl.signal.aborted) {
        setError(e instanceof Error ? e.message : String(e));
      }
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  }

  return (
    <Panel>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 text-sm font-medium text-mist-200">
          <Icon name="sparkle" size={15} className="text-gold-400" />
          {t.monitoring.adviceTitle}
        </h3>
        <div className="flex items-center gap-2">
          {busy ? (
            <Button
              variant="ghost"
              size="sm"
              icon="x"
              onClick={() => abortRef.current?.abort()}
            >
              {t.monitoring.adviceStop}
            </Button>
          ) : (
            <Button size="sm" icon="sparkle" onClick={generate}>
              {started
                ? t.monitoring.adviceRegenerate
                : t.monitoring.adviceGenerate}
            </Button>
          )}
        </div>
      </div>

      {!started ? (
        <EmptyState
          icon="sparkle"
          title={t.monitoring.adviceEmptyTitle}
          hint={t.monitoring.adviceEmptyHint}
        />
      ) : error ? (
        <div className="flex items-start gap-2.5 rounded-xl border border-cinnabar-500/25 bg-cinnabar-500/[0.08] px-4 py-3 text-sm text-cinnabar-300">
          <Icon name="warning" size={15} className="mt-0.5 text-cinnabar-400" />
          <span>{error}</span>
        </div>
      ) : (
        <div>
          <ReasoningSection
            text={reasoning}
            streaming={busy}
            reasoningTokens={reasoningTokens}
          />
          {text ? (
            <>
              <Markdown>{text}</Markdown>
              {busy && (
                <span className="animate-blink font-mono text-gold-400">▍</span>
              )}
            </>
          ) : (
            <div className="flex items-center gap-2 py-6 text-sm text-mist-500">
              <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-gold-400" />
              {t.monitoring.adviceStreaming}
            </div>
          )}
          {usage && !busy && (
            <div className="tnum mt-4 border-t border-white/[0.06] pt-3 font-mono text-[11px] text-mist-500">
              {usage}
            </div>
          )}
        </div>
      )}
    </Panel>
  );
}
