"use client";

import { Clapperboard, Clock3, DoorOpen, Footprints, MapPin, ShieldCheck, Utensils } from "lucide-react";
import type { ReactNode } from "react";

import { TasteMatch } from "@/components/taste";
import { Mono, Notice } from "@/components/ui";
import { distance, duration, hhmm, lateBy, rejections, type Plan, type Stop, type Watch } from "@/lib/groundtime";

const STOP_ICON = { sight: MapPin, meal: Utensils, terminal: DoorOpen } as const;
const STOP_KIND = { sight: "To see", meal: "To eat", terminal: "In the terminal" } as const;

/** How late a flight is, at a glance; nothing for one on time. */
export function Late({ minutes, expected }: { minutes: number; expected: string | null | undefined }) {
  const text = lateBy(minutes, expected);
  if (!text) return null;
  return (
    <span className="inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded bg-pending-soft px-1.5 py-0.5 text-xs font-semibold text-[#92400e] ring-1 ring-inset ring-[#fde68a]">
      <Clock3 size={11} /> {text}
    </span>
  );
}

export function Bullets({ why }: { why: string[] }) {
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
  const timed = stop.kind !== "terminal";
  return (
    <li className="relative pl-8">
      <span className="absolute left-0 top-0.5 grid h-6 w-6 place-items-center rounded-full bg-accent text-white">
        <Icon size={12} />
      </span>
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
        <span>{STOP_KIND[stop.kind] ?? stop.kind}</span>
        {timed && (
          <Mono className="text-foreground">
            {hhmm(stop.arrive_local)}–{hhmm(stop.leave_local)}
          </Mono>
        )}
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

function Milestone({ icon, children }: { icon: ReactNode; children: ReactNode }) {
  return (
    <li className="relative flex flex-wrap items-center gap-x-2 pl-8 text-sm">
      <span className="absolute left-0 grid h-6 w-6 place-items-center rounded-full bg-sunken text-muted ring-1 ring-line">
        {icon}
      </span>
      {children}
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
          {item.minutes != null && (
            <span>· {item.kind === "series" ? `${item.minutes}-min episodes` : duration(item.minutes)}</span>
          )}
          <TasteMatch affinity={item.affinity} />
        </p>
        <Bullets why={item.why} />
      </div>
    </li>
  );
}

/** The plan for a wait, in order: the stops, when to head back, something to watch, and how
 * it was checked. */
export function PlanView({ plan }: { plan: Plan }) {
  const w = plan.wait;
  const city = w.mode === "city";
  const rejected = rejections(plan.rejected);
  const asked = Object.keys(plan.source?.requests ?? {}).length;
  const needed = plan.dietary_needed ?? [];

  return (
    <div className="flex flex-col gap-5">
      <p className="text-lg leading-snug">{w.headline}</p>
      {w.stay_reason && <Notice>{w.stay_reason}</Notice>}

      <section>
        <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
          <Footprints size={14} className="text-accent" />
          {city ? `Your time near ${w.city || w.station} airport` : "Your time in the terminal"}
        </h3>
        {plan.stops.length === 0 ? (
          <p className="text-sm text-muted">No stops planned for this wait.</p>
        ) : (
          <ol className="relative flex flex-col gap-5 before:absolute before:bottom-2 before:left-3 before:top-2 before:w-px before:bg-line">
            {city && (
              <Milestone icon={<Footprints size={12} />}>
                <span className="font-medium">Free from</span>
                <Mono className="text-muted">{hhmm(w.free_from_local)}</Mono>
              </Milestone>
            )}
            {plan.stops.map((s) => (
              <StopRow key={`${s.entity_id}-${s.arrive_local}`} stop={s} />
            ))}
            {city && plan.head_back_by_local && (
              <Milestone icon={<DoorOpen size={12} />}>
                <span>
                  Leave for the airport by <Mono className="font-semibold">{hhmm(plan.head_back_by_local)}</Mono>; at
                  the terminal by <Mono className="font-semibold">{hhmm(plan.back_at_terminal_local)}</Mono>{" "}
                  <span className="text-muted">(needed by {hhmm(w.at_terminal_by_local)})</span>
                </span>
              </Milestone>
            )}
          </ol>
        )}
        {plan.dietary_needs_met && needed.length > 0 && plan.stops.length > 0 && (
          <p className="mt-4 flex items-center gap-1.5 text-xs text-ok">
            <ShieldCheck size={13} /> Every food stop serves {needed.join(", ").replace(/_/g, " ")}.
          </p>
        )}
      </section>

      {plan.watch.length > 0 && (
        <section>
          <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
            <Clapperboard size={14} className="text-accent" />
            Something to watch
          </h3>
          <ul className="grid gap-3 sm:grid-cols-2">
            {plan.watch.map((item) => (
              <WatchCard key={item.entity_id} item={item} />
            ))}
          </ul>
        </section>
      )}

      {plan.note && <p className="text-sm text-muted">{plan.note}</p>}

      <details className="rounded-lg border border-line px-4 py-3 text-sm">
        <summary className="cursor-pointer font-medium">How this was checked</summary>
        <div className="mt-2 flex flex-col gap-2 text-muted">
          <p>
            Looked at {plan.considered} place{plan.considered === 1 ? "" : "s"}
            {asked ? ` from ${asked} request${asked === 1 ? "" : "s"}` : ""}. Every stop kept was checked for opening
            hours, your dietary needs and getting back in time.
            {plan.taste_shared === false && " No picks saved yet, so these are popular rather than picked for you."}
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
            <p>Qloo couldn&apos;t answer for: {(plan.unavailable ?? []).join(", ")}. The rest of the plan stands.</p>
          )}
          <p className="text-xs">Picked by {plan.source?.provider ?? "Qloo Insights API"}.</p>
        </div>
      </details>
    </div>
  );
}
