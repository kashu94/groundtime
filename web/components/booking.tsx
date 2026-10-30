"use client";

import { ArrowRight, CalendarDays, Check, Heart, MapPin, Plane, Search } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import { AirlineBadge, airlineOf } from "@/components/airline";
import { NO_TASTE, TasteFields, useTasteOptions, type TasteValue } from "@/components/taste";
import { Button, cx, Empty, Mono, Notice, Panel, Spinner } from "@/components/ui";
import { tool } from "@/lib/client";
import {
  hhmm,
  LAST_BOOKABLE,
  route,
  todayInIndia,
  type Position,
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

const WHERE: [Position, string][] = [
  ["away", "Not at the airport yet"],
  ["airport", "At the airport"],
];

const select =
  "h-10 w-full rounded-md border border-control bg-surface px-2 text-sm outline-none focus:border-accent focus:ring-2 focus:ring-accent/20";

/** Booking in three steps: the flight, what you love, and where you'll be. Nothing is saved
 * until the last step's Confirm, and then the trip and the taste are saved together. */
export function Booking({ onBooked, onCancel }: { onBooked: () => void; onCancel?: () => void }) {
  const [stations, setStations] = useState<Station[] | null>(null);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [date, setDate] = useState(todayInIndia);
  const [options, setOptions] = useState<TripOption[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [chosen, setChosen] = useState<TripOption | null>(null);
  const tasteOptions = useTasteOptions();
  const [taste, setTaste] = useState<TasteValue>(NO_TASTE);
  const [position, setPosition] = useState<Position>("away");
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
        position,
      });
      onBooked();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not book.");
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
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

      {chosen && (
        <>
          <Step n={2} title="What you love" icon={<Heart size={14} />}>
            <TasteFields value={taste} onChange={setTaste} options={tasteOptions} />
            <p className="mt-4 text-xs text-muted">Nothing is saved until you confirm the booking.</p>
          </Step>

          <Step n={3} title="Where you'll be" icon={<MapPin size={14} />}>
            <div className="grid gap-2 sm:grid-cols-2">
              {WHERE.map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  aria-pressed={position === value}
                  onClick={() => setPosition(value)}
                  className={cx(
                    "rounded-lg border px-3 py-2 text-sm transition-colors",
                    position === value
                      ? "border-accent bg-accent-soft font-semibold text-[#173f63]"
                      : "border-line hover:bg-sunken",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
            <p className="mt-2 text-xs text-muted">You can change this later from your trip.</p>
          </Step>

          {error && <Notice tone="error">{error}</Notice>}
          <div className="flex flex-wrap items-center gap-3">
            <Button tone="accent" className="h-10 px-4" disabled={busy} onClick={confirm}>
              {busy ? <Spinner /> : <Check size={15} />} Confirm booking
            </Button>
            <span className="text-sm text-muted">
              {chosen.legs.map((l) => l.flight_no).join(" + ")} · {city(chosen.from)} to {city(chosen.to)} ·{" "}
              {hhmm(chosen.departs_local)}
            </span>
          </div>
        </>
      )}

      {!chosen && error && <Notice tone="error">{error}</Notice>}
    </div>
  );
}
