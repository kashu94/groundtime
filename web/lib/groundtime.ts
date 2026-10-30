// What the Groundtime tools return, and the small helpers the trip, care and crew pages
// share. Every time here is local time in India, as the server writes it.

/** `away`: not at the airport yet; `airport`: already there, so the plan stays inside. */
export type Position = "away" | "airport";

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
  /** The wait in plain words: where they are, what changed, and by when. */
  headline: string;
  /** The same wait in the third person, for customer care. */
  staff_summary: string;
  free_from_local: string;
  usual_terminal_by_local: string;
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
  /** null when there is nothing to check: no dietary needs, or no food stop. */
  dietary_needs_met: boolean | null;
  taste_shared?: boolean;
  unavailable?: string[];
  note?: string | null;
  /** The Qloo requests made, by name, with what was asked (never who for). */
  source?: { provider?: string; requests?: Record<string, unknown> };
  dietary_needed?: string[];
};

export type MyGroundtime = Plan & { traveller: { name: string } };

export type Love = { id: string; name: string; type: string };

export type Taste = { loves: Love[]; dietary: string[]; wind_down: string | null; updated_utc: string | null };

export type Found = { id: string; name: string; type: string; year: number | null; image: string | null };

export type TasteOptions = {
  picks: Found[];
  dietary: { id: string; name: string }[];
  /** Qloo type -> what it's called on screen. */
  kinds: Record<string, string>;
};

export type Station = { code: string; city: string; airport: string };

export type TripLeg = {
  flight_id: string;
  flight_no: string;
  airline: string | null;
  from: string;
  to: string;
  departs_local: string;
  arrives_local: string;
};

export type TripOption = {
  flight_ids: string[];
  from: string;
  to: string;
  departs_local: string;
  arrives_local: string;
  via: string | null;
  connection_minutes: number | null;
  legs: TripLeg[];
};

export type BookedLeg = {
  flight_id: string;
  flight_no: string;
  from: string;
  to: string;
  departs_local: string;
  arrives_local: string;
  delay_minutes: number;
  expected_departure_local: string;
};

export type CareDesk = { name: string; phone: string; hours: string };

export type MyTrip =
  | { booked: false; care: CareDesk }
  | {
      booked: true;
      name: string;
      position: Position;
      legs: BookedLeg[];
      wait: Wait | null;
      /** The airport they wait at, so this device can tell whether they are there yet. */
      airport_point: { lat: number; lon: number } | null;
      taste: Taste;
      care: CareDesk;
    };

export type AssistantRole = "traveller" | "crew" | "customer_care" | "admin";

export type AssistantAnswer = {
  answer: string;
  /** `model`: the assistant's own words, checked against what its tools returned; `summary`:
   * the checked facts written out, when the model couldn't answer; `off_topic`: not about
   * Groundtime or air travel. */
  source: "model" | "summary" | "off_topic";
  role: AssistantRole;
  tools: string[];
  notes: string[];
  /** The answer read aloud by Amazon Polly, base64 MP3, when asked for. */
  audio_mp3?: string;
};

/** The assistant serves the role of the page it's opened on. */
export function assistantRoleFor(path: string): AssistantRole | null {
  if (path.startsWith("/trip")) return "traveller";
  if (path.startsWith("/crew")) return "crew";
  if (path.startsWith("/care")) return "customer_care";
  if (path.startsWith("/admin")) return "admin";
  return null;
}

export type DelayChange = { delay_minutes: number; reason: string | null; by: string | null; at_local: string | null };

/** What customer care recorded on a flight: the latest change and every one before it. */
export type DelayRecord = {
  reason: string | null;
  recorded_by: string | null;
  recorded_local: string | null;
  first_delayed_local: string | null;
  /** Times the flight has been marked late; at most MAX_DELAY_TIMES. */
  times_delayed: number;
  delays_left: number;
  history: DelayChange[];
};

export type BoardRow = DelayRecord & {
  flight_id: string;
  flight_no: string;
  from: string;
  to: string;
  departs_local: string;
  expected_departure_local: string;
  delay_minutes: number;
  left: boolean;
  booked: number;
  with_app: number;
};

export type DelayedFlight = DelayRecord & {
  flight_id: string;
  flight_no: string;
  from: string;
  to: string;
  departs_local: string;
  expected_departure_local: string;
  delay_minutes: number;
  booked: number;
  with_app: number;
};

export type CareRow = Plan & { name: string };

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

export type CrewLeg = {
  flight_id: string;
  flight_no: string;
  from: string;
  to: string;
  departs_local: string;
  arrives_local: string;
  delay_minutes: number;
};

export type DutyDay = {
  pairing_id: string;
  date: string;
  role: string;
  report_local: string;
  release_local: string;
  legs: CrewLeg[];
};

export type MyFlights = {
  crew_id: string;
  name: string | null;
  rank: string | null;
  base: string | null;
  days: DutyDay[];
};

export type Account = {
  username: string;
  name: string | null;
  roles: string[];
  crew_id: string | null;
  traveller_id: string | null;
  may_reset: boolean;
};

export const POSITIONS: [Position, string][] = [
  ["away", "Not at the airport yet"],
  ["airport", "I'm at the airport"],
];

/** Until the server's own list arrives (taste_options), or if Qloo is slow to give it. */
export const KINDS: Record<string, string> = {
  "urn:entity:artist": "artist",
  "urn:entity:movie": "film",
  "urn:entity:tv_show": "TV show",
  "urn:entity:book": "book",
  "urn:entity:podcast": "podcast",
  "urn:entity:place": "place",
};

