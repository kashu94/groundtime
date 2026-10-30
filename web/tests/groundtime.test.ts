import { describe, expect, it } from "vitest";

import {
  addLove,
  delayMinutes,
  distance,
  duration,
  groupPicks,
  hhmm,
  kindLabel,
  later,
  lateBy,
  match,
  MAX_LOVES,
  planSummary,
  rejections,
  route,
  todayInIndia,
  toggleLove,
  type Found,
  type Stop,
  type Watch,
} from "@/lib/groundtime";
import { TOOLS } from "@/lib/tools";

describe("groundtime times", () => {
  it("shows a local time as HH:MM", () => {
    expect(hhmm("2026-10-13 18:40")).toBe("18:40");
    expect(hhmm("2026-10-13T07:05")).toBe("07:05");
    expect(hhmm(null)).toBe("—");
    expect(hhmm("")).toBe("—");
    expect(hhmm("soon")).toBe("soon");
  });

  it("reads minutes as hours and minutes", () => {
    expect(duration(45)).toBe("45 min");
    expect(duration(60)).toBe("1 h");
    expect(duration(135)).toBe("2 h 15 min");
    expect(duration(0)).toBe("0 min");
    expect(duration(null)).toBe("—");
    expect(duration(-5)).toBe("—");
  });

  it("tells today's date in India, whatever the browser's zone", () => {
    expect(todayInIndia(new Date("2026-10-29T18:29:00Z"))).toBe("2026-10-29");
    expect(todayInIndia(new Date("2026-10-29T18:30:00Z"))).toBe("2026-10-30"); // midnight in India
  });

  it("adds minutes to a local time, past midnight too", () => {
    expect(later("2026-10-13 18:40", 90)).toBe("2026-10-13 20:10");
    expect(later("2026-10-13 23:40", 45)).toBe("2026-10-14 00:25");
    expect(later("soon", 45)).toBe("soon");
  });

  it("reads distances in metres or kilometres", () => {
    expect(distance(850)).toBe("850 m");
    expect(distance(2400)).toBe("2.4 km");
    expect(distance(null)).toBe("");
  });
});

describe("groundtime plans", () => {
  it("shows a taste match only for a real affinity", () => {
    expect(match(0.874)).toBe(87);
    expect(match(1.4)).toBe(100);
    expect(match(0)).toBeNull();
    expect(match(null)).toBeNull();
  });

  it("lists rejections largest first, without empty ones", () => {
    expect(rejections({ "too far": 2, "closed now": 5, loud: 0 })).toEqual([
      ["closed now", 5],
      ["too far", 2],
    ]);
    expect(rejections(undefined)).toEqual([]);
  });

  it("adds at most five loves, each once", () => {
    const love = (id: string) => ({ id, name: id, type: "urn:entity:artist" });
    let loves = [love("a")];
    expect(addLove(loves, love("a"))).toBe(loves);
    for (const id of ["b", "c", "d", "e", "f"]) loves = addLove(loves, love(id));
    expect(loves.map((l) => l.id)).toEqual(["a", "b", "c", "d", "e"]);
    expect(loves).toHaveLength(MAX_LOVES);
  });

  it("sums up a plan: the stops and their times, else the films", () => {
    const stop = { name: "Lalbagh", arrive_local: "2026-10-13 15:10", leave_local: "2026-10-13 16:20" } as Stop;
    const film = { title: "Swades" } as Watch;
    expect(planSummary({ stops: [stop], watch: [film] })).toBe("Lalbagh 15:10–16:20");
    expect(planSummary({ stops: [], watch: [film] })).toBe("Swades");
    expect(planSummary({ stops: [], watch: [] })).toBe("Nothing planned");
  });

  it("toggles a pick in and out, never past five", () => {
    const love = (id: string) => ({ id, name: id, type: "urn:entity:movie" });
    let loves = toggleLove([], love("a"));
    expect(loves.map((l) => l.id)).toEqual(["a"]);
    expect(toggleLove(loves, love("a"))).toEqual([]);
    for (const id of ["b", "c", "d", "e"]) loves = toggleLove(loves, love(id));
    expect(toggleLove(loves, love("f"))).toBe(loves);
  });

  it("groups the short list by kind, in the server's order, without empty kinds", () => {
    const pick = (id: string, type: string) => ({ id, name: id, type, year: null, image: null }) as Found;
    const kinds = { "urn:entity:artist": "artist", "urn:entity:movie": "film", "urn:entity:book": "book" };
    const groups = groupPicks([pick("lagaan", "urn:entity:movie"), pick("rahman", "urn:entity:artist")], kinds);
    expect(groups.map(([kind, label, found]) => [kind, label, found.map((f) => f.id)])).toEqual([
      ["urn:entity:artist", "artist", ["rahman"]],
      ["urn:entity:movie", "film", ["lagaan"]],
    ]);
  });

  it("names a kind at the start of a line", () => {
    expect(kindLabel("urn:entity:tv_show")).toBe("TV show");
    expect(kindLabel("urn:entity:movie", { "urn:entity:movie": "film" })).toBe("Film");
    expect(kindLabel("urn:entity:video_game", {})).toBe("Video game");
  });
});

describe("groundtime trips and delays", () => {
  it("says how a trip goes", () => {
    expect(route({ via: null, connection_minutes: null })).toBe("Direct");
    expect(route({ via: "BLR", connection_minutes: 75 })).toBe("via BLR, 1 h 15 min connection");
    expect(route({ via: "HYD", connection_minutes: 50 })).toBe("via HYD, 50 min connection");
  });

  it("says how late a flight is, and when it now leaves", () => {
    expect(lateBy(45, "2026-10-13 19:10")).toBe("45 min late, now 19:10");
    expect(lateBy(240, "2026-10-13 22:25")).toBe("4 h late, now 22:25");
    expect(lateBy(0, "2026-10-13 18:25")).toBe("");
    expect(lateBy(null, null)).toBe("");
  });

  it("reads a typed delay as whole minutes up to twelve hours", () => {
    expect(delayMinutes("90")).toBe(90);
    expect(delayMinutes(" 0 ")).toBe(0);
    expect(delayMinutes("720")).toBe(720);
    expect(delayMinutes("721")).toBeNull();
    expect(delayMinutes("1.5")).toBeNull();
    expect(delayMinutes("-30")).toBeNull();
    expect(delayMinutes("")).toBeNull();
  });
});

describe("the tools the web app may call", () => {
  it("are exactly the server's, with its list tools marked", () => {
    expect(Object.keys(TOOLS).sort()).toEqual(
      [
        "ask",
        "book_trip",
        "delayed_flights",
        "find_flights",
        "flight_board",
        "flight_care",
        "my_flights",
        "my_groundtime",
        "my_layover",
        "my_taste",
        "my_trip",
        "record_delay",
        "reset_password",
        "save_my_taste",
        "set_position",
        "stations",
        "taste_options",
        "taste_search",
        "team_accounts",
        "whoami",
      ].sort(),
    );
    // crewops.mcp.client.LIST_TOOLS
    const lists = Object.entries(TOOLS)
      .filter(([, t]) => t.list)
      .map(([name]) => name)
      .sort();
    expect(lists).toEqual([
      "delayed_flights",
      "find_flights",
      "flight_board",
      "stations",
      "taste_search",
      "team_accounts",
    ]);
  });

  it("marks every write, so a failed one is never retried", () => {
    const writes = Object.entries(TOOLS)
      .filter(([, t]) => t.write)
      .map(([name]) => name)
      .sort();
    expect(writes).toEqual(["book_trip", "record_delay", "reset_password", "save_my_taste", "set_position"]);
  });
});
