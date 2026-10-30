# Seed week

A synthetic airline network used for development, tests and the demo. All times are UTC.
`crewops.network` repeats this week every week to 31 December 2026.

| | |
|---|---|
| Week | 2026-10-12 to 2026-10-18 |
| Stations | BLR, BOM, CCU, COK, DEL, GOI, HYD, MAA (all domestic, India) |
| Airlines | Deccan Express (DX), Konkan Skyways (KS), Nilgiri Connect (NG) |
| Fleet | 6 aircraft: 4 A320, 2 ATR72 |
| Crew | 150: captains, first officers and cabin crew of the three airlines |
| Flights | 147, flown by 39 crew trips (pairings) |
| Passengers | Seats and the number booked on every flight |

| File | Contents |
|---|---|
| `airlines.json` | The three airlines, their codes, colours and aircraft |
| `crew.json` | Every crew member: airline, rank, base, aircraft ratings |
| `flights.json` | Every leg with times, aircraft, seats and passengers booked |
| `rosters.json` | Crew trips: each duty day, its legs, report and release times, and who flies it |

Check it loads and hangs together:

```bash
uv run python -c "from crewops.ingestion.seed import load_seed, validate; print(validate(load_seed()))"
```
