"""A traveller's Groundtime plan, live against Qloo, from the command line.

    uv run python -m crewops.taste.plan TR-1001 --delay KS434=240
    uv run python -m crewops.taste.plan TR-1002 --delay KS434=240 --position airport

Reads the network and the demo bookings (``data/team/demo_travellers.json``) and uses the
seed's own moment, 13 October 13:00 IST, when ``--at`` is left out, so it needs the Qloo key
(``QLOO_API_KEY`` in ``.env``) and nothing from AWS.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

from crewops.config import Settings, load_env_file
from crewops.network import network
from crewops.taste.groundtime import ground_wait, plan_groundtime
from crewops.taste.qloo import MemoryCache, QlooError, client_from_settings
from crewops.taste.travellers import Position, load_travellers, trip

SEED_AT = datetime(2026, 10, 13, 7, 30, tzinfo=UTC)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A traveller's Groundtime plan")
    parser.add_argument("traveller", help="a demo traveller's id, e.g. TR-1001")
    parser.add_argument("--delay", action="append", default=[], help="FLIGHT_NO=minutes")
    parser.add_argument("--position", choices=[p.value for p in Position])
    parser.add_argument("--at", help="UTC time, e.g. 2026-10-13T07:30:00Z")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    load_env_file()

    travellers = load_travellers()
    traveller = travellers.get(args.traveller.upper())
    if traveller is None or not traveller.flight_nos:
        booked = ", ".join(t for t, v in travellers.items() if v.flight_nos)
        parser.error(f"no booked demo traveller {args.traveller}; one of {booked}")
    now = datetime.fromisoformat(args.at.replace("Z", "+00:00")) if args.at else SEED_AT
    legs = trip(network().flights, traveller.flight_nos, now)
    delays = {}
    for spec in args.delay:
        number, _, minutes = spec.partition("=")
        for leg in legs:
            if leg.flight_no == number.upper():
                delays[leg.flight_id] = int(minutes)
    wait = ground_wait(legs, Position(args.position or traveller.position), now, delays)
    if wait is None:
        print("Every flight on this booking has left.")
        return 1
    qloo = client_from_settings(Settings.from_env(), cache=MemoryCache())
    try:
        plan = plan_groundtime(wait, traveller.taste, qloo)
    except QlooError as exc:
        print(f"Qloo: {exc}")
        return 1
    out = plan.to_dict()
    if args.json:
        print(json.dumps(out, indent=2))
        return 0
    w = out["wait"]
    print(f"{traveller.name}: {w['headline']}")
    print(f"  {w['position']}, {w['mode']} plan; gate by {w['at_gate_by_local'][11:]}")
    if w["stay_reason"]:
        print(f"  {w['stay_reason']}")
    for s in out["stops"]:
        when = (
            f"{s['arrive_local'][11:]}-{s['leave_local'][11:]}"
            if s["kind"] != "terminal"
            else "now"
        )
        print(f"  {when:11} {s['name']}  ({'; '.join(s['why'])})")
    if out["back_at_terminal_local"]:
        print(
            f"  at the terminal {out['back_at_terminal_local'][11:]}, "
            f"needed by {w['at_terminal_by_local'][11:]}"
        )
    for x in out["watch"]:
        print(f"  watch: {x['title']} ({x['kind']}, {x['minutes']} min)")
    print(f"  rejected: {out['rejected']}")
    print(f"  Qloo calls: {qloo.calls}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
