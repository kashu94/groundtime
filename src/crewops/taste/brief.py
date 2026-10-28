"""Print layover briefs for a pairing's night stops, live against Qloo.

    uv run python -m crewops.taste.brief P-2291
    uv run python -m crewops.taste.brief P-2291 --crew C-1042      # one crew member's own view
    uv run python -m crewops.taste.brief P-2291 --json

Reads the seed week and the demo taste profiles (``data/team/demo_tastes.json``), so it needs
only ``QLOO_API_KEY`` in ``.env``: no AWS account.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from crewops.config import Settings, load_env_file
from crewops.engine.world import build_world
from crewops.ingestion.seed import load_seed
from crewops.taste.layover import layover_brief, night_stops
from crewops.taste.profile import TasteProfile
from crewops.taste.qloo import QlooError, client_from_settings

DEMO_TASTES = Path(__file__).resolve().parents[3] / "data" / "team" / "demo_tastes.json"


def demo_profiles(path: Path = DEMO_TASTES) -> dict[str, TasteProfile]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {p["crew_id"]: TasteProfile.from_dict(p["crew_id"], p) for p in raw["profiles"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pairing_id")
    parser.add_argument("--crew", help="a crew member's own brief, with only their profile")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    load_env_file()
    settings = Settings.from_env()
    seed = load_seed()
    world = build_world(seed)
    stops = night_stops(world, pairing_id=args.pairing_id, crew_id=args.crew)
    if not stops:
        print(f"{args.pairing_id} has no night stop" + (f" for {args.crew}" if args.crew else ""))
        return 1
    profiles = demo_profiles()
    if args.crew:
        profiles = {k: v for k, v in profiles.items() if k == args.crew}
    qloo = client_from_settings(settings)
    min_rest = world.book.min_rest_hours
    for stop in stops:
        try:
            brief = layover_brief(stop, profiles, qloo, min_rest_hours=min_rest)
        except QlooError as err:
            print(f"{err.code}: {err}", file=sys.stderr)
            return 2
        view = brief.to_dict(for_crew=bool(args.crew))
        if args.json:
            print(json.dumps(view, indent=2))
            continue
        w = view["window"]
        print(
            f"{stop.pairing_id} night stop at {w['city']} ({w['hotel_area']}) on {stop.date}: "
            f"free {w['free_from_local'][-5:]} to {w['sleep_by_local'][-5:]} {w['timezone']}, "
            f"rest {w['rest_hours']} h"
        )
        print(
            f"  {view['taste_shared_by']} of {view['crew_count']} crew shared their taste; "
            f"Qloo offered {view['considered']} places, "
            f"left out: {view['rejected'] or 'none'}"
        )
        for n, pick in enumerate(view["picks"], 1):
            print(f"  {n}. {pick['name']}: " + " · ".join(pick["why"]))
        if view["note"]:
            print(f"  {view['note']}")
    print(f"Qloo requests sent: {qloo.calls}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
