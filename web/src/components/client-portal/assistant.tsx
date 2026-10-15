"use client";

import { useRef, useState } from "react";
import { useT } from "@/components/locale-context";
import Markdown from "@/components/markdown";
import { Badge, Button, Panel } from "@/components/ui";
import type { ClientAssistantAnswer } from "@/lib/api/client-portal";

export default function ClientAssistant() {
  const t = useT().clientPortal;
  const inFlight = useRef(false);
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  const [answer, setAnswer] = useState<ClientAssistantAnswer | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function ask() {
    const question = message.trim();
    if (!question || inFlight.current) return;
    inFlight.current = true;
    setPending(true);
    setAnswer(null);
    setError(null);
    try {
      const response = await fetch("/api/me/assistant", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: question }),
      });
      const data = await response.json().catch(() => null);
      if (!response.ok || typeof data?.answer !== "string") {
        setError(
          typeof data?.detail === "string" ? data.detail : t.assistantFailed,
        );
        return;
      }
      setAnswer({ answer: data.answer, demo: data.demo === true });
    } catch {
      setError(t.assistantFailed);
    } finally {
      inFlight.current = false;
      setPending(false);
    }
  }

  return (
    <div className="space-y-6">
      <Panel>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void ask();
          }}
          className="space-y-4"
        >
          <label
            htmlFor="client-question"
            className="block text-sm font-medium text-mist-200"
          >
            {t.question}
          </label>
          <textarea
            id="client-question"
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            placeholder={t.questionPlaceholder}
            maxLength={8000}
            required
            disabled={pending}
            rows={5}
            aria-describedby="client-assistant-hint"
            className="w-full resize-y rounded-xl border border-white/10 bg-ink-950 p-4 text-sm leading-6 text-mist-100 focus:border-gold-500 focus:outline-none"
          />
          <p
            id="client-assistant-hint"
            className="text-xs leading-6 text-mist-400"
          >
            {t.assistantHint}
          </p>
          <Button
            type="submit"
            icon="sparkle"
            disabled={pending || !message.trim()}
          >
            {pending ? t.sending : t.send}
          </Button>
          {pending && (
            <p role="status" className="text-sm text-mist-400">
              {t.sending}
            </p>
          )}
          {error && (
            <p role="alert" className="text-sm text-cinnabar-300">
              {error}
            </p>
          )}
        </form>
      </Panel>
      <div aria-live="polite" aria-atomic="true">
        {answer && (
          <Panel>
            <div className="mb-4 flex flex-wrap items-center gap-3">
              <h2 className="font-display text-xl">{t.answer}</h2>
              {answer.demo && <Badge tone="gold">{t.demoAnswer}</Badge>}
            </div>
            <Markdown>{answer.answer}</Markdown>
          </Panel>
        )}
      </div>
    </div>
  );
}
