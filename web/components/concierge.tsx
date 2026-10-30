"use client";

import { MessageCircle, Send, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { tool } from "@/lib/client";
import type { ConciergeAnswer } from "@/lib/groundtime";

import { Button, Notice, Panel, Spinner } from "./ui";

const SUGGESTIONS = ["What can I do with the delay?", "I'm already at the airport", "Something to watch?"];

/** The traveller's concierge: a question in plain words, an answer from their own plan. */
export function Concierge({ onMoved }: { onMoved?: () => void }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<ConciergeAnswer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function ask(text: string) {
    const q = text.trim();
    if (!q || busy) return;
    setQuestion(q);
    setBusy(true);
    setError(null);
    setAnswer(null);
    try {
      const out = await tool<ConciergeAnswer>("ask", { question: q });
      setAnswer(out);
      // "I'm already at the airport" moves them, and the trip page should show it
      if (out.tools?.includes("set_position")) onMoved?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The concierge couldn't answer just now.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title="Ask the concierge" icon={<MessageCircle size={14} className="text-accent" />}>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          ask(question);
        }}
      >
        <label className="flex-1">
          <span className="sr-only">Your question</span>
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            maxLength={500}
            placeholder="Ask about your wait"
            className="h-10 w-full rounded-md border border-control bg-surface px-3 text-sm outline-none transition-colors focus:border-accent focus:ring-2 focus:ring-accent/20"
          />
        </label>
        <Button type="submit" tone="accent" disabled={busy || !question.trim()} className="h-10">
          {busy ? <Spinner /> : <Send size={14} />} Ask
        </Button>
      </form>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            type="button"
            disabled={busy}
            onClick={() => ask(s)}
            className="rounded-full border border-line px-3 py-1 text-xs text-[#4b4d50] transition-colors hover:bg-sunken disabled:opacity-60"
          >
            {s}
          </button>
        ))}
      </div>
      {error && (
        <div className="mt-4">
          <Notice tone="error">{error}</Notice>
        </div>
      )}
      {answer && !busy && (
        <div className="mt-4 rounded-lg bg-sunken p-4">
          <div className="flex flex-col gap-2 text-sm leading-relaxed">
            {answer.answer
              .split("\n")
              .filter((line) => line.trim())
              .map((line, i) => (
                <p key={i}>{line}</p>
              ))}
          </div>
          <p className="mt-3 flex items-center gap-1.5 text-[11px] text-muted">
            <ShieldCheck size={12} />
            {answer.source === "model"
              ? "The concierge's answer, checked against what the tools returned."
              : "Your checked plan, written out."}
          </p>
        </div>
      )}
    </Panel>
  );
}
