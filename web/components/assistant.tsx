"use client";

import { Bot, Mic, Send, ShieldCheck, Square, Volume2, VolumeX, X } from "lucide-react";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { tool } from "@/lib/client";
import { assistantRoleFor, type AssistantAnswer, type AssistantRole } from "@/lib/groundtime";

import { useMe } from "./me";
import { cx, Spinner } from "./ui";

/** Fired after the assistant changes something a page shows (a traveller's position). */
export const CHANGED = "groundtime:changed";

const TITLES: Record<AssistantRole, string> = {
  traveller: "for your trip",
  crew: "for crew",
  customer_care: "for customer care",
  admin: "for admins",
};

const SUGGESTIONS: Record<AssistantRole, string[]> = {
  traveller: [
    "What can I do with the delay?",
    "I'm already at the airport",
    "Something to watch before boarding?",
    "When do I need to be at the gate?",
  ],
  crew: ["When is my next duty?", "Are any of my flights delayed?", "Where can I eat on my layover?"],
  customer_care: [
    "Which flights are delayed?",
    "Is KS434 late?",
    "How are KS434's passengers planned for?",
    "How do I record a delay?",
  ],
  admin: ["How many sign-ins are there?", "Whose passwords can I reset?", "How are accounts created?"],
};

type Turn = { role: "user" | "assistant"; text: string; source?: AssistantAnswer["source"] };

const VOICE_KEY = "groundtime.voice";

type Recognition = {
  lang: string;
  interimResults: boolean;
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
  start: () => void;
  stop: () => void;
};

/** The browser's own speech-to-text, where it has one (Chrome, Edge, Safari). */
function recognition(): Recognition | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as Record<string, (new () => Recognition) | undefined>;
  const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition;
  return Ctor ? new Ctor() : null;
}

/** The Groundtime assistant, in the corner of every page. It answers as the role of the page
 * it's opened on, with that role's tools, and only about Groundtime and air travel. Answers
 * can be read aloud by Amazon Polly; questions can be spoken where the browser supports it. */
