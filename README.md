# Groundtime

**Every hour on the ground, worth having.** When a flight is delayed, Groundtime gives every
passenger and crew member on it a plan for the wait, made for their taste by the Qloo Taste AI
API and checked, stop by stop, so it is true: open, within reach, right for what they can eat,
and over in time for the gate.

KS434 from Goa to Bengaluru is four hours late. Today, everyone on it gets the same SMS and, at
best, the same meal voucher. With Groundtime:

* **Aarav hasn't left his hotel yet.** "You haven't left for the airport yet. KS434 is 4 h
  late, so instead of being at the airport at 14:20, here's what to do near it on your way in,
  before you need to be at the terminal by 18:20." Cansaulim Beach at 14:55, a vegetarian
  lunch at 16:25, leave for the airport at 17:25, at the terminal by 18:16. Every stop is real,
  open for the whole visit, picked by Qloo for what he loves, and the rides are counted.
* **Sara is already at the airport.** She is never told to leave it: once inside the departure
  terminal, Indian airports only let a passenger back out with the airline's and security's
  clearance. Food in the terminal, and a film matched to her taste that ends before her gate
  closes.
* **Meher is connecting in Bengaluru, and eats Jain.** She stays airside: a Jain-friendly
  restaurant in the terminal and something to watch that fits the connection.
* **The crew** get a meal near the crew hotel inside their rest, with the delay moving their
  evening and eight hours of sleep protected before the next report.

> Qloo chooses, the engine checks, the model talks. The model never calculates a time and never
> names a place a tool didn't return.

## How it works

