"use client";

import { BedDouble, Clock3, MoonStar, Plane, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { AirlineBadge, airlineOf } from "@/components/airline";
import { useMe } from "@/components/me";
import { Bullets, Late } from "@/components/plan";
import { TasteMatch, TastePicker } from "@/components/taste";
import { day, Empty, Mono, Notice, Panel, Spinner } from "@/components/ui";
import { tool } from "@/lib/client";
import { distance, duration, hhmm, later, rejections, type Layover, type MyFlights } from "@/lib/groundtime";

function Flights({ flights }: { flights: MyFlights }) {
  return (
    <Panel title="My flights" icon={<Plane size={14} className="text-accent" />}>
      {flights.days.length === 0 ? (
        <Empty icon={<MoonStar size={22} />}>No duty in the week ahead.</Empty>
      ) : (
        <ol className="flex flex-col gap-3">
          {flights.days.map((d) => (
            <li key={`${d.pairing_id}-${d.date}`} className="rounded-lg border border-line p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-sm font-semibold">{day(d.date)}</span>
                <span className="text-xs text-muted">
                  <Mono>{d.pairing_id}</Mono> · {d.role}
                </span>
              </div>
              <p className="mt-1 flex items-center gap-1.5 text-xs text-muted">
                <Clock3 size={12} /> Report <Mono>{hhmm(d.report_local)}</Mono> · Release{" "}
                <Mono>{hhmm(d.release_local)}</Mono>
              </p>
              <ul className="mt-2 flex flex-col gap-1.5">
                {d.legs.map((leg) => (
                  <li key={leg.flight_id} className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
                    <AirlineBadge code={airlineOf(leg.flight_no)} compact />
                    <Mono className="font-medium">{leg.flight_no}</Mono>
                    <span>
                      {leg.from} <Mono className="text-muted">{hhmm(leg.departs_local)}</Mono> → {leg.to}{" "}
                      <Mono className="text-muted">{hhmm(leg.arrives_local)}</Mono>
                    </span>
                    <Late minutes={leg.delay_minutes} expected={later(leg.departs_local, leg.delay_minutes)} />
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ol>
      )}
      <p className="mt-3 text-[11px] text-muted">Times are local, in India.</p>
    </Panel>
  );
}

/** The next night stop: the free evening, and places Qloo ranks for this crew member's
 * taste, each checked to be open, close to the hotel and right for their diet. */
function LayoverCard({ brief }: { brief: Layover }) {
  if (!brief.night_stop) return <Empty icon={<MoonStar size={22} />}>{brief.note}</Empty>;
  const w = brief.window;
  const needed = brief.dietary_needed ?? [];
  const rejected = rejections(brief.rejected);
  return (
    <div className="flex flex-col gap-4">
      <div>
        <p className="text-sm font-semibold">
          {w.city || w.station}
          {w.hotel_area && <span className="font-normal text-muted"> · {w.hotel_area}</span>}
        </p>
        <p className="mt-0.5 text-xs text-muted">
          {day(brief.night_stop.date)} · <Mono>{brief.night_stop.pairing_id}</Mono> · {w.rest_hours} h rest
          {brief.night_stop.cause === "delay" && " · moved by a delay"}
        </p>
      </div>
      <dl className="grid grid-cols-3 gap-3 text-sm">
        <div>
          <dt className="text-xs text-muted">Free from</dt>
          <dd className="font-mono">{hhmm(w.free_from_local)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted">Meal at</dt>
          <dd className="font-mono">{hhmm(w.meal_at_local)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted">Asleep by</dt>
          <dd className="font-mono">{hhmm(w.sleep_by_local)}</dd>
        </div>
      </dl>
      <p className="text-xs text-muted">
        {duration(w.free_minutes)} free
        {w.tiring ? " after a long day, so somewhere quiet and close." : "."}
      </p>
      {brief.picks.length === 0 ? (
        <p className="text-sm text-muted">No place fits this evening.</p>
      ) : (
        <ol className="flex flex-col gap-3">
          {brief.picks.map((p, i) => (
            <li key={`${p.name}-${i}`} className="rounded-lg border border-line p-3">
              <p className="flex flex-wrap items-center gap-2 text-sm font-semibold">
                {p.name} <TasteMatch affinity={p.affinity} />
              </p>
              <p className="mt-0.5 text-xs text-muted">
                {[
                  distance(p.distance_m),
                  p.open_until && `open until ${hhmm(p.open_until)}`,
                  p.genres.slice(0, 3).join(", "),
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
              <Bullets why={p.why} />
            </li>
          ))}
        </ol>
      )}
      {brief.dietary_needs_met && needed.length > 0 && brief.picks.length > 0 && (
        <p className="flex items-center gap-1.5 text-xs text-ok">
          <ShieldCheck size={13} /> Every pick serves {needed.join(", ").replace(/_/g, " ")}.
        </p>
      )}
      {brief.note && <p className="text-xs text-muted">{brief.note}</p>}
      <p className="text-[11px] text-muted">
        Looked at {brief.considered} place{brief.considered === 1 ? "" : "s"}
        {rejected.length > 0 && `; left out: ${rejected.map(([reason, n]) => `${reason} (${n})`).join(", ")}`}. Picked
        by Qloo Insights API.
      </p>
    </div>
  );
}

export default function Crew() {
  const me = useMe();
  const [flights, setFlights] = useState<MyFlights | null>(null);
  const [brief, setBrief] = useState<Layover | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [layoverError, setLayoverError] = useState<string | null>(null);

  const loadLayover = useCallback(() => {
    tool<Layover>("my_layover").then(
      (b) => {
        setBrief(b);
        setLayoverError(null);
      },
      (err: Error) => setLayoverError(err.message),
    );
  }, []);
  useEffect(() => {
    if (!me.crew_id) return;
    tool<MyFlights>("my_flights").then(setFlights, (err: Error) => setError(err.message));
    loadLayover();
  }, [me.crew_id, loadLayover]);

  if (!me.crew_id) return <Notice>This view is for crew. Your account has no crew record.</Notice>;
  if (error) return <Notice tone="error">{error}</Notice>;
  if (!flights)
    return (
      <div className="text-muted">
        <Spinner />
      </div>
    );

  return (
    <div className="flex flex-col gap-6">
      <header>
        <p className="text-sm text-muted">Good to see you</p>
        <h1 className="mt-0.5 text-[22px] font-semibold tracking-tight">{flights.name ?? me.user_id}</h1>
        <p className="mt-1 text-sm text-muted">
          <Mono>{flights.crew_id}</Mono>
          {flights.rank && <> · {flights.rank}</>}
          {flights.base && <> · based at {flights.base}</>}
        </p>
      </header>

      <div className="grid items-start gap-6 lg:grid-cols-2">
        <Flights flights={flights} />
        <Panel title="Your next layover" icon={<BedDouble size={14} className="text-accent" />}>
          {layoverError ? (
            <Notice tone="error">{layoverError}</Notice>
          ) : !brief ? (
            <Spinner className="text-muted" />
          ) : (
            <LayoverCard brief={brief} />
          )}
        </Panel>
      </div>

      <TastePicker
        crew
        onSaved={() => {
          setBrief(null);
          loadLayover();
        }}
      />
    </div>
  );
}
