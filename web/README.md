# Groundtime web app

Groundtime turns every hour on the ground into one worth having: when a flight is delayed or
a connection is long, a passenger's wait is planned with Qloo around what they love and
checked (opening hours, dietary needs, back at the gate in time). This app holds the
traveller's booking and trip page, crew's flights and layover plan, customer care's flight
board and every waiting passenger's plan, and the admin's accounts. Next.js 16 (App Router),
TypeScript and Tailwind.

The browser calls no AWS API. Every action goes to this app's server routes, which forward
it to the Groundtime MCP server on AgentCore as the signed-in user. Tokens stay in httpOnly
cookies.

## Run it

From the repository root, after the stacks are deployed:

```bash
uv run python -m crewops.web_env     # writes web/.env.local from the stack outputs
cd web
npm install
npm run dev                          # http://localhost:3000
```

The app needs only `CREWOPS_REGION`, `CREWOPS_USER_POOL_CLIENT_ID` and
`CREWOPS_MCP_RUNTIME_ARN`. Sign in as any member of the demo team
(`data/team/demo_team.json`): a traveller (`tr1001.kapoor` to `tr1004.das`), crew
(`c1042.nair`), customer care (`neha.joshi`) or the admin (`priya.desai`).

`npm run start` (production mode) marks the sign-in cookies Secure, so over plain http it
works only on `localhost`; use `npm run dev` on a local network address.

## Check it

```bash
npm test             # unit tests, offline
npm run typecheck
npm run lint
npm run build
```

## Layout

```
app/
  login/               Sign-in
  (app)/trip/          Traveller: book a trip (flight, what you love, where you'll be), then
                       the trip, the wait, the plan for it and the concierge
  (app)/crew/          Crew: my flights, the next layover's plan, what I love
  (app)/care/          Customer care: the flight board, recording delays, every waiting
                       passenger's plan
  (app)/admin/         Admin: accounts and password resets
  api/                 Sign-in and the MCP tool proxy
components/            Shell, booking, plan, concierge, taste picker, small UI pieces
lib/                   Cognito, session cookies, MCP client, Groundtime shapes and helpers
tests/                 Vitest unit tests
```
