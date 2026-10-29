// What the Groundtime tools return, and the small helpers the trip, care and crew pages
// share. Every time here is the station's local time, as the server writes it.

export type Position = "away" | "landside" | "airside";

export type Wait = {
  station: string;
  city: string;
  airport: string;
  flight_id: string;
  flight_no: string;
  to: string;
  scheduled_departure_local: string;
  expected_departure_local: string;
  delay_minutes: number;
  connecting_from: string | null;
  position: Position;
  can_leave: boolean;
  mode: "city" | "terminal";
  stay_reason: string | null;
  free_from_local: string;
  at_terminal_by_local: string;
  at_gate_by_local: string;
  outside_minutes: number;
  wait_minutes: number;
  timezone: string;
};

export type Stop = {
  entity_id: string;
  name: string;
  address: string | null;
  distance_m: number | null;
  affinity: number | null;
  rating: number | null;
  price_level: number | null;
  dietary: string[];
  noise: string | null;
  genres: string[];
  image: string | null;
  website: string | null;
  kind: "sight" | "meal" | "terminal";
  arrive_local: string;
  leave_local: string;
  ride_minutes: number | null;
  why: string[];
};

export type Watch = {
  entity_id: string;
  title: string;
  kind: "film" | "series";
  minutes: number | null;
  year: number | null;
  affinity: number | null;
  image: string | null;
  why: string[];
};

export type Plan = {
  wait: Wait;
  stops: Stop[];
  watch: Watch[];
  head_back_by_local: string | null;
  back_at_terminal_local: string | null;
  considered: number;
  rejected: Record<string, number>;
  dietary_needs_met: boolean;
  taste_shared?: boolean;
  unavailable?: string[];
  note?: string | null;
  source?: { provider: string; requests: number };
  dietary_needed?: string[];
};

export type MyGroundtime = Plan & { traveller: { name: string } };

export type Love = { id: string; name: string; type: string };

export type Taste = { loves: Love[]; dietary: string[]; wind_down: string | null; updated_utc: string | null };

export type Found = { id: string; name: string; type: string; year: number | null; image: string | null };

export type DelayedFlight = {
  flight_id: string;
  flight_no: string;
  from: string;
  to: string;
  scheduled_utc: string;
  delay_minutes: number;
  booked: number;
  with_app: number;
};

export type CareRow = Plan & { name: string; username: string };

export type FlightCare = {
  flight_id: string;
  flight_no: string;
  from: string;
  to: string;
  delay_minutes: number;
  booked: number;
  by_mode: { city: number; terminal: number };
  note?: string | null;
  travellers: CareRow[];
};

export type LayoverPick = {
  name: string;
  address: string | null;
  distance_m: number | null;
  affinity: number | null;
  rating: number | null;
  dietary: string[];
  noise: string | null;
  genres: string[];
  why: string[];
  open_until: string | null;
};

export type Layover =
  | { night_stop: null; note: string }
  | {
      night_stop: {
        pairing_id: string;
        date: string;
        station: string;
        release_utc: string;
        next_report_utc: string;
        crew_count: number;
        duty_hours: number;
        cause: string | null;
      };
      window: {
        station: string;
        city: string;
        hotel_area: string;
        rest_hours: number;
        legal_rest: boolean;
        free_from_local: string | null;
        sleep_by_local: string | null;
        free_minutes: number;
        meal_at_local: string | null;
        tiring: boolean;
        timezone?: string;
      };
      picks: LayoverPick[];
      considered: number;
      rejected: Record<string, number>;
      taste_shared_by: number;
      crew_count: number;
      dietary_needs_met: boolean;
      quiet: boolean;
      note: string | null;
      dietary_needed?: string[];
    };

export const POSITIONS: [Position, string][] = [
  ["away", "Not at the airport yet"],
  ["landside", "At the terminal, before security"],
  ["airside", "Past security"],
];

export const SEARCH_KINDS: [string, string][] = [
  ["urn:entity:artist", "Artist"],
  ["urn:entity:movie", "Film"],
  ["urn:entity:tv_show", "TV show"],
  ["urn:entity:book", "Book"],
  ["urn:entity:podcast", "Podcast"],
];

export const DIETARY: [string, string][] = [
  ["vegetarian", "Vegetarian"],
  ["vegan", "Vegan"],
  ["jain", "Jain"],
  ["halal", "Halal"],
  ["gluten_free", "Gluten free"],
];

export const MAX_LOVES = 5;

/** "2026-10-13 18:40" -> "18:40"; anything else (null, a bare time) as it is, or "—". */
export function hhmm(local: string | null | undefined): string {
  if (!local) return "—";
  const m = /^\d{4}-\d{2}-\d{2}[ T](\d{2}:\d{2})/.exec(local);
  return m ? m[1] : local;
}

/** 45 -> "45 min", 60 -> "1 h", 135 -> "2 h 15 min". */
export function duration(minutes: number | null | undefined): string {
  if (minutes == null || !Number.isFinite(minutes) || minutes < 0) return "—";
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  if (!h) return `${m} min`;
  return m ? `${h} h ${m} min` : `${h} h`;
}

/** 850 -> "850 m", 2400 -> "2.4 km". */
export function distance(metres: number | null | undefined): string {
  if (metres == null || !Number.isFinite(metres)) return "";
  return metres < 1000 ? `${Math.round(metres)} m` : `${(metres / 1000).toFixed(1)} km`;
}

/** Qloo's affinity (0 to 1) as a whole percentage, or null when there is none. */
export function match(affinity: number | null | undefined): number | null {
  if (affinity == null || !Number.isFinite(affinity) || affinity <= 0) return null;
  return Math.round(Math.min(1, affinity) * 100);
}

/** Rejection counts, largest first, without the empty ones. */
export function rejections(rejected: Record<string, number> | null | undefined): [string, number][] {
  return Object.entries(rejected ?? {})
    .filter(([, n]) => n > 0)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

/** At most five loves, each id once, in the order they were picked. */
export function addLove(loves: Love[], love: Love): Love[] {
  if (loves.length >= MAX_LOVES || loves.some((l) => l.id === love.id)) return loves;
  return [...loves, love];
}

/** One line for a care row: the stops and their times, or the films for the wait. */
export function planSummary(plan: Pick<Plan, "stops" | "watch">): string {
  if (plan.stops.length) {
    return plan.stops.map((s) => `${s.name} ${hhmm(s.arrive_local)}–${hhmm(s.leave_local)}`).join(" · ");
  }
  if (plan.watch.length) return plan.watch.map((w) => w.title).join(" · ");
  return "Nothing planned";
}
