"use client";

import { CheckCircle2, Clock3, HeartHandshake, Plane, Users } from "lucide-react";
import { useEffect, useState } from "react";

import { Info } from "@/components/info";
import { clock, cx, day, Empty, Mono, Notice, Panel, Spinner } from "@/components/ui";
import { tool } from "@/lib/client";
import { duration, hhmm, planSummary, POSITIONS, type DelayedFlight, type FlightCare } from "@/lib/groundtime";

const WHERE = Object.fromEntries(POSITIONS);

export default function Care() {
  const [flights, setFlights] = useState<DelayedFlight[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [chosen, setChosen] = useState<string | null>(null);
  const [care, setCare] = useState<FlightCare | null>(null);
  const [careError, setCareError] = useState<string | null>(null);

  useEffect(() => {
    tool<DelayedFlight[]>("delayed_flights").then(setFlights, (err: Error) => setError(err.message));
  }, []);

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
  }, [chosen]);

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-xl font-semibold tracking-tight">Customer care</h1>
        <p className="mt-1 max-w-3xl text-sm text-muted">
          For every delayed flight, each passenger with Groundtime has a plan for the wait: places in the city when
          there is time to leave and get back, the terminal when there isn&apos;t, and something to watch that ends
          before boarding. Offer it at the desk; dietary needs show only as met, never what they are.
        </p>
      </header>

      {error && <Notice tone="error">{error}</Notice>}

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
        <Panel title="Delayed flights" icon={<Plane size={14} className="text-accent" />}>
          {!flights && !error ? (
            <Spinner className="text-muted" />
          ) : !flights?.length ? (
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
                      <span className="rounded bg-pending-soft px-1.5 py-0.5 text-xs font-medium text-[#92400e] ring-1 ring-inset ring-[#fde68a]">
                        +{duration(f.delay_minutes)}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-muted">
                      {day(f.scheduled_utc)} <Mono>{clock(f.scheduled_utc)}</Mono> · {f.booked} booked · {f.with_app}{" "}
                      with Groundtime
                    </p>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel
          title={care ? `${care.flight_no} ${care.from} → ${care.to}` : "Passengers"}
          icon={<Users size={14} className="text-accent" />}
          action={
            care && (
              <span className="text-xs text-muted">
                {care.by_mode.city} in the city · {care.by_mode.terminal} in the terminal
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
              {care.note && <p className="text-sm text-muted">{care.note}</p>}
              {care.travellers.length === 0 ? (
                <Empty icon={<Users size={22} />}>Nobody on this flight uses Groundtime yet.</Empty>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="text-xs text-muted">
                      <tr className="border-b border-rule">
                        <th className="py-2 pr-3 font-medium">Passenger</th>
                        <th className="py-2 pr-3 font-medium">
                          <span className="inline-flex items-center gap-1">
                            Where <Info term="airside" />
                          </span>
                        </th>
                        <th className="py-2 pr-3 font-medium">Plan</th>
                        <th className="py-2 pr-3 font-medium">Dietary</th>
                        <th className="py-2 font-medium">Back at terminal</th>
                      </tr>
                    </thead>
                    <tbody>
                      {care.travellers.map((t) => (
                        <tr key={t.username} className="border-b border-rule align-top last:border-0">
                          <td className="py-2.5 pr-3 font-medium">{t.name}</td>
                          <td className="py-2.5 pr-3 text-xs">
                            {WHERE[t.wait.position] ?? t.wait.position}
                            <span
                              className={cx(
                                "ml-1.5 rounded px-1.5 py-0.5 text-[11px] font-medium",
                                t.wait.mode === "city" ? "bg-accent-soft text-[#173f63]" : "bg-sunken text-[#353736]",
                              )}
                            >
                              {t.wait.mode === "city" ? "City" : "Terminal"}
                            </span>
                          </td>
                          <td className="py-2.5 pr-3 text-xs text-foreground">{planSummary(t)}</td>
                          <td className="py-2.5 pr-3">
                            {t.dietary_needs_met ? (
                              <span
                                className="inline-flex items-center gap-1 text-xs text-ok"
                                title="Dietary needs met"
                              >
                                <CheckCircle2 size={14} /> Met
                              </span>
                            ) : (
                              <span className="text-xs text-critical">Not met</span>
                            )}
                          </td>
                          <td className="py-2.5">
                            <Mono>{t.wait.mode === "city" ? hhmm(t.back_at_terminal_local) : "—"}</Mono>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}
