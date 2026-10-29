import { describe, expect, it } from "vitest";

import {
  addLove,
  distance,
  duration,
  hhmm,
  match,
  MAX_LOVES,
  planSummary,
  rejections,
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

  it("lets only saving a taste profile write", () => {
    expect(TOOLS.save_my_taste.write).toBe(true);
    for (const name of ["my_groundtime", "my_taste", "taste_search", "my_layover", "delayed_flights", "flight_care"]) {
      expect(TOOLS[name as keyof typeof TOOLS].write).toBe(false);
    }
    expect(TOOLS.taste_search.list).toBe(true);
    expect(TOOLS.delayed_flights.list).toBe(true);
  });
});
