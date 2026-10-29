"use client";

import { Clapperboard, DoorOpen, Footprints, MapPin, Plane, ShieldCheck, Utensils } from "lucide-react";
import { useCallback, useEffect, useState, type ReactNode } from "react";

import { Info } from "@/components/info";
import { useMe } from "@/components/me";
import { TasteMatch, TastePicker } from "@/components/taste";
import { cx, Empty, Mono, Notice, Panel, Spinner } from "@/components/ui";
import { tool } from "@/lib/client";
import {
  distance,
  duration,
  hhmm,
  POSITIONS,
  rejections,
  type MyGroundtime,
  type Position,
  type Stop,
  type Watch,
} from "@/lib/groundtime";

const STOP_ICON = { sight: MapPin, meal: Utensils, terminal: DoorOpen } as const;

function Bullets({ why }: { why: string[] }) {
  if (!why.length) return null;
  return (
    <ul className="mt-1.5 flex flex-col gap-0.5 text-xs text-muted">
      {why.map((w) => (
        <li key={w} className="flex gap-1.5">
          <span aria-hidden>·</span>
          {w}
        </li>
      ))}
    </ul>
  );
}

function StopRow({ stop }: { stop: Stop }) {
  const Icon = STOP_ICON[stop.kind] ?? MapPin;
  return (
    <li className="relative pl-8">
      <span className="absolute left-0 top-0.5 grid h-6 w-6 place-items-center rounded-full bg-accent text-white">
        <Icon size={12} />
      </span>
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
        <Mono className="text-foreground">
          {hhmm(stop.arrive_local)}–{hhmm(stop.leave_local)}
        </Mono>
        {stop.ride_minutes != null && stop.ride_minutes > 0 && <span>{stop.ride_minutes} min ride</span>}
        {distance(stop.distance_m) && <span>{distance(stop.distance_m)} away</span>}
      </p>
      <p className="mt-0.5 flex flex-wrap items-center gap-2 text-sm font-semibold">
        {stop.website ? (
          <a href={stop.website} target="_blank" rel="noreferrer" className="hover:underline">
            {stop.name}
          </a>
        ) : (
          stop.name
        )}
        <TasteMatch affinity={stop.affinity} />
      </p>
      {stop.genres.length > 0 && <p className="text-xs text-muted">{stop.genres.slice(0, 4).join(", ")}</p>}
      <Bullets why={stop.why} />
    </li>
  );
}

function Milestone({ icon, label, time }: { icon: ReactNode; label: string; time: string | null }) {
  return (
    <li className="relative flex items-center gap-2 pl-8 text-sm">
      <span className="absolute left-0 grid h-6 w-6 place-items-center rounded-full bg-sunken text-muted ring-1 ring-line">
        {icon}
      </span>
      <span className="font-medium">{label}</span>
      <Mono className="text-muted">{hhmm(time)}</Mono>
    </li>
  );
}

function WatchCard({ item }: { item: Watch }) {
  return (
    <li className="flex gap-3 rounded-lg border border-line p-3">
      {item.image ? (
        // Qloo's image hosts vary; a plain img keeps them out of the build config.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={item.image} alt="" className="h-20 w-14 shrink-0 rounded object-cover" />
      ) : (
        <span className="grid h-20 w-14 shrink-0 place-items-center rounded bg-sunken text-muted">
          <Clapperboard size={18} />
        </span>
      )}
      <div className="min-w-0">
        <p className="text-sm font-semibold">
          {item.title}
          {item.year && <span className="font-normal text-muted"> ({item.year})</span>}
        </p>
        <p className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-muted">
          {item.kind === "series" ? "Series" : "Film"}
          {item.minutes != null && <span>· {duration(item.minutes)}</span>}
          <TasteMatch affinity={item.affinity} />
        </p>
        <Bullets why={item.why} />
      </div>
    </li>
  );
}