1. **Book, and say what you love.** A traveller finds a flight (direct, or two with a same-day
   connection) and, on the same screen, taps a few things they love from a short list (artists,
   films, series, books, each looked up in Qloo's catalogue) or searches Qloo for anything
   else, and says what they can eat. Nothing is saved until they confirm the booking; then the
   trip and the taste are saved together.
2. **A delay is recorded once.** Customer care records it on the flight board as operations
   confirm it: "KS434, 240 minutes, late inbound aircraft". Every plan on that flight changes at
   once: passengers', and the crew's evening.
3. **Each traveller opens their plan,** or asks the concierge: "my flight's late, what can I
   do?" They say where they are, because that decides what is possible.
4. **Customer care sees every waiting passenger's plan,** and that each one meets their dietary
   needs, without ever seeing what the needs are.

## How Qloo is used

Qloo is the taste in every plan. Nothing in Groundtime recommends anything without it.

| Groundtime asks Qloo | Qloo API | Then the engine checks |
|---|---|---|
| The short list to pick from at booking, and anything else they love | Search, over Qloo's catalogue | Each pick is a Qloo id, never free text |
| Places to see near the airport, for this traveller's taste | Insights, `urn:entity:place` with `filter.location`, genre tags, their loves as `signal.interests` | A real sight (Qloo also tags hotels and travel agents as attractions); open for the whole visit; the rides there, on and to the terminal fit before the terminal deadline |
| Somewhere to eat | Insights, restaurant genre, plus a second list filtered to a dietary option they need | Offers every dietary option they need; open; within reach |
| Food without leaving the terminal | Insights within 900 m of the terminal | A place to eat, not a lounge or a duty-free shop; open now |
| Something to watch while waiting, or on the flight | Insights, `urn:entity:movie` and `urn:entity:tv_show`, cross-domain from the music, books and films they love | Ends before the gate closes; episodes fit the wait |
| Where a crew can eat tonight | Insights near the crew hotel, with the crew member's loves | Open for a whole meal inside the free time their rest leaves; every dietary need; quiet after a tiring day |

### Where you are decides what is possible

For each traveller the engine works out when their time is their own and the two deadlines
that matter: the terminal door (bag drop and security still ahead) and the gate
(`crewops.taste.groundtime`).

| Where the traveller is | Groundtime plans |
|---|---|
| Not at the airport yet (the delay is known before they set off) | The delay is time handed back: from when they would have had to be at the airport, an outing near it, on their way in, that gets them to the terminal in time. If there isn't time for one, the plan is at the airport. |
| At the airport | The terminal only, however long the delay: Indian airports only let a passenger back out of the departure terminal with the airline's and security's clearance. Food there, and films and series that fit. |
| Connecting | The terminal only, airside, from their arrival. |

Every flight in the network is domestic, so no visa applies.

### The concierge: an agent with Qloo tools

A traveller can simply ask. Amazon Nova decides which tools to call (`my_wait`,
`plan_groundtime`, `set_position` when they say "I'm already at the airport",
`find_to_watch`, `search_catalogue`) and words the answer. Before it is shown, every
capitalised name in it is matched against what the tools returned; one that isn't there means
the model made it up, and the traveller gets the checked plan written out instead
(`crewops.taste.concierge`). With no model, or Bedrock unavailable, they get that written-out
plan straight away.

### Privacy

Qloo is called only from the server, with ids, a map point and a radius. No name, username,
traveller id, crew id or email is ever sent; a guard refuses any request that could carry one
(`crewops.taste.qloo.guard`). Customer care sees that a plan meets someone's dietary needs,
never what the needs are. Taste is opt-in and saved only when a booking is confirmed.

## Roles

| Role | Sees and does |
|---|---|
| Traveller | Books a trip and shares what they love; their wait, their plan, the concierge |
| Crew | Their flights for the week with any delay; a plan for their next layover; their own taste |
| Customer care | The flight board: records and clears delays; every waiting passenger's plan |
| Admin | The accounts, and password resets |

Who may do what is decided in the MCP server from the caller's verified Cognito groups and
profile, never from what they type.

## Architecture

```
 Browser ──► Next.js on Amplify Hosting ──(the user's access token)──► MCP server on
 (sign in)   server routes only; holds no key                          Bedrock AgentCore Runtime
                                                                           │
             Cognito user pool ◄── token checked again ────────────────────┤
                                                                           ├──► Qloo Taste AI API
                                                                           │    (key from SSM SecureString)
                                                                           ├──► Amazon Nova 2 Lite on Bedrock
                                                                           │    (the concierge only)
                                                                           └──► DynamoDB: accounts, bookings,
                                                                                taste, delays, Qloo cache
```

* **One MCP server** holds every capability as a tool, and any MCP host can use it. The web
  app is one such host: its server routes call the tools as the signed-in user.
* **The network in memory.** The airline network (three fictional Indian airlines, eight
  airports, 147 flights a week and the crew trips that fly them) ships with the server and is
  repeated weekly to the end of 2026 (`crewops.network`), so the demo works on any day.
* **The engine is plain Python**: waits, deadlines, rides, opening hours, dietary checks. The
  same schedule and the same Qloo answers always give the same plan.

### AWS services

| Service | Used for |
|---|---|
| Amplify Hosting | The Next.js web app (server-side rendering) |
| Cognito | Sign-in; roles are groups. No self sign-up, no email or phone stored |
| Bedrock AgentCore Runtime | Hosts the MCP server (stateless streamable HTTP, Cognito JWT authorizer) |
| Bedrock (Amazon Nova 2 Lite) | The concierge's tool loop |
| DynamoDB | One on-demand table: profiles, bookings, taste, delays, a day's cache of Qloo answers |
| Systems Manager Parameter Store | The Qloo API key, as a SecureString read at run time |

Three CloudFormation stacks: `Groundtime-<stage>-Data`, `-Auth` and `-Mcp`.

## Repository layout

```
src/crewops/
  taste/        Groundtime: Qloo client, the wait and the plan, bookings, layovers, concierge
  mcp/          the MCP server, its API (role checks), the package builder and a test client
  auth/         token checks, the team file and account provisioning
  store/        the DynamoDB table: profiles, bookings, delays, taste, Qloo cache
  domain/       typed records: flights, crew trips, crew, airlines, roles
  network.py    the network in memory, from the seed week to the end of the year
  bedrock.py    the concierge's Bedrock client and circuit breaker
infra/          AWS CDK app (Python): Data, Auth and Mcp stacks
web/            Next.js app: My trip, Crew, Customer care, Admin
data/seed/      the network's seed week (airlines, crew, flights, crew trips)
data/team/      demo accounts, demo passengers and crew taste profiles
tests/          pytest, with moto for AWS
```

## Getting started

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/); Node.js 20+ for the web app.

```bash
uv sync
uv run pytest
uv run ruff check .
cd web && npm ci && npm test
```

Try a passenger's plan live against Qloo with nothing from AWS (put `QLOO_API_KEY=...` in
`.env`, which is git-ignored). KS434 from Goa four hours late, with the traveller not yet at
the airport, already there, or connecting in Bengaluru:

```bash
uv run python -m crewops.taste.plan TR-1001 --delay KS434=240
uv run python -m crewops.taste.plan TR-1002 --delay KS434=240
uv run python -m crewops.taste.plan TR-1003
```

## Deploying

Infrastructure is defined with the AWS CDK in Python and deployed to `ap-southeast-2`
(Sydney) by default. You need Node.js and an AWS CLI profile for the target account. Every
resource is named `groundtime-<stage>-...` and every stack `Groundtime-<stage>-...`.

1. **Profile and region**, once: `aws configure --profile groundtime`, and a `.env` with
   `AWS_PROFILE=groundtime` (access keys stay in `~/.aws`, never in `.env`).
