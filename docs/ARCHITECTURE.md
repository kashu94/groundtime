# Architecture

## Principle

Qloo chooses, the engine checks, the model talks. The model never calculates.

A passenger told to see a fort that closed an hour ago, or to leave an airport they can't get
back into, misses a flight. So every recommendation comes from Qloo; every time, deadline,
ride, opening hour and dietary check from deterministic code; and the model is used only
where language earns its cost: choosing which tools to call for a traveller's question, and
putting the checked answer into words.

## System

```
 Browser ──► Next.js (Amplify Hosting) ──► MCP server (Bedrock AgentCore Runtime)
               server routes, cookies          │  token checked again, caller built
               the user's access token         │  from Cognito groups + profile
                                               │
       Cognito user pool ◄─────────────────────┤
                                               ├──► Qloo Taste AI API (Search, Insights)
                                               ├──► Amazon Nova 2 Lite (concierge only)
                                               ├──► SSM Parameter Store (the Qloo key)
                                               └──► DynamoDB (one table)
```

Three stacks: `Groundtime-<stage>-Data` (the table), `-Auth` (the user pool, one group per
role, the web client) and `-Mcp` (the AgentCore runtime and its role). The execution role may
read and write the table, invoke the one concierge model, read the one SSM parameter that
holds the Qloo key, and reset passwords in the pool. Nothing else.

## The network

The airline network is not in the table. `data/seed` holds one hand-built week (12 to 18
October 2026): three fictional Indian airlines, eight airports, 147 flights and the 39 crew
trips (pairings) that fly them, with 150 crew. `crewops.network` repeats it weekly to 31
December, the same flights at the same times with the same crew, and the MCP server holds it
in memory (about 1,700 flights). A plan reads it many times; a table round trip each time
would only add latency.

The deployed server runs on the real clock (`CREWOPS_REAL_TIME=1`); tests and local runs use
a fixed moment, 13 October 13:00 in India, so they repeat exactly.

## Data store

One on-demand DynamoDB table, `groundtime-<stage>-ops` (`crewops.store.schema`):

| Item | pk / sk |
|---|---|
| User profile (the crew or passenger record a login stands for) | `USER#username / PROFILE` |
| A traveller's booking | `BOOKING / TR-id` |
| Traveller taste profile | `TRAVELLER#TR-id / TASTE` |
| Crew taste profile | `CREW#C-id / TASTE` |
| Delay on a flight, with every change and how many times it was marked late | `DELAY / flight-id` |
| Qloo answer, cached a day | `QLOO / request-hash` (TTL) |

Bookings and delays each sit in one partition, so customer care reads all of either with one
query. A traveller has one booking at a time; a flight has one delay, the latest recorded.

## Booking

`find_flights` lists direct flights between two airports on a day, then one-stop trips with a
same-day connection of one to six hours, earliest arrival first, only flights leaving at least
an hour from now (`crewops.taste.travellers.find_trips`). `taste_options` gives the short list
for the booking screen: a fixed set of names per kind (artists, films, series, books), each
looked up once in Qloo's Search API so what is saved is Qloo's id for it, plus the dietary
needs Groundtime can check for.

`book_trip` takes the flight ids, the picks and the dietary needs together. It checks
everything first (the flights exist, connect and can still be booked; every pick is a Qloo id
of a known kind, at most five; every dietary need is one the engine checks), then saves the
booking and the taste profile. A booking that fails saves nothing; nothing a traveller browses
is kept.

