# Groundtime web app

Groundtime turns every hour on the ground into one worth having: when a flight is delayed
or a connection is long, each passenger's and crew member's safe free time is planned with
Qloo and checked (opening hours, dietary needs, back at the gate in time). This app holds
the passenger's trip page, customer care's view of every delayed flight, the assistant, and
crew control's console, approvals, crew phone view and admin pages. Next.js 16 (App
Router), TypeScript and Tailwind.

The browser calls no AWS API except the live-events socket. Every action goes to this
app's server routes, which forward it to the Groundtime MCP server on AgentCore as the
signed-in user. Tokens stay in httpOnly cookies; only the live-events socket gets the ID
token.

## Run it

From the repository root, after the stacks are deployed:

```bash
uv run python -m crewops.web_env     # writes web/.env.local from the stack outputs
cd web
npm install
npm run dev                          # http://localhost:3000
```

Sign in as any member of the demo team. Spoken answers use Amazon Polly with the AWS
profile in `.env.local`; everything else uses only the signed-in user's token.

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
  (app)/trip/          A passenger's wait, planned: flight, stops, films, taste picker
  (app)/care/          Customer care: delayed flights and every passenger's plan
  (app)/console/       Waiting work, live status feed, a disruption's plans and actions
  (app)/assistant/     The assistant: talk or type, spoken answers, follow-ups
  (app)/crew/          Crew phone view: my hours, report unavailable, layover care
  (app)/admin/         Alert addresses (admins)
  api/                 Sign-in, the MCP tool proxy, live-events token, speech
components/            Shell, signed-in user, small UI pieces
lib/                   Cognito, session cookies, MCP client, AppSync Events protocol
tests/                 Vitest unit tests
```

The tree above is the core. `app/` also holds the disruption list (`(app)/disruptions/`),
the reporters' Operations board (`(app)/operations/`) and Report page (`(app)/report/`),
the approvals queue (`(app)/approvals/`), the public `evaluation/` page and the desk
`speaker/`. Under `api/`, `push/` hands out the public key for desktop alerts and `speaker/`
pairs the desk speaker and serves its feed.