export const DIETARY: { id: string; name: string }[] = [
  { id: "vegetarian", name: "Vegetarian" },
  { id: "vegan", name: "Vegan" },
  { id: "jain", name: "Jain" },
  { id: "halal", name: "Halal" },
  { id: "gluten_free", name: "Gluten-free" },
];

export const MAX_LOVES = 5;

/** Flights are on sale up to the end of 2026. */
export const LAST_BOOKABLE = "2026-12-31";

/** One-tap delays for customer care, in minutes. */
export const QUICK_DELAYS = [30, 60, 120, 240];

/** The server's limit on a recorded delay: twelve hours. */
export const MAX_DELAY_MINUTES = 12 * 60;

/** How many times one flight may be marked late. Clearing a delay doesn't count. */
export const MAX_DELAY_TIMES = 3;

/** Within this distance of the airport counts as being there. */
export const AT_AIRPORT_M = 3000;

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

/** A tap on a pick: out if it was in, in if there is room. */
export function toggleLove(loves: Love[], love: Love): Love[] {
  return loves.some((l) => l.id === love.id) ? loves.filter((l) => l.id !== love.id) : addLove(loves, love);
}

/** The short list by kind, in the order the server lists the kinds, without empty ones. */
export function groupPicks(picks: Found[], kinds: Record<string, string>): [string, string, Found[]][] {
  return Object.entries(kinds)
    .map(([kind, label]): [string, string, Found[]] => [kind, label, picks.filter((p) => p.type === kind)])
    .filter(([, , found]) => found.length > 0);
}

/** "film" -> "Film": a kind's label at the start of a line. */
export function kindLabel(kind: string, kinds: Record<string, string> = KINDS): string {
  const label = kinds[kind] ?? kind.replace(/^urn:(entity:)?/, "").replace(/_/g, " ");
  return label.charAt(0).toUpperCase() + label.slice(1);
}

/** Today's date in India (YYYY-MM-DD), whatever the browser's own time zone. */
export function todayInIndia(now: Date = new Date()): string {
  return new Date(now.getTime() + 330 * 60_000).toISOString().slice(0, 10);
}

/** A local time some minutes later, written the same way: ("2026-10-13 23:40", 45) ->
 * "2026-10-14 00:25". */
export function later(local: string, minutes: number): string {
  const m = /^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})/.exec(local);
  if (!m) return local;
  const at = new Date(`${m[1]}T${m[2]}:00Z`);
  at.setUTCMinutes(at.getUTCMinutes() + minutes);
  return at.toISOString().slice(0, 16).replace("T", " ");
}

/** How a trip goes: "Direct", or "via BLR, 1 h 15 min connection". */
export function route(option: Pick<TripOption, "via" | "connection_minutes">): string {
  if (!option.via) return "Direct";
  return option.connection_minutes == null
    ? `via ${option.via}`
    : `via ${option.via}, ${duration(option.connection_minutes)} connection`;
}

/** "45 min late, now 19:10", or "" for a flight on time. */
export function lateBy(minutes: number | null | undefined, expectedLocal: string | null | undefined): string {
  if (!minutes || minutes <= 0) return "";
  return `${duration(minutes)} late, now ${hhmm(expectedLocal)}`;
}

/** What customer care typed as a delay: whole minutes from 0 to twelve hours, else null. */
export function delayMinutes(text: string): number | null {
  const t = text.trim();
  if (!/^\d{1,3}$/.test(t)) return null;
  const n = Number(t);
  return n <= MAX_DELAY_MINUTES ? n : null;
}

/** One line for a care row: the stops and their times, or the films for the wait. */
export function planSummary(plan: Pick<Plan, "stops" | "watch">): string {
  if (plan.stops.length) {
    return plan.stops.map((s) => `${s.name} ${hhmm(s.arrive_local)}–${hhmm(s.leave_local)}`).join(" · ");
  }
  if (plan.watch.length) return plan.watch.map((w) => w.title).join(" · ");
  return "Nothing planned";
}

/** A flight board row matches a search when the flight number, either airport or a city
 * typed matches: "ks434", "KS 434", "goi", "goa blr". Every word has to match something. */
export function matchesFlight(
  row: Pick<BoardRow, "flight_no" | "from" | "to">,
  query: string,
  cityOf: (code: string) => string = (c) => c,
): boolean {
  const words = query.toLowerCase().replace(/([a-z]{2})\s+(\d)/g, "$1$2").split(/[\s,→>-]+/).filter(Boolean);
  const fields = [row.flight_no, row.from, row.to, cityOf(row.from), cityOf(row.to)].map((f) => f.toLowerCase());
  return words.every((w) => fields.some((f) => f.includes(w)));
}

/** Straight-line distance in metres between two points on the Earth. */
export function metresBetween(a: { lat: number; lon: number }, b: { lat: number; lon: number }): number {
  const rad = Math.PI / 180;
  const dLat = (b.lat - a.lat) * rad;
  const dLon = (b.lon - a.lon) * rad;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * 6_371_000 * Math.asin(Math.sqrt(h));
}

/** Where a device reading puts the traveller, or null when it is too rough to tell. */
export function positionFromFix(
  airport: { lat: number; lon: number },
  fix: { lat: number; lon: number; accuracy: number },
): Position | null {
  const metres = metresBetween(airport, fix);
  if (metres + fix.accuracy <= AT_AIRPORT_M) return "airport";
  if (metres - fix.accuracy > AT_AIRPORT_M) return "away";
  return null;
}
