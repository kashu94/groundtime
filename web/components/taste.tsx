"use client";

import { Check, Heart, Search, Sparkles, X } from "lucide-react";
import { useEffect, useState } from "react";

import { tool } from "@/lib/client";
import { addLove, DIETARY, match, MAX_LOVES, SEARCH_KINDS, type Found, type Love, type Taste } from "@/lib/groundtime";

import { Button, cx, Notice, Panel, Spinner } from "./ui";

const KIND_LABEL = Object.fromEntries(SEARCH_KINDS.map(([k, label]) => [k, label]));

/** What you love and what you eat, for Qloo to plan around. Travellers and crew alike; only
 * crew get the wind-down choice, for the evening on a night stop. */
export function TastePicker({ crew = false, onSaved }: { crew?: boolean; onSaved?: () => void }) {
  const [loves, setLoves] = useState<Love[]>([]);
  const [dietary, setDietary] = useState<string[]>([]);
  const [windDown, setWindDown] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState(SEARCH_KINDS[0][0]);
  const [found, setFound] = useState<Found[]>([]);
  // the query a search is out for; a newer one hides its spinner
  const [searching, setSearching] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    tool<Taste>("my_taste").then(
      (t) => {
        setLoves(t.loves ?? []);
        setDietary(t.dietary ?? []);
        setWindDown(t.wind_down ?? "");
        setLoaded(true);
      },
      (err: Error) => {
        setError(err.message);
        setLoaded(true);
      },
    );
  }, []);

  // Search Qloo's catalogue once typing pauses; a newer query drops an older answer.
  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) return;
    let live = true;
    const t = setTimeout(() => {
      setSearching(q);
      tool<Found[]>("taste_search", { query: q, kind })
        .then(
          (rows) => live && setFound(rows ?? []),
          (err: Error) => live && setError(err.message),
        )
        .finally(() => setSearching((s) => (s === q ? null : s)));
    }, 400);
    return () => {
      live = false;
      clearTimeout(t);
    };
  }, [query, kind]);

  function change() {
    setSaved(false);
    setError(null);
  }

  async function save() {
    setBusy(true);
    change();
    try {
      const out = await tool<Taste>("save_my_taste", {
        loves,
        dietary,
        ...(crew && windDown ? { wind_down: windDown } : {}),
      });
      setLoves(out.loves ?? []);
      setDietary(out.dietary ?? []);
      setWindDown(out.wind_down ?? "");
      setSaved(true);
      onSaved?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  const full = loves.length >= MAX_LOVES;

  return (
    <Panel title="What you love" icon={<Heart size={14} className="text-accent" />}>
      {!loaded ? (
        <Spinner className="text-muted" />
      ) : (
        <div className="flex flex-col gap-4">
          <p className="text-xs text-muted">
            Only Qloo ids are saved, never free text; your picks are sent to Qloo as ids, never with your name.
          </p>

          <div>
            <p className="mb-1.5 text-sm font-medium">
              Your picks{" "}
              <span className="font-normal text-muted">
                ({loves.length} of {MAX_LOVES})
              </span>
            </p>
            {loves.length === 0 ? (
              <p className="text-sm text-muted">Nothing yet. Search below and add up to five.</p>
            ) : (
              <ul className="flex flex-wrap gap-1.5">
                {loves.map((l) => (
                  <li
                    key={l.id}
                    className="inline-flex items-center gap-1 rounded-full bg-accent-soft py-0.5 pl-2.5 pr-1 text-xs text-[#173f63]"
                  >
                    {l.name}
                    <span className="text-[#173f63]/60">
                      · {KIND_LABEL[l.type] ?? l.type.replace("urn:entity:", "")}
                    </span>
                    <button
                      type="button"
                      aria-label={`Remove ${l.name}`}
                      className="rounded-full p-0.5 hover:bg-white/70"
                      onClick={() => {
                        setLoves(loves.filter((x) => x.id !== l.id));
                        change();
                      }}
                    >
                      <X size={12} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="flex flex-col gap-2">
            <div className="flex gap-2">
              <select
                aria-label="What kind"
                value={kind}
                onChange={(e) => setKind(e.target.value)}
                className="h-10 rounded-md border border-control bg-surface px-2 text-sm outline-none focus:border-accent"
              >
                {SEARCH_KINDS.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
              <label className="relative flex-1">
                <span className="sr-only">Search Qloo</span>
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  maxLength={80}
                  disabled={full}
                  placeholder={full ? "Five picks: remove one to add another" : "Search, e.g. A. R. Rahman"}
                  className="h-10 w-full rounded-md border border-control bg-surface pl-8 pr-8 text-sm outline-none transition-colors focus:border-accent focus:ring-2 focus:ring-accent/20 disabled:opacity-60"
                />
                {searching === query.trim() && <Spinner className="absolute right-3 top-3 text-muted" />}
              </label>
            </div>
            {found.length > 0 && !full && query.trim().length >= 2 && (
              <ul className="flex flex-col divide-y divide-rule rounded-md border border-line">
                {found.map((f) => {
                  const taken = loves.some((l) => l.id === f.id);
                  return (
                    <li key={f.id}>
                      <button
                        type="button"
                        disabled={taken}
                        onClick={() => {
                          setLoves(addLove(loves, { id: f.id, name: f.name, type: f.type || kind }));
                          setQuery("");
                          change();
                        }}
                        className="flex w-full items-center gap-3 px-3 py-2 text-left text-sm hover:bg-sunken disabled:opacity-60"
                      >
                        {f.image ? (
                          // Qloo's own image hosts vary; a plain img keeps them out of the build config.
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={f.image} alt="" className="h-8 w-8 shrink-0 rounded object-cover" />
                        ) : (
                          <span className="h-8 w-8 shrink-0 rounded bg-sunken" />
                        )}
                        <span className="min-w-0 flex-1 truncate">
                          {f.name}
                          {f.year && <span className="text-muted"> ({f.year})</span>}
                        </span>
                        {taken && <Check size={14} className="text-ok" />}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          <fieldset className="text-sm">
            <legend className="mb-1.5 font-medium">Dietary needs</legend>
            <div className="flex flex-wrap gap-x-4 gap-y-2">
              {DIETARY.map(([value, label]) => (
                <label key={value} className="flex items-center gap-1.5">
                  <input
                    type="checkbox"
                    checked={dietary.includes(value)}
                    onChange={(e) => {
                      setDietary(e.target.checked ? [...dietary, value] : dietary.filter((d) => d !== value));
                      change();
                    }}
                    className="accent-accent"
                  />
                  {label}
                </label>
              ))}
            </div>
          </fieldset>

          {crew && (
            <label className="flex flex-col gap-1 text-sm">
              <span className="font-medium">After a duty I like it</span>
              <select
                value={windDown}
                onChange={(e) => {
                  setWindDown(e.target.value);
                  change();
                }}
                className="h-10 rounded-md border border-control bg-surface px-2 outline-none focus:border-accent"
              >
                <option value="">No preference</option>
                <option value="quiet">Quiet</option>
                <option value="lively">Lively</option>
              </select>
            </label>
          )}

          {error && <Notice tone="error">{error}</Notice>}
          {saved && <Notice tone="ok">Saved. Your next plan uses it.</Notice>}
          <div>
            <Button type="button" tone="accent" disabled={busy} onClick={save} className={cx(busy && "cursor-wait")}>
              {busy && <Spinner />} Save
            </Button>
          </div>
        </div>
      )}
    </Panel>
  );
}

/** Qloo's affinity for this person's taste, as a small chip. */
export function TasteMatch({ affinity }: { affinity: number | null | undefined }) {
  const pct = match(affinity);
  if (pct === null) return null;
  return (
    <span
      title={`Qloo taste match: ${pct}%`}
      className="inline-flex shrink-0 items-center gap-1 rounded-full bg-accent-soft px-2 py-0.5 text-[11px] font-medium text-[#173f63]"
    >
      <Sparkles size={10} /> Qloo taste match
    </span>
  );
}
