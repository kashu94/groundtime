"use client";

import { CheckCircle2, Clock3, HeartHandshake, History, Pencil, Plane, Search, Users, X, XCircle } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { useMe } from "@/components/me";
import { Late } from "@/components/plan";
import { Button, cx, Empty, Mono, Notice, Panel, Spinner } from "@/components/ui";
import { tool } from "@/lib/client";
import {
  delayMinutes,
  duration,
  hhmm,
  LAST_BOOKABLE,
  matchesFlight,
  MAX_DELAY_TIMES,
  planSummary,
  QUICK_DELAYS,
  todayInIndia,
  type BoardRow,
  type DelayedFlight,
  type DelayRecord,
  type FlightCare,
  type Station,
} from "@/lib/groundtime";

/** "Marked late 2 of 3 times · first 12:10 · latest 13:00 by neha.joshi", or null if never. */
function DelayCount({ record }: { record: DelayRecord }) {
  if (!record.times_delayed) return null;
  const full = record.delays_left <= 0;
  return (
    <span className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-xs text-muted">
      <span className={cx("font-medium", full ? "text-critical" : "text-foreground")}>
        Marked late {record.times_delayed} of {MAX_DELAY_TIMES} times
      </span>
      {record.first_delayed_local && (
        <span>
          · first at <Mono>{hhmm(record.first_delayed_local)}</Mono>
        </span>
      )}
      {record.recorded_local && (
        <span>
          · last change <Mono>{hhmm(record.recorded_local)}</Mono>
          {record.recorded_by && <> by {record.recorded_by}</>}
        </span>
      )}
    </span>
  );
}

function DelayHistory({ record }: { record: DelayRecord }) {
  if (!record.history.length) return null;
  return (
    <div>
      <p className="flex items-center gap-1.5 text-xs font-medium">
        <History size={12} /> Changes so far
      </p>
      <ol className="mt-1 flex flex-col gap-0.5 text-xs text-muted">
        {record.history.map((h, i) => (
          <li key={i}>
            <Mono>{hhmm(h.at_local)}</Mono> · {h.delay_minutes ? `${duration(h.delay_minutes)} late` : "cleared"}
            {h.reason && h.reason !== "Not given" && h.reason !== "Back on time" && <> · {h.reason}</>}
            {h.by && <> · {h.by}</>}
          </li>
        ))}
      </ol>
    </div>
  );
}

/** Record a delay on one flight as operations confirm it; 0 clears it. */
function DelayEditor({
  row,
  onSaved,
  onClose,
}: {
  row: BoardRow;
  onSaved: (message: string) => void;
  onClose: () => void;
}) {
  const [minutes, setMinutes] = useState(row.delay_minutes ? String(row.delay_minutes) : "");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const value = delayMinutes(minutes);
  const full = row.delays_left <= 0;

  async function save(delay: number) {
    setBusy(true);
    setError(null);
    try {
      const out = await tool<{ waiting: number }>("record_delay", {
        flight_id: row.flight_id,
        delay_minutes: delay,
        reason: reason.trim(),
      });
      const who = `${out.waiting} Groundtime traveller${out.waiting === 1 ? "" : "s"}`;
      onSaved(
        delay
          ? `${row.flight_no} is now ${duration(delay)} late. Plans for ${who} move with it.`
          : `${row.flight_no} is back on time. Plans for ${who} move with it.`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not record that.");
      setBusy(false);
    }
  }

  return (
    <form
      className="flex flex-col gap-3 rounded-md bg-sunken p-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (value !== null && !full) save(value);
      }}
    >
      <DelayHistory record={row} />
      {full ? (
        <p className="text-xs text-critical">
          {row.flight_no} has been marked late {MAX_DELAY_TIMES} times, the most allowed. You can still clear the delay
          if it leaves on time.
        </p>
      ) : (
        <p className="text-xs text-muted">
          {row.delays_left === MAX_DELAY_TIMES
            ? `A flight can be marked late up to ${MAX_DELAY_TIMES} times, so give the best estimate operations have.`
            : `${row.delays_left} more change${row.delays_left === 1 ? "" : "s"} allowed on this flight.`}
        </p>
      )}
      {!full && (
        <>
          <div className="flex flex-wrap items-center gap-2">
            {QUICK_DELAYS.map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setMinutes(String(m))}
                className={cx(
                  "rounded-full border px-3 py-1 text-xs transition-colors",
                  value === m ? "border-accent bg-accent-soft font-medium text-[#173f63]" : "border-line bg-surface",
                )}
              >
                {duration(m)}
              </button>
            ))}
            <label className="flex items-center gap-1.5 text-xs">
              <input
                value={minutes}
                onChange={(e) => setMinutes(e.target.value)}
                inputMode="numeric"
                aria-label="Delay in minutes"
                placeholder="Minutes"
                className="h-8 w-20 rounded-md border border-control bg-surface px-2 text-sm outline-none focus:border-accent"
              />
              min
            </label>
          </div>
          <input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            maxLength={200}
            placeholder="Reason, e.g. late inbound aircraft (optional)"
            className="h-9 rounded-md border border-control bg-surface px-3 text-sm outline-none focus:border-accent"
          />
        </>
      )}
      {minutes.trim() && value === null && (
        <p className="text-xs text-critical">A delay is whole minutes, up to 12 hours.</p>
      )}
      {error && <Notice tone="error">{error}</Notice>}
      <div className="flex flex-wrap gap-2">
        {!full && (
          <Button type="submit" tone="accent" disabled={busy || value === null || value === 0 || value === row.delay_minutes}>
            {busy && <Spinner />} Save
          </Button>
        )}
        {row.delay_minutes > 0 && (
          <Button type="button" tone="secondary" disabled={busy} onClick={() => save(0)}>
            Clear: back on time
          </Button>
        )}
        <Button type="button" tone="ghost" disabled={busy} onClick={onClose}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