export function Assistant() {
  const me = useMe();
  const path = usePathname();
  const role = assistantRoleFor(path);
  const allowed = role !== null && me.roles.includes(role);
  const [open, setOpen] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Read in the browser only; the closed button looks the same either way, so the server's
  // render still matches.
  const [voice, setVoice] = useState(() => {
    try {
      return typeof window !== "undefined" && localStorage.getItem(VOICE_KEY) === "1";
    } catch {
      return false; // storage blocked: speech stays off
    }
  });
  const [speaking, setSpeaking] = useState(false);
  const [listening, setListening] = useState(false);
  const [canListen] = useState(() => recognition() !== null);
  const player = useRef<HTMLAudioElement | null>(null);
  const listener = useRef<Recognition | null>(null);
  const end = useRef<HTMLDivElement | null>(null);
  const [shownFor, setShownFor] = useState<AssistantRole | null>(role);

  // A conversation belongs to one role: another page starts a new one.
  if (shownFor !== role) {
    setShownFor(role);
    setTurns([]);
    setError(null);
  }

  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [turns, busy]);

  const stopSpeaking = useCallback(() => {
    player.current?.pause();
    player.current = null;
    setSpeaking(false);
  }, []);

  useEffect(() => () => stopSpeaking(), [stopSpeaking]);

  function play(mp3: string) {
    stopSpeaking();
    const audio = new Audio(`data:audio/mpeg;base64,${mp3}`);
    player.current = audio;
    audio.onended = () => setSpeaking(false);
    setSpeaking(true);
    audio.play().catch(() => setSpeaking(false));
  }

  function toggleVoice() {
    const next = !voice;
    setVoice(next);
    if (!next) stopSpeaking();
    try {
      localStorage.setItem(VOICE_KEY, next ? "1" : "0");
    } catch {
      // not remembered; fine
    }
  }

  async function ask(text: string) {
    const q = text.trim();
    if (!q || busy || !role) return;
    stopSpeaking();
    setQuestion("");
    setError(null);
    const history = turns.slice(-6).map(({ role: who, text: said }) => ({ role: who, text: said }));
    setTurns((t) => [...t, { role: "user", text: q }]);
    setBusy(true);
    try {
      const out = await tool<AssistantAnswer>("ask", { question: q, role, history, voice });
      setTurns((t) => [...t, { role: "assistant", text: out.answer, source: out.source }]);
      if (out.audio_mp3) play(out.audio_mp3);
      if (out.tools.includes("set_position")) window.dispatchEvent(new Event(CHANGED));
    } catch (err) {
      setError(err instanceof Error ? err.message : "The assistant couldn't answer just now.");
    } finally {
      setBusy(false);
    }
  }

  function listen() {
    if (listening) {
      listener.current?.stop();
      return;
    }
    const r = recognition();
    if (!r) return;
    r.lang = "en-IN";
    r.interimResults = false;
    r.onresult = (e) => {
      const heard = e.results[0]?.[0]?.transcript ?? "";
      if (heard.trim()) ask(heard);
    };
    r.onend = () => setListening(false);
    r.onerror = () => setListening(false);
    listener.current = r;
    setListening(true);
    r.start();
  }

  if (!allowed || !role) return null;

  return (
    <>
      {!open && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-label="Open the Groundtime assistant"
          className="fixed bottom-5 right-5 z-40 inline-flex h-12 items-center gap-2 rounded-full bg-accent pl-4 pr-5 text-sm font-semibold text-white shadow-lg shadow-accent/30 transition-transform hover:scale-[1.03] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        >
          <Bot size={18} /> Ask Groundtime
        </button>
      )}

      {open && (
        <section
          role="dialog"
          aria-label="Groundtime assistant"
          className="fixed inset-x-0 bottom-0 z-50 flex max-h-[85vh] flex-col rounded-t-2xl border border-line bg-surface shadow-2xl sm:inset-x-auto sm:bottom-5 sm:right-5 sm:h-[36rem] sm:max-h-[calc(100vh-2.5rem)] sm:w-[25rem] sm:rounded-2xl"
        >
          <header className="flex items-center gap-2 border-b border-line px-4 py-3">
            <span className="grid h-8 w-8 place-items-center rounded-full bg-accent text-white">
              <Bot size={16} />
            </span>
            <div className="min-w-0 flex-1 leading-tight">
              <p className="text-sm font-semibold">Groundtime assistant</p>
              <p className="text-xs text-muted">{TITLES[role]}</p>
            </div>
            <button
              type="button"
              onClick={toggleVoice}
              aria-pressed={voice}
              title={voice ? "Answers are read aloud" : "Read answers aloud"}
              className={cx(
                "rounded-md p-2 transition-colors",
                voice ? "bg-accent-soft text-accent" : "text-muted hover:bg-sunken hover:text-foreground",
              )}
            >
              {voice ? <Volume2 size={16} /> : <VolumeX size={16} />}
            </button>
            <button
              type="button"
              onClick={() => {
                stopSpeaking();
                listener.current?.stop();
                setOpen(false);
              }}
              aria-label="Close"
              className="rounded-md p-2 text-muted hover:bg-sunken hover:text-foreground"
            >
              <X size={16} />
            </button>
          </header>

          <div className="flex-1 overflow-y-auto px-4 py-4" aria-live="polite">
            {turns.length === 0 ? (
              <div>
                <p className="text-sm text-muted">
                  Ask about {role === "traveller" ? "your trip and your wait" : role === "crew" ? "your duties and layovers" : role === "customer_care" ? "flights, delays and waiting passengers" : "accounts and roles"}, or about air travel with the airlines here.
                </p>
                <div className="mt-3 flex flex-col items-start gap-1.5">
                  {SUGGESTIONS[role].map((s) => (
                    <button
                      key={s}
                      type="button"
                      disabled={busy}
                      onClick={() => ask(s)}
                      className="rounded-full border border-line px-3 py-1.5 text-left text-xs text-[#4b4d50] transition-colors hover:bg-sunken disabled:opacity-60"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <ol className="flex flex-col gap-3">
                {turns.map((t, i) => (
                  <li key={i} className={cx("flex", t.role === "user" ? "justify-end" : "justify-start")}>
                    <div
                      className={cx(
                        "max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed",
                        t.role === "user" ? "rounded-br-sm bg-accent text-white" : "rounded-bl-sm bg-sunken",
                      )}
                    >
                      {t.text
                        .split("\n")
                        .filter((line) => line.trim())
                        .map((line, j) => (
                          <p key={j} className={j ? "mt-1.5" : undefined}>
                            {line}
                          </p>
                        ))}
                      {t.role === "assistant" && t.source !== "off_topic" && (
                        <p className="mt-2 flex items-center gap-1 text-[11px] text-muted">
                          <ShieldCheck size={11} />
                          {t.source === "model" ? "Checked against Groundtime's data" : "Written from Groundtime's data"}
                        </p>
                      )}
                    </div>
                  </li>
                ))}
                {busy && (
                  <li className="flex items-center gap-2 text-xs text-muted">
                    <Spinner /> Looking it up…
                  </li>
                )}
              </ol>
            )}
            {error && <p className="mt-3 text-xs text-critical">{error}</p>}
            <div ref={end} />
          </div>

          {speaking && (
            <button
              type="button"
              onClick={stopSpeaking}
              className="mx-4 mb-2 inline-flex items-center justify-center gap-1.5 rounded-md bg-sunken px-3 py-1.5 text-xs font-medium"
            >
              <Square size={11} /> Stop reading aloud
            </button>
          )}

          <form
            className="flex items-center gap-2 border-t border-line p-3"
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
                placeholder={listening ? "Listening…" : "Ask a question"}
                className="h-10 w-full rounded-full border border-control bg-surface px-4 text-sm outline-none transition-colors focus:border-accent focus:ring-2 focus:ring-accent/20"
              />
            </label>
            {canListen && (
              <button
                type="button"
                onClick={listen}
                disabled={busy}
                aria-pressed={listening}
                aria-label={listening ? "Stop listening" : "Ask by voice"}
                className={cx(
                  "grid h-10 w-10 shrink-0 place-items-center rounded-full border transition-colors disabled:opacity-60",
                  listening ? "animate-pulse border-critical bg-critical text-white" : "border-control text-muted hover:text-foreground",
                )}
              >
                <Mic size={16} />
              </button>
            )}
            <button
              type="submit"
              disabled={busy || !question.trim()}
              aria-label="Ask"
              className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-accent text-white transition-colors disabled:opacity-50"
            >
              {busy ? <Spinner /> : <Send size={15} />}
            </button>
          </form>
        </section>
      )}
    </>
  );
}