A trip starts as "not at the airport yet"; where the traveller is is asked on the day, not at
booking. On My trip, with their permission, the browser compares the device's location with
the departure airport (within 3 km, allowing for the reading's accuracy) and sends only
`set_position` with `airport` or `away`; a reading too rough to tell changes nothing. The
location itself never leaves the device.

The demo passengers (`data/team/demo_travellers.json`) come already booked by flight number,
on the next day their flights operate. When one says where they are, their booking is saved
with the day it resolved to.

## The plan for a wait

`crewops.taste.groundtime` plans a passenger's wait; `crewops.taste.service` gives it the
booking, the taste and the delays.

- **The schedule gives the wait** (`ground_wait`). The expected departure is the schedule
  plus the delay customer care recorded. The gate deadline is departure less gate close
  (25 min) and 15 min; the terminal-door deadline is that less security (45 min) and 15 min.
  Every headline says the wait in plain words.
- **Where they are decides what is possible.** Someone not at the airport yet is free from
  when they would have had to be at the terminal without the delay; with at least 90 minutes
  before the terminal deadline, the plan is an outing near the airport on their way in
  (`city`). Someone already at the airport is free from now and stays in the terminal: Indian
  airports only let a passenger back out of the departure terminal with the airline's and
  security's clearance. A connecting passenger is airside from their arrival and stays in.
  The network is domestic, so no visa rule applies.
- **Qloo gives the candidates.** Up to five Insights requests, sent at once: sights (genre
  tags museum, park, beach, market, monument, gallery, attraction) and restaurants within the
  airport's radius, or restaurants and cafés within 900 m of the terminal; a list filtered to a
  dietary option they need; films and series. All carry the traveller's loves as signals.
  One that fails is listed as unavailable; the rest of the plan still stands.
- **The checks decide.** A sight must carry a sight's genre and none of a hotel's, an
  agency's or an office's (Qloo tags those as attractions too). A meal must be an eatery
  offering every dietary option needed. Every outing is walked on the clock: the ride (road
  distance 1.4 times the straight line, 25 km/h, 10 minutes to find a cab), the visit (the
  place open throughout), the next ride, the ride to the terminal; one that reaches the
  terminal late is dropped. Two stops beat one; then listed hours, Qloo affinity and the
  earlier arrival. A film is kept only if it ends 20 minutes before the gate, or within the
  flight when the wait is spent outside; a series if an episode does. Every stop says why it
  was chosen, and every rejection is counted.

## The concierge

A Converse tool loop on Amazon Nova 2 Lite with five tools (`my_wait`, `plan_groundtime`,
`set_position`, `find_to_watch`, `search_catalogue`), at most five rounds and 25 seconds.
Before its answer is shown, every run of capitalised words in it must appear in a tool result
or the question; otherwise, or with no model, or when Bedrock is down (a circuit breaker stops
waiting on it after three failures in a row), the traveller gets the plan written out from
the checked facts.

## Delays and customer care

Customer care finds a flight on the board by number, airport or city, and records a delay
(`record_delay`): minutes (up to 12 hours), a reason, who recorded it. Zero clears it, and a
flight that has left can't be changed. A flight can be marked late at most three times; the
count and the check are one conditional DynamoDB update, so two people saving at once can't
pass it. Clearing is always allowed. Every change is kept in the delay's history, and the
board shows how many times a flight has been marked late, when first and last, and by whom.

Every plan reads delays from the table (cached five seconds per server), so a recorded delay
moves every affected passenger's deadlines and plan, and a delay on the last leg of a crew
member's day moves their release and so their layover evening.

`flight_care` lists every Groundtime traveller on a delayed flight with their plan (planned in
parallel), and shows a dietary need only as met, never what it is: the staff view drops the
dietary request and every reason that names a diet, and words the reasons about the traveller
rather than to them.

## Layover care

`crewops.taste.layover` gives a crew member's next night stop a meal plan:

- **The crew trip gives the window** (`window.py`). Release, plus the ride to the crew hotel
  and check-in, is when they are free. The next report, less the ride back, an hour to get
  ready and eight hours of sleep, is when they must be asleep. A meal needs 75 minutes inside
  that. A duty of ten hours or more, or a short window, counts as tiring. A rest under 12 hours
  is flagged.
- **Qloo gives the places**: restaurants within the crew hotel's radius (1.5 km after a
  tiring day), ranked by affinity to the crew member's picks, and a second list filtered by a
  dietary need.
- **The checks decide**: open for the whole meal, every dietary option needed, not loud when
  tired or when they prefer quiet, not airside or a food court, within the radius.

## MCP server

Everything goes through one MCP server on AgentCore Runtime (stateless streamable HTTP, a
code package on Linux ARM64, billed per second while a session runs).

- **Front door.** AgentCore's JWT authorizer admits only access tokens from the Cognito pool
  and web client, and passes the `Authorization` header through.
- **Second check.** The server verifies the token's signature and claims again, then builds
  the caller from the token's groups and the user's profile (the crew or passenger record
  they stand for, written only by the team command). A call without a valid token does
  nothing.
- **Tools, by role.** Traveller: `stations`, `find_flights`, `taste_options`, `book_trip`,
  `my_trip`, `set_position`, `my_groundtime`, `ask`. Traveller and crew: `my_taste`,
  `save_my_taste`, `taste_search`. Crew: `my_flights`, `my_layover`. Customer care:
  `flight_board`, `record_delay`, `delayed_flights`, `flight_care`. Admin: `team_accounts`,
  `reset_password`. Everyone: `whoami`.
- **Errors.** A failure the server did not expect is logged and reaches the caller as
  `INTERNAL`, with no detail.

## Qloo, safely

Privacy is enforced, not promised. Qloo receives ids, tags, a map point and a radius; the
client's guard refuses any parameter outside an allow-list and any value that looks like a
traveller id, crew id, user id or email. The key is a SecureString read at run time by the
MCP server alone, sent only as the `X-Api-Key` header, never logged.

Failures are bounded: a 12 s timeout, one retry for a rate limit or a 5xx, and a one-minute
pause after three failures in a row. Errors keep Qloo's own categories (`QLOO_AUTH`,
`QLOO_RATE_LIMIT`, `QLOO_UNAVAILABLE`, `QLOO_BAD_RESPONSE`) and `QLOO_REFUSED` for a request
the guard stopped. Answers are cached in the table for a day, so a flight full of passengers
waiting at one airport costs one set of calls.

## Web app

The web app (`web/`, Next.js on Amplify Hosting) is a backend for frontend: the browser talks
only to the app's own server routes, which call the MCP server as the signed-in user, so
every role rule stays in one place and the app holds no key.

- **Sign-in.** The server signs in to Cognito with the username and password (no client
  secret; Cognito's public API, so no AWS credentials) and keeps the tokens in httpOnly,
  same-site cookies, refreshing them before they expire.
- **Actions.** `/api/tools/<name>` forwards one of a fixed list of MCP tools with the user's
  access token, and only for requests whose Origin is this site.
- **Pages.** My trip (travellers: booking, the plan, the concierge), Crew, Customer care and
  Admin, each shown only to its role.
