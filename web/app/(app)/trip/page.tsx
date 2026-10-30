"use client";

import { ArrowRight, Heart, Plus, Sparkles } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { AirlineBadge, airlineOf } from "@/components/airline";
import { Booking } from "@/components/booking";
import { CareDesk } from "@/components/care-desk";
import { Concierge } from "@/components/concierge";
import { useMe } from "@/components/me";
import { Late, PlanView } from "@/components/plan";
import { TastePicker } from "@/components/taste";
import { Button, cx, day, Mono, Notice, Panel, Spinner } from "@/components/ui";
import { WhereNow } from "@/components/where";
import { tool } from "@/lib/client";
import { hhmm, later, type BookedLeg, type MyGroundtime, type MyTrip, type Position } from "@/lib/groundtime";

function LegRow({ leg }: { leg: BookedLeg }) {
  const late = leg.delay_minutes > 0;
  return (
    <li className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5 py-3 first:pt-0 last:pb-0">
      <div className="flex min-w-0 items-center gap-2">
        <AirlineBadge code={airlineOf(leg.flight_no)} compact />
        <Mono className="font-semibold">{leg.flight_no}</Mono>
        <span className="text-sm">
          {leg.from} <span className="text-muted">→</span> {leg.to}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-muted">{day(leg.departs_local.slice(0, 10))}</span>
        <Mono className={cx(late && "text-muted line-through")}>{hhmm(leg.departs_local)}</Mono>
        <span className="text-muted">to</span>
        <Mono>{hhmm(late ? later(leg.arrives_local, leg.delay_minutes) : leg.arrives_local)}</Mono>
        <Late minutes={leg.delay_minutes} expected={leg.expected_departure_local} />
      </div>
    </li>
  );
}

function Booked({
  trip,
  onChange,
  onBookAnother,
}: {
  trip: Extract<MyTrip, { booked: true }>;
  onChange: () => Promise<void>;
  onBookAnother: () => void;
}) {
  const [plan, setPlan] = useState<MyGroundtime | null>(null);
  const [planning, setPlanning] = useState(false);
  const [moving, setMoving] = useState(false);
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const w = trip.wait;

  async function planMyTime() {
    setPlanning(true);
    setError(null);
    try {
      setPlan(await tool<MyGroundtime>("my_groundtime"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not plan your time.");
    } finally {
      setPlanning(false);
    }
  }

  // Anything that changes the wait makes a plan already shown out of date: plan it again.
  async function changed() {
    await onChange();
    if (plan) await planMyTime();
  }

  async function move(position: Position) {
    setMoving(true);
    setError(null);
    try {
      await tool("set_position", { position });
      await changed();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not change that.");
    } finally {
      setMoving(false);
    }
  }

  const taste = editing ? (
    <TastePicker onSaved={changed} onClose={() => setEditing(false)} />
  ) : (
    <Panel title="What you love" icon={<Heart size={14} className="text-accent" />}>
      <p className="text-sm text-muted">
        {trip.taste.loves.length
          ? trip.taste.loves.map((l) => l.name).join(", ")
          : "Nothing saved yet, so plans show what's popular."}
      </p>
      <Button tone="secondary" className="mt-3" onClick={() => setEditing(true)}>
        <Heart size={14} /> Edit what I love
      </Button>
    </Panel>
  );

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm text-muted">Hello{trip.name ? `, ${trip.name}` : ""}</p>
          <h1 className="mt-0.5 text-[22px] font-semibold tracking-tight">Your trip</h1>
        </div>
        <Button tone="secondary" onClick={onBookAnother}>
          <Plus size={14} /> Book another trip
        </Button>
      </header>

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
        <div className="flex min-w-0 flex-col gap-6">
          <section className="rounded-lg border border-line bg-surface p-5">
            <ul className="flex flex-col divide-y divide-rule">
              {trip.legs.map((leg) => (
                <LegRow key={leg.flight_id} leg={leg} />
              ))}
            </ul>
            <p className="mt-3 text-[11px] text-muted">Times are local, in India.</p>
          </section>

          {w ? (
            <p className="text-xl leading-snug tracking-tight sm:text-2xl">{w.headline}</p>
          ) : (
            <Notice>Every flight on this booking has left. Have a good trip.</Notice>
          )}

          {w && !w.connecting_from && (
            <WhereNow
              position={trip.position}
              airport={trip.airport_point}
              airportName={`${w.city} airport`}
              moving={moving}
              onMove={move}
            />
          )}

          {error && <Notice tone="error">{error}</Notice>}

          {w && (
            <Panel
              title="Your time, planned"
              icon={<Sparkles size={14} className="text-accent" />}
              action={
                plan && (
                  <Button tone="ghost" disabled={planning} onClick={planMyTime}>
                    {planning && <Spinner />} Plan again
                  </Button>
                )
              }
            >
              {plan ? (
                <PlanView plan={plan} />
              ) : (
                <div className="flex flex-col items-start gap-3">
                  <p className="text-sm text-muted">
                    Places, food and something to watch, picked by Qloo for what you love, each checked for opening
                    hours, your dietary needs and getting to your gate in time.
                  </p>
                  <Button tone="accent" className="h-10 px-4" disabled={planning} onClick={planMyTime}>
                    {planning ? <Spinner /> : <ArrowRight size={15} />} Plan my time
                  </Button>
                </div>
              )}
            </Panel>
          )}
        </div>

        <aside className="flex min-w-0 flex-col gap-6 lg:sticky lg:top-4">
          {w && <Concierge onMoved={changed} />}
          {taste}
          <CareDesk desk={trip.care} />
        </aside>
      </div>
    </div>
  );
}

export default function Trip() {
  const me = useMe();
  const [trip, setTrip] = useState<MyTrip | null>(null);
  const [booking, setBooking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    () =>
      tool<MyTrip>("my_trip").then(
        (t) => {
          setTrip(t);
          setError(null);
        },
        (err: Error) => setError(err.message),
      ),
    [],
  );
  const traveller = me.roles.includes("traveller");
  useEffect(() => {
    if (traveller) load();
  }, [traveller, load]);

  if (!traveller) return <Notice>This view is for travellers.</Notice>;
  if (error && !trip) return <Notice tone="error">{error}</Notice>;
  if (!trip)
    return (
      <div className="text-muted">
        <Spinner />
      </div>
    );

  if (!trip.booked || booking) {
    return (
      <Booking
        onBooked={() => {
          setBooking(false);
          setTrip(null);
          load();
        }}
        onCancel={trip.booked ? () => setBooking(false) : undefined}
        care={trip.care}
      />
    );
  }
  return (
    <Booked
      key={trip.legs.map((l) => l.flight_id).join("+")}
      trip={trip}
      onChange={load}
      onBookAnother={() => setBooking(true)}
    />
  );
}
