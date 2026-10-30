"use client";

import { LocateFixed, MapPin } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button, cx, Spinner } from "@/components/ui";
import { POSITIONS, positionFromFix, type Position } from "@/lib/groundtime";

type Point = { lat: number; lon: number };

/** One reading from this device, or why there isn't one. */
function locate(): Promise<{ lat: number; lon: number; accuracy: number }> {
  return new Promise((resolve, reject) => {
    if (!("geolocation" in navigator)) {
      reject(new Error("This browser can't share a location."));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ lat: p.coords.latitude, lon: p.coords.longitude, accuracy: p.coords.accuracy }),
      (e) =>
        reject(
          new Error(
            e.code === e.PERMISSION_DENIED
              ? "Location is turned off for this site, so tell us below instead."
              : "Couldn't get a location just now. Tell us below instead.",
          ),
        ),
      { enableHighAccuracy: true, timeout: 15_000, maximumAge: 60_000 },
    );
  });
}

/** Where the traveller is: from this device's location when they allow it, else what they
 * tap. The location is compared with the airport here, in the browser; only "at the
 * airport" or "not yet" is sent to Groundtime. */
export function WhereNow({
  position,
  airport,
  airportName,
  moving,
  onMove,
}: {
  position: Position;
  airport: Point | null;
  airportName: string;
  moving: boolean;
  onMove: (position: Position) => Promise<void>;
}) {
  const [checking, setChecking] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const checkedOnOpen = useRef(false);

  const check = useCallback(
    async (quiet: boolean) => {
      if (!airport) return;
      setChecking(true);
      if (!quiet) setNote(null);
      try {
        const found = positionFromFix(airport, await locate());
        if (found === null) {
          if (!quiet) setNote("Your location is too rough to tell. Tell us below instead.");
        } else if (found !== position) {
          await onMove(found);
          setNote(
            found === "airport"
              ? `Your location shows you at ${airportName}, so your plan now stays inside the terminal.`
              : `Your location shows you aren't at ${airportName} yet, so your plan can start near it.`,
          );
        } else if (!quiet) {
          setNote(found === "airport" ? `You're at ${airportName}.` : `You're not at ${airportName} yet.`);
        }
      } catch (err) {
        if (!quiet) setNote(err instanceof Error ? err.message : "Couldn't get a location.");
      } finally {
        setChecking(false);
      }
    },
    [airport, airportName, onMove, position],
  );

  // Already allowed on this site: check once when the trip opens, without asking.
  useEffect(() => {
    if (checkedOnOpen.current || !airport || !navigator.permissions) return;
    checkedOnOpen.current = true;
    navigator.permissions
      .query({ name: "geolocation" })
      .then((p) => {
        if (p.state === "granted") void check(true);
      })
      .catch(() => undefined);
  }, [airport, check]);

  return (
    <fieldset>
      <legend className="mb-2 flex w-full flex-wrap items-center justify-between gap-2 text-sm font-medium">
        Where are you now?
        {airport && (
          <Button tone="ghost" disabled={checking || moving} onClick={() => check(false)}>
            {checking ? <Spinner /> : <LocateFixed size={13} />} Use my location
          </Button>
        )}
      </legend>
      <div className="grid gap-2 sm:grid-cols-2">
        {POSITIONS.map(([value, label]) => (
          <button
            key={value}
            type="button"
            aria-pressed={position === value}
            disabled={moving || checking}
            onClick={() => position !== value && onMove(value)}
            className={cx(
              "rounded-lg border px-3 py-2 text-sm transition-colors disabled:cursor-wait",
              position === value ? "border-accent bg-accent-soft font-semibold text-[#173f63]" : "border-line hover:bg-sunken",
            )}
          >
            {label}
          </button>
        ))}
      </div>
      <p className="mt-2 flex items-start gap-1.5 text-xs text-muted">
        <MapPin size={12} className="mt-0.5 shrink-0" />
        {note ??
          "Your location is checked on this device and never stored; Groundtime keeps only whether you're at the airport."}
      </p>
    </fieldset>
  );
}