export default function Trip() {
  const me = useMe();
  const [position, setPosition] = useState<Position | null>(null);
  const [plan, setPlan] = useState<MyGroundtime | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchPlan = useCallback((where: Position | null) => {
    tool<MyGroundtime>("my_groundtime", where ? { position: where } : {})
      .then(setPlan, (err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);
  useEffect(() => fetchPlan(null), [fetchPlan]);

  function load(where: Position | null) {
    setLoading(true);
    setError(null);
    fetchPlan(where);
  }

  if (!me.roles.includes("traveller")) return <Notice>This view is for passengers with a booking.</Notice>;
  if (!plan && loading)
    return (
      <div className="text-muted">
        <Spinner />
      </div>
    );
  if (!plan) return <Notice tone="error">{error ?? "No trip found."}</Notice>;

  const w = plan.wait;
  const city = w.mode === "city";
  const shown = position ?? w.position;
  const rejected = rejections(plan.rejected);

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <header>
        <p className="text-sm text-muted">Hello{plan.traveller?.name ? `, ${plan.traveller.name}` : ""}</p>
        <h1 className="mt-0.5 text-[22px] font-semibold tracking-tight">
          {duration(w.wait_minutes)} at {w.city || w.station}, planned
        </h1>
      </header>

      <section className="rounded-lg border border-line bg-surface p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="flex items-center gap-2 text-lg font-semibold">
              <Plane size={18} className="text-accent" />
              <Mono>{w.flight_no}</Mono> <span className="text-muted">→</span> {w.to}
            </p>
            <p className="mt-1 text-sm text-muted">
              From {w.airport || w.station}
              {w.connecting_from && <> · connecting from {w.connecting_from}</>}
            </p>
          </div>
          {w.delay_minutes > 0 && (
            <span className="rounded bg-pending-soft px-2 py-1 text-xs font-semibold text-[#92400e] ring-1 ring-inset ring-[#fde68a]">
              Delayed {duration(w.delay_minutes)}
            </span>
          )}
        </div>
        <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-4">
          <div>
            <dt className="text-xs text-muted">Scheduled</dt>
            <dd className={cx("font-mono", w.delay_minutes > 0 && "text-muted line-through")}>
              {hhmm(w.scheduled_departure_local)}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted">Expected</dt>
            <dd className="font-mono font-semibold">{hhmm(w.expected_departure_local)}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted">Be at the gate by</dt>
            <dd className="font-mono font-semibold">{hhmm(w.at_gate_by_local)}</dd>
          </div>
          {city && (
            <div>
              <dt className="text-xs text-muted">Back at the terminal door by</dt>
              <dd className="font-mono font-semibold">{hhmm(w.at_terminal_by_local)}</dd>
            </div>
          )}
        </dl>
        <p className="mt-3 text-[11px] text-muted">Local time at {w.station}.</p>
      </section>

      <fieldset>
        <legend className="mb-2 flex items-center gap-1.5 text-sm font-medium">
          Where are you now? <Info term="airside" />
        </legend>
        <div className="grid gap-2 sm:grid-cols-3">
          {POSITIONS.map(([value, label]) => (
            <button
              key={value}
              type="button"
              aria-pressed={shown === value}
              disabled={loading}
              onClick={() => {
                setPosition(value);
                load(value);
              }}
              className={cx(
                "rounded-lg border px-3 py-2 text-sm transition-colors disabled:cursor-wait",
                shown === value
                  ? "border-accent bg-accent-soft font-semibold text-[#173f63]"
                  : "border-line hover:bg-sunken",
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </fieldset>

      {error && <Notice tone="error">{error}</Notice>}
      {w.stay_reason && <Notice>{w.stay_reason}</Notice>}
      {plan.note && <p className="text-sm text-muted">{plan.note}</p>}

      <Panel
        title={city ? `Your time in ${w.city || w.station}` : "Your time in the terminal"}
        icon={<Footprints size={14} className="text-accent" />}
        action={loading ? <Spinner className="text-muted" /> : undefined}
      >
        {plan.stops.length === 0 ? (
          <Empty icon={<DoorOpen size={22} />}>No stops planned for this wait.</Empty>
        ) : (
          <ol className="relative flex flex-col gap-5 before:absolute before:bottom-2 before:left-3 before:top-2 before:w-px before:bg-line">
            <Milestone icon={<Footprints size={12} />} label="Free from" time={w.free_from_local} />
            {plan.stops.map((s) => (
              <StopRow key={`${s.entity_id}-${s.arrive_local}`} stop={s} />
            ))}
            {plan.head_back_by_local && (
              <Milestone icon={<Footprints size={12} />} label="Head back by" time={plan.head_back_by_local} />
            )}
            {plan.back_at_terminal_local && (
              <Milestone
                icon={<DoorOpen size={12} />}
                label="Back at the terminal"
                time={plan.back_at_terminal_local}
              />
            )}
          </ol>
        )}
        {plan.dietary_needs_met && (plan.dietary_needed ?? []).length > 0 && (
          <p className="mt-4 flex items-center gap-1.5 text-xs text-ok">
            <ShieldCheck size={13} /> Every meal stop serves {(plan.dietary_needed ?? []).join(", ").replace(/_/g, " ")}
            .
          </p>
        )}
      </Panel>

      {plan.watch.length > 0 && (
        <Panel
          title={city ? "For the flight" : "For the wait"}
          icon={<Clapperboard size={14} className="text-accent" />}
        >
          <ul className="grid gap-3 sm:grid-cols-2">
            {plan.watch.map((item) => (
              <WatchCard key={item.entity_id} item={item} />
            ))}
          </ul>
        </Panel>
      )}

      <details className="rounded-lg border border-line px-4 py-3 text-sm">
        <summary className="cursor-pointer font-medium">How this was checked</summary>
        <div className="mt-2 flex flex-col gap-2 text-muted">
          <p>
            Considered {plan.considered} place{plan.considered === 1 ? "" : "s"} from Qloo
            {plan.source?.requests ? ` in ${plan.source.requests} request${plan.source.requests === 1 ? "" : "s"}` : ""}
            ; each kept stop was checked for opening hours, your dietary needs and getting back in time.
            {plan.taste_shared === false && " No picks saved yet, so Qloo ranked by popularity."}
          </p>
          {rejected.length > 0 && (
            <ul className="flex flex-col gap-0.5">
              {rejected.map(([reason, n]) => (
                <li key={reason}>
                  <Mono>{n}</Mono> left out: {reason}
                </li>
              ))}
            </ul>
          )}
          {(plan.unavailable ?? []).length > 0 && (
            <p>Not available right now: {(plan.unavailable ?? []).join(", ")}.</p>
          )}
        </div>
      </details>

      <TastePicker onSaved={() => load(position)} />
    </div>
  );
}