2. **The Qloo key**, once per stage, typed at the prompt rather than on the command line:

   ```bash
   read -rs QLOO_KEY && aws ssm put-parameter --name /groundtime-dev/qloo/api-key \
     --type SecureString --value "$QLOO_KEY" --profile groundtime --region ap-southeast-2 && unset QLOO_KEY
   ```

3. **Build the MCP server's package and deploy** (the package carries ARM64 wheels for
   AgentCore; no Docker needed):

   ```bash
   scripts/cdk.sh bootstrap                 # once per account and region
   uv run python -m crewops.mcp.package     # builds build/mcp_server
   scripts/cdk.sh deploy --all
   ```

   On Windows, run the CDK directly with the same settings:

   ```powershell
   $env:AWS_PROFILE="groundtime"; $env:AWS_REGION="ap-southeast-2"; $env:CREWOPS_STAGE="dev"
   npx --yes aws-cdk@latest deploy --all --profile groundtime
   ```

   AgentCore expects Linux file permissions in the package; if the server fails to start after
   a deploy from Windows, deploy `Groundtime-dev-Mcp` from Linux, macOS or WSL.

4. **Create the demo accounts** (asks for one password for all of them, never stored):

   ```bash
   uv run python -m crewops.auth.provision            # what would change
   uv run python -m crewops.auth.provision --apply
   ```

5. **The web app.** `uv run python -m crewops.web_env` writes `web/.env.local` from the stack
   outputs for a local run (`cd web && npm run dev`). For Amplify Hosting, connect the
   repository (it uses `amplify.yml`, app root `web`) and set three environment variables from
   the same outputs: `CREWOPS_REGION`, `CREWOPS_USER_POOL_CLIENT_ID` and
   `CREWOPS_MCP_RUNTIME_ARN`. The web app's server needs no AWS credentials: sign-in is
   Cognito's public API, and every tool call carries the user's own token.

Call the deployed server the way any MCP host would (it asks for the password):

```bash
uv run python -m crewops.mcp.client --as neha.joshi tools
uv run python -m crewops.mcp.client --as tr1001.kapoor my_trip
uv run python -m crewops.mcp.client --as tr1001.kapoor ask "My flight is late, what can I do?"
```

### Settings

Read from `.env` in the repository root (not committed) and the environment; a value set in
the shell wins. Only `AWS_PROFILE` is required.

| Variable | Default | Purpose |
|---|---|---|
| `AWS_PROFILE` | none | AWS CLI profile to deploy and run with; `default` is refused |
| `AWS_REGION` | `ap-southeast-2` | Region for every resource |
| `CREWOPS_STAGE` | `dev` | Prefix for resource names (`groundtime-<stage>-...`) |
| `QLOO_API_URL` | `https://hackathon.api.qloo.com` | Qloo Taste AI API |
| `QLOO_API_KEY` | none | Local runs only; the deployed server reads Parameter Store |
| `CREWOPS_QLOO_CACHE_HOURS` | `24` | How long a Qloo answer is reused |
| `CREWOPS_CONCIERGE_MODEL_ID` | `global.amazon.nova-2-lite-v1:0` | The concierge's model; any Converse model with tool calling |

The deployed server runs on the real clock. Tests and local runs use a fixed moment
(13 October 2026, 13:00 in India), so they give the same result every time.

## The demo

Demo sign-ins (`data/team/demo_team.json`):

| Username | Who |
|---|---|
| `tr1001.kapoor` | Aarav, booked on KS434 Goa to Bengaluru, not at the airport yet; vegetarian, loves A. R. Rahman and *Lagaan* |
| `tr1002.fernandes` | Sara, on KS434, already at the airport |
| `tr1003.shah` | Meher, Mumbai to Delhi via Bengaluru (KS432, KS588); Jain |
| `tr1004.das` | Rahul, no trip yet: books one in the app |
| `neha.joshi` | Customer care |
| `c1042.nair` | Crew |
| `priya.desai` | Admin |

The pre-booked passengers' trips are on the next day their flights operate. KS434 leaves Goa
at 16:00 every day, so before 16:00 it is today's; after that, tomorrow's.

1. As `tr1004.das`, book Goa to Bengaluru, pick a few things you love from the short list,
   say you eat vegetarian, and confirm. My trip shows the flight on time.
2. As `neha.joshi`, open the flight board for that day and record KS434 240 minutes late.
3. As `tr1001.kapoor`, open My trip: the plan near Goa airport, on the way in, ending at the
   terminal in time. Switch to "I'm at the airport": the plan stays inside the terminal.
4. Ask the concierge "Something to watch before I board?".
5. Back as `neha.joshi`, open KS434 under "Delayed now": every Groundtime passenger's plan,
   with their dietary needs shown only as met.

## License

[MIT](LICENSE)
