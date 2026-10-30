"use client";

import { CheckCircle2, Clock3, HeartHandshake, Pencil, Plane, Users, XCircle } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { useMe } from "@/components/me";
import { Late } from "@/components/plan";
import { Button, cx, Empty, Mono, Notice, Panel, Spinner } from "@/components/ui";
import { tool } from "@/lib/client";
import {
  delayMinutes,
  duration,
  hhmm,
  LAST_BOOKABLE,
  planSummary,
  QUICK_DELAYS,
  todayInIndia,
  type BoardRow,
  type DelayedFlight,
  type FlightCare,
} from "@/lib/groundtime";

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
        if (value !== null) save(value);
      }}
    >
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
      {minutes.trim() && value === null && (
        <p className="text-xs text-critical">A delay is whole minutes, up to 12 hours.</p>
      )}
      {error && <Notice tone="error">{error}</Notice>}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" tone="accent" disabled={busy || value === null}>
          {busy && <Spinner />} Save
        </Button>
        {row.delay_minutes > 0 && (
          <Button type="button" tone="secondary" disabled={busy} onClick={() => save(0)}>
            Clear
          </Button>
        )}
        <Button type="button" tone="ghost" disabled={busy} onClick={onClose}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function Board({ onChanged, version }: { onChanged: (message: string, flightId: string) => void; version: number }) {
  const [date, setDate] = useState(todayInIndia);
  const [rows, setRows] = useState<BoardRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);

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
      {error ? (
        <Notice tone="error">{error}</Notice>
      ) : !rows ? (
        <Spinner className="text-muted" />
      ) : rows.length === 0 ? (
        <Empty icon={<Plane size={22} />}>No departures that day.</Empty>
      ) : (
        <ul className="flex flex-col divide-y divide-rule">
          {rows.map((r) => (
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
                        <Pencil size={13} /> Record delay
                      </Button>
                    )
                  )}
                </span>
              </div>
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
                          {t.dietary_needs_met ? (
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