const FILTERS = [
  ["all", "All"],
  ["to_leave", "Still to leave"],
  ["delayed", "Delayed"],
  ["groundtime", "With Groundtime travellers"],
] as const;
type Filter = (typeof FILTERS)[number][0];

function Board({ onChanged, version }: { onChanged: (message: string, flightId: string) => void; version: number }) {
  const [date, setDate] = useState(todayInIndia);
  const [rows, setRows] = useState<BoardRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("to_leave");
  const [cities, setCities] = useState<Record<string, string>>({});

  useEffect(() => {
    tool<Station[]>("stations").then(
      (s) => setCities(Object.fromEntries(s.map((x) => [x.code, x.city]))),
      () => undefined,
    );
  }, []);

  const shown = useMemo(
    () =>
      (rows ?? []).filter(
        (r) =>
          matchesFlight(r, query, (c) => cities[c] ?? c) &&
          (filter === "all" ||
            (filter === "to_leave" && !r.left) ||
            (filter === "delayed" && r.delay_minutes > 0) ||
            (filter === "groundtime" && r.with_app > 0)),
      ),
    [rows, query, filter, cities],
  );

  useEffect(() => {
    let live = true;
    tool<BoardRow[]>("flight_board", { date }).then(
      (r) => {
        if (!live) return;
        setRows(r);
        setError(null);
      },
      (err: Error) => live && setError(err.message),
    );
    return () => {
      live = false;
    };
  }, [date, version]);

  return (
    <Panel
      title="Flight board"
      icon={<Plane size={14} className="text-accent" />}
      action={
        <input
          type="date"
          aria-label="Date"
          value={date}
          max={LAST_BOOKABLE}
          onChange={(e) => {
            setRows(null);
            setEditing(null);
            setDate(e.target.value || todayInIndia());
          }}
          className="h-8 rounded-md border border-control bg-surface px-2 text-sm outline-none focus:border-accent"
        />
      }
    >
      <div className="mb-4 flex flex-col gap-2">
        <label className="relative block">
          <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
          <input
            type="text"
            inputMode="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Search flights"
            placeholder="Search a flight number, airport or city: KS434, GOI, Goa Bengaluru"
            className="h-10 w-full rounded-md border border-control bg-surface pl-9 pr-9 text-sm outline-none focus:border-accent focus:ring-2 focus:ring-accent/20"
          />
          {query && (
            <button
              type="button"
              aria-label="Clear search"
              onClick={() => setQuery("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-muted hover:bg-sunken hover:text-foreground"
            >
              <X size={14} />
            </button>
          )}
        </label>
        <div className="flex flex-wrap items-center gap-1.5">
          {FILTERS.map(([value, label]) => (
            <button
              key={value}
              type="button"
              aria-pressed={filter === value}
              onClick={() => setFilter(value)}
              className={cx(
                "rounded-full border px-3 py-1 text-xs transition-colors",
                filter === value ? "border-accent bg-accent-soft font-medium text-[#173f63]" : "border-line hover:bg-sunken",
              )}
            >
              {label}
            </button>
          ))}
          {rows && (
            <span className="ml-auto text-xs text-muted">
              {shown.length} of {rows.length} flights
            </span>
          )}
        </div>
      </div>
      {error ? (
        <Notice tone="error">{error}</Notice>
      ) : !rows ? (
        <Spinner className="text-muted" />
      ) : rows.length === 0 ? (
        <Empty icon={<Plane size={22} />}>No departures that day.</Empty>
      ) : shown.length === 0 ? (
        <Empty icon={<Search size={22} />}>No flight matches that. Try a flight number like KS434, or an airport.</Empty>
      ) : (
        <ul className="flex max-h-[34rem] flex-col divide-y divide-rule overflow-y-auto pr-1">
          {shown.map((r) => (
            <li key={r.flight_id} className={cx("py-2.5 first:pt-0 last:pb-0", r.left && "opacity-55")}>
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-sm">
                <Mono className="w-14 font-semibold">{r.flight_no}</Mono>
                <span className="w-24">
                  {r.from} <span className="text-muted">→</span> {r.to}
                </span>
                <Mono className={cx(r.delay_minutes > 0 && "text-muted line-through")}>{hhmm(r.departs_local)}</Mono>
                <Late minutes={r.delay_minutes} expected={r.expected_departure_local} />
                <span className="text-xs text-muted">
                  {r.with_app} with Groundtime · {r.booked} booked
                </span>
                <span className="ml-auto">
                  {r.left ? (
                    <span className="text-xs text-muted">Departed</span>
                  ) : (
                    editing !== r.flight_id && (
                      <Button tone="ghost" onClick={() => setEditing(r.flight_id)}>
                        <Pencil size={13} />{" "}
                        {r.delays_left <= 0 ? "View delay" : r.delay_minutes > 0 ? "Change delay" : "Record delay"}
                      </Button>
                    )
                  )}
                </span>
              </div>
              {r.times_delayed > 0 && (
                <div className="mt-1">
                  <DelayCount record={r} />
                </div>
              )}
              {editing === r.flight_id && !r.left && (
                <div className="mt-2">
                  <DelayEditor
                    row={r}
                    onClose={() => setEditing(null)}
                    onSaved={(message) => {
                      setEditing(null);
                      onChanged(message, r.flight_id);
                    }}
                  />
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      <p className="mt-3 text-[11px] text-muted">Times are local, in India.</p>
    </Panel>
  );
}

export default function Care() {
  const me = useMe();
  const allowed = me.roles.includes("customer_care");
  const [flights, setFlights] = useState<DelayedFlight[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [chosen, setChosen] = useState<string | null>(null);
  const [care, setCare] = useState<FlightCare | null>(null);
  const [careError, setCareError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  // bumped after each recorded delay, so every view reloads with it
  const [version, setVersion] = useState(0);

  const loadDelayed = useCallback(() => {
    tool<DelayedFlight[]>("delayed_flights").then(setFlights, (err: Error) => setError(err.message));
  }, []);
  useEffect(() => {
    if (allowed) loadDelayed();
  }, [allowed, loadDelayed, version]);

  useEffect(() => {
    if (!chosen) return;
    let live = true;
    tool<FlightCare>("flight_care", { flight_id: chosen }).then(
      (c) => live && setCare(c),
      (err: Error) => live && setCareError(err.message),
    );
    return () => {
      live = false;
    };
  }, [chosen, version]);

  if (!allowed) return <Notice>This view is for customer care.</Notice>;

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-xl font-semibold tracking-tight">Customer care</h1>
        <p className="mt-1 max-w-3xl text-sm text-muted">
          Record a delay as soon as operations confirm it, and every waiting passenger with Groundtime gets a plan for
          it: somewhere near the airport when there&apos;s time, the terminal when there isn&apos;t. Dietary needs show
          only as met, never what they are.
        </p>
      </header>

      {message && <Notice tone="ok">{message}</Notice>}

      <Board
        version={version}
        onChanged={(text, flightId) => {
          setMessage(text);
          if (chosen === flightId) setCare(null);
          setVersion((v) => v + 1);
        }}
      />

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
        <Panel title="Delayed now" icon={<Clock3 size={14} className="text-accent" />}>
          {error ? (
            <Notice tone="error">{error}</Notice>
          ) : !flights ? (
            <Spinner className="text-muted" />
          ) : !flights.length ? (
            <Empty icon={<Clock3 size={22} />}>No delayed flights still to leave.</Empty>
          ) : (
            <ul className="flex flex-col gap-2">
              {flights.map((f) => (
                <li key={f.flight_id}>
                  <button
                    type="button"
                    aria-pressed={chosen === f.flight_id}
                    onClick={() => {
                      if (f.flight_id === chosen) return;
                      setCare(null);
                      setCareError(null);
                      setChosen(f.flight_id);
                    }}
                    className={cx(
                      "lift w-full rounded-lg border p-3 text-left transition-colors",
                      chosen === f.flight_id ? "border-accent bg-accent-soft/60" : "border-line hover:bg-sunken",
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-semibold">
                        <Mono>{f.flight_no}</Mono> {f.from} → {f.to}
                      </span>
                    </div>
                    <div className="mt-1.5">
                      <Late minutes={f.delay_minutes} expected={f.expected_departure_local} />
                    </div>
                    <p className="mt-1.5 text-xs text-muted">
                      {f.with_app} with Groundtime · {f.booked} booked
                      {f.reason && f.reason !== "Not given" && <> · {f.reason}</>}
                    </p>
                    <div className="mt-1">
                      <DelayCount record={f} />
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel
          title={care ? `${care.flight_no} ${care.from} → ${care.to}` : "Waiting passengers"}
          icon={<Users size={14} className="text-accent" />}
          action={
            care && (
              <span className="text-xs text-muted">
                {care.by_mode.city} near the airport · {care.by_mode.terminal} in the terminal
              </span>
            )
          }
        >
          {!chosen ? (
            <Empty icon={<HeartHandshake size={22} />}>Pick a delayed flight to see every passenger&apos;s plan.</Empty>
          ) : careError ? (
            <Notice tone="error">{careError}</Notice>
          ) : !care ? (
            <Spinner className="text-muted" />
          ) : (
            <div className="flex flex-col gap-3">
              {care.travellers.length === 0 ? (
                <Empty icon={<Users size={22} />}>Nobody on this flight uses Groundtime yet.</Empty>
              ) : (
                <ul className="flex flex-col gap-3">
                  {care.travellers.map((t, i) => (
                    <li key={`${t.name}-${i}`} className="rounded-lg border border-line p-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-semibold">{t.name}</span>
                        <span
                          className={cx(
                            "rounded px-1.5 py-0.5 text-[11px] font-medium",
                            t.wait.mode === "city" ? "bg-accent-soft text-[#173f63]" : "bg-sunken text-[#353736]",
                          )}
                        >
                          {t.wait.mode === "city" ? "Near the airport" : "In the terminal"}
                        </span>
                        <span className="ml-auto">
                          {t.dietary_needs_met === null ? null : t.dietary_needs_met ? (
                            <span className="inline-flex items-center gap-1 text-xs text-ok">
                              <CheckCircle2 size={13} /> Dietary needs met
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-xs text-critical">
                              <XCircle size={13} /> Dietary needs not met
                            </span>
                          )}
                        </span>
                      </div>
                      <p className="mt-1.5 text-sm">{t.wait.staff_summary}</p>
                      <p className="mt-1.5 text-xs text-muted">{planSummary(t)}</p>
                      {t.wait.mode === "city" && t.back_at_terminal_local && (
                        <p className="mt-1 text-xs text-muted">
                          Back at the terminal by <Mono>{hhmm(t.back_at_terminal_local)}</Mono>
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              )}
              {care.note && <p className="text-xs text-muted">{care.note}</p>}
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}
