"use client";

import { ArrowRight, CalendarDays, Check, Heart, Plane, Search } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import { AirlineBadge, airlineOf } from "@/components/airline";
import { CareDesk } from "@/components/care-desk";
import { NO_TASTE, TasteFields, useTasteOptions, type TasteValue } from "@/components/taste";
import { Button, cx, day, Empty, Mono, Notice, Panel, Spinner } from "@/components/ui";
import { tool } from "@/lib/client";
import {
  hhmm,
  LAST_BOOKABLE,
  route,
  todayInIndia,
  type CareDesk as Desk,
  type Station,
  type TripOption,
} from "@/lib/groundtime";

function Step({ n, title, icon, children }: { n: number; title: string; icon: ReactNode; children: ReactNode }) {
  return (
    <Panel
      title={
        <span className="flex items-center gap-2">
          <span className="grid h-5 w-5 place-items-center rounded-full bg-accent text-[11px] font-semibold text-white">
            {n}
          </span>
          {title}
        </span>
      }
      icon={icon}
    >
      {children}
    </Panel>
  );
}

function OptionCard({ option, chosen, onChoose }: { option: TripOption; chosen: boolean; onChoose: () => void }) {
  return (
    <button
      type="button"
      aria-pressed={chosen}
      onClick={onChoose}
      className={cx(
        "lift w-full rounded-lg border p-3 text-left transition-colors",
        chosen ? "border-accent bg-accent-soft/60" : "border-line hover:bg-sunken",
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="flex items-center gap-2 text-sm font-semibold">
          <Mono>{hhmm(option.departs_local)}</Mono>
          <ArrowRight size={13} className="text-muted" />
          <Mono>{hhmm(option.arrives_local)}</Mono>
        </span>
        <span className="flex items-center gap-2 text-xs text-muted">
          {route(option)}
          {chosen && <Check size={14} className="text-accent" />}
        </span>
      </div>
      <ul className="mt-2 flex flex-col gap-1 text-xs text-muted">
        {option.legs.map((leg) => (
          <li key={leg.flight_id} className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <AirlineBadge code={airlineOf(leg.flight_no)} compact />
            <Mono className="text-foreground">{leg.flight_no}</Mono>
            {leg.airline && <span>{leg.airline}</span>}
            <span>
              {leg.from} <Mono>{hhmm(leg.departs_local)}</Mono> → {leg.to} <Mono>{hhmm(leg.arrives_local)}</Mono>
            </span>
          </li>
        ))}
      </ul>
    </button>
  );
}

const select =
  "h-10 w-full rounded-md border border-control bg-surface px-2 text-sm outline-none focus:border-accent focus:ring-2 focus:ring-accent/20";

/** Booking in two steps: the flight, then what you love. Nothing is saved until Confirm, and
 * then the trip and the taste are saved together. Where the traveller is isn't asked here: a
 * trip starts as "not at the airport yet", and My trip finds out on the day. */
export function Booking({
  onBooked,
  onCancel,
  care,
}: {
  onBooked: () => void;
  onCancel?: () => void;
  care?: Desk;
}) {
  const [stations, setStations] = useState<Station[] | null>(null);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [date, setDate] = useState(todayInIndia);
  const [options, setOptions] = useState<TripOption[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [chosen, setChosen] = useState<TripOption | null>(null);
  const tasteOptions = useTasteOptions();
  const [taste, setTaste] = useState<TasteValue>(NO_TASTE);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    tool<Station[]>("stations").then(setStations, (err: Error) => setError(err.message));
  }, []);

  const today = todayInIndia();

  // A new search question: the old answers and choice no longer apply.
  function ask(change: () => void) {
    change();
    setOptions(null);
    setChosen(null);
  }
  const city = (code: string) => stations?.find((s) => s.code === code)?.city ?? code;

  async function search() {
    setSearching(true);
    setError(null);
    setChosen(null);
    try {
      setOptions(await tool<TripOption[]>("find_flights", { origin: from, destination: to, date }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not search flights.");
    } finally {
      setSearching(false);
    }
  }

  async function confirm() {
    if (!chosen) return;
    setBusy(true);
    setError(null);
    try {
      await tool("book_trip", {
        flight_ids: chosen.flight_ids,
        loves: taste.loves,
        dietary: taste.dietary,
      });
      onBooked();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not book.");
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[22px] font-semibold tracking-tight">Book a trip</h1>
          <p className="mt-1 text-sm text-muted">
            If your flight is delayed, Groundtime plans the wait around what you love.
          </p>
        </div>
        {onCancel && (
          <Button tone="ghost" onClick={onCancel}>
            Back to my trip
          </Button>
        )}
      </header>

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,26rem)]">
        <div className="flex min-w-0 flex-col gap-6">
        <Step n={1} title="Where and when" icon={<Plane size={14} />}>
          <form
            className="grid gap-3 sm:grid-cols-[1fr_1fr_1fr_auto] sm:items-end"
            onSubmit={(e) => {
              e.preventDefault();
              search();
            }}
          >
            <label className="flex flex-col gap-1 text-sm">
              <span className="font-medium">From</span>
              <select
                required
                value={from}
                onChange={(e) => {
                  const code = e.target.value;
                  ask(() => {
                    setFrom(code);
                    if (code === to) setTo("");
                  });
                }}
                className={select}
              >
                <option value="">Choose</option>
                {stations?.map((s) => (
                  <option key={s.code} value={s.code}>
                    {s.city} ({s.code})
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="font-medium">To</span>
              <select
                required
                value={to}
                onChange={(e) => {
                  const code = e.target.value;
                  ask(() => setTo(code));
                }}
                className={select}
              >
                <option value="">Choose</option>
                {stations
                  ?.filter((s) => s.code !== from)
                  .map((s) => (
                    <option key={s.code} value={s.code}>
                      {s.city} ({s.code})
                    </option>
                  ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="font-medium">Date</span>
              <input
                type="date"
                required
                min={today}
                max={LAST_BOOKABLE}
                value={date}
                onChange={(e) => {
                  const day = e.target.value;
                  ask(() => setDate(day));
                }}
                className={select}
              />
            </label>
            <Button type="submit" tone="accent" className="h-10" disabled={searching || !from || !to || from === to}>
              {searching ? <Spinner /> : <Search size={14} />} Search
            </Button>
          </form>

          {options && (
            <div className="mt-5">
              {options.length === 0 ? (
                <Empty icon={<CalendarDays size={22} />}>
                  No flights left to book from {city(from)} to {city(to)} that day. Try another date.
                </Empty>
              ) : (
                <ul className="flex flex-col gap-2">
                  {options.map((o) => (
                    <li key={o.flight_ids.join("+")}>
                      <OptionCard option={o} chosen={chosen === o} onChoose={() => setChosen(o)} />
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </Step>
          {!chosen && error && <Notice tone="error">{error}</Notice>}
        </div>

        <aside className="flex min-w-0 flex-col gap-6 lg:sticky lg:top-4">
          {chosen ? (
            <>
              <Step n={2} title="What you love" icon={<Heart size={14} />}>
                <TasteFields value={taste} onChange={setTaste} options={tasteOptions} />
                <p className="mt-4 text-xs text-muted">
                  If your flight is delayed, your plan is built around these. Nothing is saved until you confirm.
                </p>
              </Step>

              <section className="rounded-lg border border-line bg-surface p-4">
                <p className="text-sm font-semibold">
                  {chosen.legs.map((l) => l.flight_no).join(" + ")} · {city(chosen.from)} to {city(chosen.to)}
                </p>
                <p className="mt-1 text-sm text-muted">
                  {day(chosen.departs_local.slice(0, 10))}, leaves <Mono>{hhmm(chosen.departs_local)}</Mono>, arrives{" "}
                  <Mono>{hhmm(chosen.arrives_local)}</Mono> · {route(chosen)}
                </p>
                {error && (
                  <div className="mt-3">
                    <Notice tone="error">{error}</Notice>
                  </div>
                )}
                <Button tone="accent" className="mt-4 h-10 w-full justify-center" disabled={busy} onClick={confirm}>
                  {busy ? <Spinner /> : <Check size={15} />} Confirm booking
                </Button>
              </section>
            </>
          ) : (
            <section className="rounded-lg border border-dashed border-line p-5 text-sm text-muted">
              <p className="flex items-center gap-2 font-medium text-foreground">
                <span className="grid h-5 w-5 place-items-center rounded-full bg-sunken text-[11px] font-semibold">
                  2
                </span>
                What you love
              </p>
              <p className="mt-2">
                Choose a flight first. Then tap a few things you love, so a delay becomes time for something you enjoy.
              </p>
            </section>
          )}
          {care && <CareDesk desk={care} />}
        </aside>
      </div>
    </div>
  );
}
