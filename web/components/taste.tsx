"use client";

import { Check, Heart, Plus, Search, Sparkles, X } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import { tool } from "@/lib/client";
import {
  addLove,
  DIETARY,
  groupPicks,
  kindLabel,
  KINDS,
  match,
  MAX_LOVES,
  toggleLove,
  type Found,
  type Love,
  type Taste,
  type TasteOptions,
} from "@/lib/groundtime";

import { Button, cx, Notice, Panel, Spinner } from "./ui";

export type TasteValue = { loves: Love[]; dietary: string[]; windDown: string };

export const NO_TASTE: TasteValue = { loves: [], dietary: [], windDown: "" };

/** The short list and dietary options. The short list is looked up in Qloo, so it can take a
 * moment; if it fails, search still works on its own. */
export function useTasteOptions(): TasteOptions | null {
  const [options, setOptions] = useState<TasteOptions | null>(null);
  useEffect(() => {
    tool<TasteOptions>("taste_options").then(setOptions, () =>
      setOptions({ picks: [], dietary: DIETARY, kinds: KINDS }),
    );
  }, []);
  return options;
}

function Chip({
  on,
  disabled,
  onClick,
  children,
}: {
  on: boolean;
  disabled?: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={on}
      disabled={disabled}
      onClick={onClick}
      className={cx(
        "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        on ? "border-accent bg-accent-soft font-medium text-[#173f63]" : "border-line hover:bg-sunken",
      )}
    >
      {on ? <Check size={13} /> : <Plus size={13} className="text-muted" />}
      {children}
    </button>
  );
}

/** What you love and what you eat, as fields: the short list to tap, a search of Qloo's
 * catalogue for anything else, and dietary needs. Only crew get the wind-down choice, for the
 * evening on a night stop. Saving is up to the caller. */
export function TasteFields({
  value,
  onChange,
  options,
  crew = false,
}: {
  value: TasteValue;
  onChange: (value: TasteValue) => void;
  options: TasteOptions | null;
  crew?: boolean;
}) {
  const kinds = options?.kinds ?? KINDS;
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState("urn:entity:artist");
  const [found, setFound] = useState<Found[]>([]);
  // the query a search is out for; a newer one hides its spinner
  const [searching, setSearching] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Search Qloo's catalogue once typing pauses; a newer query drops an older answer.
  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) return;
    let live = true;
    const t = setTimeout(() => {
      setSearching(q);
      setError(null);
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

  const { loves, dietary } = value;
  const full = loves.length >= MAX_LOVES;
  const has = (id: string) => loves.some((l) => l.id === id);
  const set = (change: Partial<TasteValue>) => onChange({ ...value, ...change });
  const groups = groupPicks(options?.picks ?? [], kinds);
  const shortList = new Set((options?.picks ?? []).map((p) => p.id));
  // picks made by search, which the short list doesn't show
  const extra = loves.filter((l) => !shortList.has(l.id));

  return (
    <div className="flex flex-col gap-5">
      <div>
        <p className="text-sm font-medium">
          Pick up to five things you love{" "}
          <span className="font-normal text-muted">
            ({loves.length} of {MAX_LOVES})
          </span>
        </p>
        <p className="mt-0.5 text-xs text-muted">
          Qloo uses them to find places and films for you. They go to Qloo only as ids, never with your name.
        </p>
      </div>

      {!options ? (
        <p className="flex items-center gap-2 text-sm text-muted">
          <Spinner /> Getting a few ideas from Qloo…
        </p>
      ) : (
        groups.map(([k, label, picks]) => (
          <div key={k}>
            <p className="mb-1.5 text-xs font-medium text-muted">{kindLabel(k, { [k]: `${label}s` })}</p>
            <div className="flex flex-wrap gap-1.5">
              {picks.map((p) => (
                <Chip
                  key={p.id}
                  on={has(p.id)}
                  disabled={full && !has(p.id)}
                  onClick={() => set({ loves: toggleLove(loves, { id: p.id, name: p.name, type: p.type }) })}
                >
                  {p.name}
                </Chip>
              ))}
            </div>
          </div>
        ))
      )}

      {extra.length > 0 && (
        <ul className="flex flex-wrap gap-1.5">
          {extra.map((l) => (
            <li
              key={l.id}
              className="inline-flex items-center gap-1 rounded-full bg-accent-soft py-1 pl-3 pr-1 text-sm text-[#173f63]"
            >
              {l.name}
              <span className="text-xs text-[#173f63]/60">· {kinds[l.type] ?? kindLabel(l.type)}</span>
              <button
                type="button"
                aria-label={`Remove ${l.name}`}
                className="rounded-full p-0.5 hover:bg-white/70"
                onClick={() => set({ loves: loves.filter((x) => x.id !== l.id) })}
              >
                <X size={13} />
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="flex flex-col gap-2">
        <p className="text-xs font-medium text-muted">Something else?</p>
        <div className="flex gap-2">
          <select
            aria-label="What kind"
            value={kind}
            onChange={(e) => setKind(e.target.value)}
            className="h-10 rounded-md border border-control bg-surface px-2 text-sm outline-none focus:border-accent"
          >
            {Object.keys(kinds).map((k) => (
              <option key={k} value={k}>
                {kindLabel(k, kinds)}
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
        {error && <Notice tone="error">{error}</Notice>}
        {found.length > 0 && !full && query.trim().length >= 2 && (
          <ul className="flex flex-col divide-y divide-rule rounded-md border border-line">
            {found.map((f) => (
              <li key={f.id}>
                <button
                  type="button"
                  disabled={has(f.id)}
                  onClick={() => {
                    set({ loves: addLove(loves, { id: f.id, name: f.name, type: f.type || kind }) });
                    setQuery("");
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
                  {has(f.id) && <Check size={14} className="text-ok" />}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <p className="mb-1.5 text-sm font-medium">Dietary needs</p>
        <div className="flex flex-wrap gap-1.5">
          {(options?.dietary ?? DIETARY).map((d) => {
            const on = dietary.includes(d.id);
            return (
              <Chip
                key={d.id}
                on={on}
                onClick={() => set({ dietary: on ? dietary.filter((x) => x !== d.id) : [...dietary, d.id] })}
              >
                {d.name}
              </Chip>
            );
          })}
        </div>
      </div>

      {crew && (
        <div>
          <p className="mb-1.5 text-sm font-medium">After a duty I like it</p>
          <div className="flex flex-wrap gap-1.5">
            {[
              ["quiet", "Quiet"],
              ["lively", "Lively"],
            ].map(([v, label]) => (
              <Chip key={v} on={value.windDown === v} onClick={() => set({ windDown: value.windDown === v ? "" : v })}>
                {label}
              </Chip>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/** The saved taste, to change: loads it, and saves only when asked. */
export function TastePicker({ crew = false, onSaved }: { crew?: boolean; onSaved?: () => void }) {
  const options = useTasteOptions();
  const [value, setValue] = useState<TasteValue | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    tool<Taste>("my_taste").then(
      (t) => setValue({ loves: t.loves ?? [], dietary: t.dietary ?? [], windDown: t.wind_down ?? "" }),
      (err: Error) => {
        setError(err.message);
        setValue(NO_TASTE);
      },
    );
  }, []);

  async function save() {
    if (!value) return;
    setBusy(true);
    setSaved(false);
    setError(null);
    try {
      const out = await tool<Taste>("save_my_taste", {
        loves: value.loves,
        dietary: value.dietary,
        ...(crew && value.windDown ? { wind_down: value.windDown } : {}),
      });
      setValue({ loves: out.loves ?? [], dietary: out.dietary ?? [], windDown: out.wind_down ?? "" });
      setSaved(true);
      onSaved?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title="What you love" icon={<Heart size={14} className="text-accent" />}>
      {!value ? (
        <Spinner className="text-muted" />
      ) : (
        <div className="flex flex-col gap-4">
          <TasteFields
            value={value}
            onChange={(v) => {
              setValue(v);
              setSaved(false);
            }}
            options={options}
            crew={crew}
          />
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
