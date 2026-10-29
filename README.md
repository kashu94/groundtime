# Groundtime

**Every hour on the ground, worth having.** An airline agent that turns a delay or a long
connection into time well spent, for passengers and for crew. Built on the Qloo Taste AI API,
the Model Context Protocol and AWS.

KS434 from Goa is four hours late. The airline knows at 13:00; its passengers find out at
the gate. One is still at their hotel and could have had the afternoon. One is past
security with nothing to do. One is connecting in Bengaluru, Jain, with three and a half hours
to fill. Today they all get the same SMS and, at best, the same meal voucher.

Groundtime gives each of them a plan of their own, the moment the delay is reported:

* **Still in town:** Cansaulim Beach at 14:55, a vegetarian lunch at 16:25, head back at
  17:25, at the terminal door by 18:16, with 18:20 the deadline. Every stop is real, open for
  the whole visit, picked by Qloo for what this traveller loves, and the rides are counted.
* **Past security:** no suggestion to leave, because they can't. Food at the terminal, and a
  105-minute film matched to their taste that ends before the gate closes.
* **Crew on the same disruption:** dinner near the crew hotel inside their legal rest, with
  eight hours of sleep protected before the next report.

> Qloo chooses, the engine checks, the model talks. The model never calculates a time and
> never names a place a tool didn't return.

## How Qloo is used

Qloo is the taste in every plan. Nothing in Groundtime recommends anything without it.

| Groundtime asks Qloo | Qloo API | Then the engine checks |
|---|---|---|
| Places to see near the airport, for this traveller's taste | Insights, `urn:entity:place` with `filter.location`, genre tags, the traveller's loves as `signal.interests` | It is a real sight (Qloo also tags hotels and travel agents as attractions); open for the whole visit; the ride there, on and back gets them to the terminal in time |
| Somewhere to eat | Insights, restaurant genre, plus a second list filtered to a dietary option they need | Offers every dietary option they need; open; within reach |
| Food without leaving the terminal | Insights within 900 m of the terminal | It is a place to eat, not a lounge or a duty-free shop; open now |
| Something to watch while waiting, or on the flight | Insights, `urn:entity:movie` and `urn:entity:tv_show`, cross-domain from the music, books and films they love | The film's running time ends before the gate closes; episodes fit the wait |
| What the traveller loves | Search, over Qloo's catalogue | Each pick is a Qloo id, never free text |
| Where a crew can eat tonight | Insights near the crew hotel, with the crew's shared loves | Open for a whole meal inside the free window the roster gives; every dietary need; quiet after a tiring day |

**The wait, from the schedule.** For each traveller the engine works out when their time is
their own and the two deadlines that matter: the terminal door (bag drop and security still
ahead) and the gate. A delay is time handed back: the free time starts when they would have had
to be at the airport. Where they are decides what is possible (`crewops.taste.groundtime`):

| Where the traveller is | Groundtime plans |
|---|---|
| Not at the airport yet (the delay is known early) | An outing around the airport, ending at the terminal door in time |
| At the terminal, before security | The same, if the time allows after the walk out and back; otherwise the terminal |
| Past security, or on a connection | The terminal only: screened passengers can't walk back out of an Indian airport. Food there, and films and series that fit |

The network is domestic, so no visa applies. An international transit would add one more
rule here: no entry permission, no outing.

**The concierge, an agent with Qloo tools.** A traveller can simply ask: "my flight's late and
I'm still at the hotel, what can I do?" Amazon Nova decides which tools to call (`my_wait`,
`plan_groundtime`, `find_to_watch`, `search_catalogue`) and words the answer. Before it is
shown, every capitalised name in it is matched against what the tools returned; one that isn't
there means the model made it up, and the traveller gets the checked plan written out instead
(`crewops.taste.concierge`).

**Re-planned by the delay itself.** Delays are reported once, through the operations side
(a reporter, or a feed), and every plan reads them live: a new delay moves every affected
traveller's deadlines and plan at once. Customer care sees each delayed flight's travellers
and what was planned for them.

**Privacy.** Qloo is called only from the server, with ids, a map point and a radius. No
name, username, crew id, traveller id or email is ever sent; a guard refuses any request that
could carry one (`crewops.taste.qloo.guard`). Customer care and controllers see that a plan
meets someone's dietary needs, never what the needs are. Taste is opt-in.

## The operations side

The same app runs the airline's crew control, which is where delays come from and what keeps
the crew side legal:

* A reporter records a disruption (a delay, sick crew, a gate closure); the analysis works out
  who and what it touches and the legal options, ranked by cost, before a controller asks.
* A controller picks cover and a different person approves it (four eyes); only then is the
  roster changed, in one transaction.
* Every crew id, duty hour and rupee in an answer comes from a deterministic legality engine,
  and a verifier checks the wording against the tool results.
* A desk speaker announces new disruptions; desktop alerts and email reach the right role.

## Roles

| Role | Can do |
|---|---|
| Traveller | Their own trip: the wait, the plan, the concierge, their taste profile |
| Customer care | Every delayed flight and each Groundtime traveller's plan (needs shown only as met) |
| Crew | Own schedule, own unavailability, a taste profile, their own layover brief |
| Reporter | Record any disruption, including flight delays; follow their own reports |
| Controller | Review disruptions and options, submit one plan for approval, see a crew's layover brief |
| Approver | Approve or reject submitted plans; approval commits them |
| Auditor | Read-only access to every disruption, decision and audit record |
| Admin | Revoke a report filed in error, reset passwords, book planned leave, tighten rule thresholds, read the activity log, manage alert addresses. Never submits or approves a plan |
| Super admin | Everything an admin does, and also resets admins' passwords and relaxes a rule threshold back towards regulation |
| Speaker | A device, not a person: hears the alert briefs for its desk or area |

Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#roles-and-approvals).

## Architecture

```
   Web app (Next.js)                              Any MCP host
   my trip · customer care · crew · console       (Claude Code, VS Code, MCP Inspector)
              \                                     /
               ▼                                   ▼
        ┌──────────────────────────────────────────────────────────┐
        │ Groundtime MCP server on AgentCore Runtime                │
        │ concierge agent (Nova) · crew-control agent (Nova)        │
        │ Bedrock Guardrails · AgentCore Memory                     │
        └───────┬───────────────────┬──────────────────────┬────────┘
                ▼                   ▼                      ▼
        Groundtime planner    Legality engine        S3 Vectors + Titan V2
        wait · checks ──────► Qloo Taste AI API
        layover care          (Insights, Search, Tags)
                │                   │
                ▼                   ▼
        DynamoDB (operation, delays, taste profiles, Qloo cache)
           │──Streams──┬──► disruption analysis (Lambda)
           ▲           └──► notifier (Lambda) ──► live updates (AppSync Events)
           │                                  └─► email alerts (SNS, by role)
        SQS ingestion (live reports) · S3 roster uploads (batch)
```

Full design: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Why each piece was chosen:
[docs/DECISIONS.md](docs/DECISIONS.md).

## Services

| Service | Role |
|---|---|
| Qloo Taste AI API | Every recommendation: places to see and eat around the airport and in the terminal, films and series, places near the crew hotel; the catalogue travellers and crew pick their loves from |
| Amazon Bedrock | Amazon Nova for language only (the concierge's tool choice and wording, crew-control routing), Titan V2 embeddings, Guardrails |
| Amazon Bedrock AgentCore | Runtime for the agents and the MCP server, Memory |
| Amazon DynamoDB | The operation, reported delays, taste profiles and the Qloo answer cache (single table) with Streams |
| Amazon S3 Vectors | Hybrid search over rules, example questions and past scenarios |
| Amazon SQS + AWS Lambda | Real-time disruption ingestion and background analysis |
| Amazon SNS | Email alerts by role, including customer care |
| Amazon EventBridge Scheduler | One-time escalation checks |
| AWS Systems Manager Parameter Store | The Qloo API key and the web push keys, as SecureStrings |
| AWS AppSync Events | Live updates |
| Amazon Cognito | Sign-in, with one group per role |
| Amazon Polly | Spoken answers in the assistant and on the desk speaker |
| AWS Amplify Hosting | The web app |
| AWS CDK | Infrastructure as code |

## Repository layout

The Python package is `crewops`: the operations engine Groundtime is built on.

```
data/seed/              The seed operating week (JSON), carried forward to 31 December on load
data/eval/              Gold questions, paraphrases, reference scenarios and the held-out set
data/team/              The demo team and demo passengers (bookings by flight number), demo
                        taste profiles; nothing private
src/crewops/
  taste/                Groundtime: the Qloo client and guard, airports and crew hotels, the
                        wait, the plan and its checks, the concierge agent, layover care
  config.py             Runtime settings
  domain/               Typed records shared by every layer
  ingestion/            Seed loading, roster uploads (S3 + Lambda), live reports (SQS + Lambda)
  engine/               Legality engine: duty math, the seven rules, assessment, cost ranking,
                        blast radius, delay effects, joint plans
  analysis/             Disruption analysis, its stream Lambda and the run command
  search/               Hybrid keyword + semantic search over S3 Vectors
  store/                DynamoDB key layout, item conversion, reads and writes
  tools/                The crew-control tools agents call: schemas, role checks, dispatch
  agent/                Crew-control question pipeline: router, planner, verifier, Nova roles
  auth/                 Sign-in: the team, token checks, claims to caller, account sync
  plans/                Plans and approvals, with the four-eyes rules
  mcp/                  The MCP server for AgentCore, its package builder and a client
  notify/               Live events, email alerts, escalation and desktop alerts
  alerts.py             Spoken alerts for the desk speaker and "welcome back"
skills/                 The Agent Skill (SKILL.md, references, a client script)
web/                    The web app (Next.js): my trip, customer care, crew, console, assistant
infra/                  AWS CDK app: one stack per part of the system
tests/                  Unit tests
docs/                   Architecture and decisions
```

## Getting started

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run pytest
uv run ruff check .
```

## Deploying

Infrastructure is defined with the AWS CDK in Python and deployed to `us-east-1` by
default. You need Node.js (22 or later recommended) and an AWS CLI profile for the target
account. Every resource is named `groundtime-<stage>-...` and every stack
`Groundtime-<stage>-...`, so a stage never touches anything else in the account.

```bash
aws configure --profile groundtime   # once: access keys stay in ~/.aws

scripts/cdk.sh bootstrap          # once per account and region
scripts/cdk.sh diff               # what would change
scripts/cdk.sh deploy --all       # create or update the stacks
scripts/cdk.sh destroy --all      # remove a dev stage completely
```

`scripts/cdk.sh` reads `.env`, refuses to run without a named profile, and prints the
target account before calling the latest CDK CLI. The CLI must be at least as new as the
`aws-cdk-lib` the app uses; an older global install fails with a "cloud assembly schema
version mismatch". On Windows, run the same settings directly:

```powershell
$env:AWS_PROFILE="groundtime"; $env:AWS_REGION="us-east-1"; $env:CREWOPS_STAGE="dev"
npx --yes aws-cdk@latest deploy --all --profile groundtime
```

### Settings

Settings are read from a `.env` file in the repository root (not committed) and from the
environment; a value set in the shell wins over the file. Only `AWS_PROFILE` is required.

| Variable | Default | Purpose |
|---|---|---|
| `AWS_PROFILE` | none | AWS CLI profile to deploy and run with; `default` is refused |
| `AWS_REGION` | `us-east-1` | Region for every resource |
| `CREWOPS_STAGE` | `dev` | Prefix for resource names (`groundtime-<stage>-...`) |
| `QLOO_API_URL` | `https://hackathon.api.qloo.com` | Qloo Taste AI API |
| `QLOO_API_KEY` | none | Local runs only; deployed services read Parameter Store |
| `CREWOPS_QLOO_CACHE_HOURS` | `24` | How long a Qloo answer is reused |
| `CREWOPS_ROUTER_MODEL_ID` | `amazon.nova-micro-v1:0` | Triage model |
| `CREWOPS_ADVISOR_MODEL_ID` | `global.amazon.nova-2-lite-v1:0` | Tool-calling advisor model |
| `CREWOPS_EXPLAINER_MODEL_ID` | `global.amazon.nova-2-lite-v1:0` | Answer rewriting model |
| `CREWOPS_EMBEDDING_MODEL_ID` | `amazon.titan-embed-text-v2:0` | Embeddings for search |
| `CREWOPS_EMBEDDING_DIMENSIONS` | `512` | 256, 512 or 1024 |
| `CREWOPS_GUARDRAIL_ID` | none | Bedrock guardrail, once deployed |
| `CREWOPS_GUARDRAIL_VERSION` | none | Published guardrail version; required with the id |
| `CREWOPS_MAX_TOOL_ITERATIONS` | `8` | Cap on the advisor's tool loop |
| `CREWOPS_RESPONSE_BUDGET_SECONDS` | `6.0` | Time budget for a spoken answer |
| `CREWOPS_ROUTER_SEMANTIC_FLOOR` | `0.45` | Least similarity for the router to borrow an example question's intent; set from `crewops.agent.calibrate` |
| `CREWOPS_QUEUE_SENDERS` | none | IAM ARNs, besides the MCP server, allowed to send reports to the queue (comma-separated) |

A minimal `.env`:

```bash
AWS_PROFILE=groundtime
```

Access keys never go in `.env`; they stay in `~/.aws`.

### The Qloo API key

The deployed MCP server reads the key from a SecureString in Parameter Store, once per
process, so it is in no template, environment variable or log. Store it once per stage,
typing the key at the prompt rather than on the command line:

```bash
read -rs QLOO_KEY && aws ssm put-parameter --name /groundtime-dev/qloo/api-key \
  --type SecureString --value "$QLOO_KEY" --profile groundtime && unset QLOO_KEY
```

For local runs, put `QLOO_API_KEY=...` in `.env` (git-ignored). Try a layover brief for the
seed week's Delhi night stop, live against Qloo:

```bash
uv run python -m crewops.taste.brief P-2291
```

And a passenger's Groundtime plan, for KS434 from Goa four hours late, with the traveller in
town, past security, or connecting in Bengaluru:

```bash
uv run python -m crewops.taste.plan tr1001.kapoor --delay KS434=240
uv run python -m crewops.taste.plan tr1002.fernandes --delay KS434=240
uv run python -m crewops.taste.plan tr1003.shah
```

### The Groundtime demo

The demo passengers (`data/team/demo_travellers.json`) book flight numbers, so their trip is
on whichever day the flight next operates: on the deployed app, today or tomorrow. Their
accounts are created with the rest of the team (`crewops.auth.provision`). To see Groundtime
react to a delay:

1. Sign in as a reporter (`imran.sheikh`), open Report, and report KS434 (today's) delayed
   by 240 minutes.
2. Sign in as `tr1001.kapoor` (not at the airport yet): My trip shows an outing around Goa,
   back at the terminal in time. Switch to "past security" and the plan stays in the terminal.
3. Ask the assistant "my flight is late, what can I do?": the concierge answers from the plan.
4. Sign in as `neha.joshi` (customer care): Customer care lists KS434 and every Groundtime
   passenger's plan.

After the first deploy, load the operation into the table (about 5,000 items):

```bash
uv run python -m crewops.ingestion.load_seed --dry-run   # validate and count, no AWS calls
uv run python -m crewops.ingestion.load_seed             # validate, then write
```

The seed is one hand-built week (12 to 18 October 2026). The loader carries it forward to
31 December (`crewops.ingestion.calendar`), past the end of the year: the same flights each
week with passengers booked varying a little, and the crew rotating within their airline,
rank and base, so nobody flies the same days for ever; the reserve pool stays on call. Every
generated week is checked with the legality engine (rest across the weekend, the 7- and
28-day limits, certificates) and anyone who would break a rule is swapped with a colleague,
so the roster is legal before any disruption. `--week-only` loads the seed week alone.

The deployed services run on the real clock (`CREWOPS_REAL_TIME=1`, set by their stacks):
flights before now count as flown, a disruption is reported for today up to two months
ahead, crew see their flights from five days back to two months ahead, and the Operations
board moves a week at a time across the same span. Tests, the evaluation and local runs keep
the seed's own moment (12 October, 18:00 UTC), so they give the same result every time.

Planned leave (annual leave, a planned operation, a course) is not a disruption. An admin
books it on the Admin page, up to the end of the rostered period, as rostering would. The
person is never offered as cover then, and any trips they already have in that period go to
a controller to re-crew in advance, with four-eyes approval as usual.
Nothing about it is urgent, so it gets the controller's email but no escalation, no desktop alert, no speaker announcement and no team emails.

Loading only writes, so a table that holds an older week keeps it beside the new one. On the
disposable `dev` and `test` stages, `--replace` empties the table first, including every
disruption, plan and audit event; any other stage refuses it.

```bash
uv run python -m crewops.ingestion.load_seed --replace   # dev/test: start from a clean table
```

### Uploading roster changes

Admins change the operation by uploading a JSON file to the roster bucket (its name is in the
`Groundtime-dev-Ingestion` stack outputs). The file holds any of the operation's collections in
the same shapes as the seed files, for example `{"pairings": [...]}`; the seed's
`rosters.json` and `rules.json` can be uploaded as they are.

```bash
aws s3 cp week-38.json s3://<roster-bucket>/uploads/week-38.json --profile groundtime
aws s3 cp s3://<roster-bucket>/results/week-38.json.result.json - --profile groundtime
```

A Lambda merges the upload over the current operation, validates the whole result, and
writes the uploaded records only if there are no errors. Records with the same id are
replaced and new ids are added; nothing is deleted. Every upload gets a report under
`results/` saying accepted or rejected, with the errors and any new warnings. Upload one
file at a time: two uploads processed at the same moment are each checked against the
operation as it was before either of them.

### Sending a live report

Reports go to the SQS ingest queue, where a worker Lambda validates them, checks the role
the sender states and every id they name, and stores each one once as a REPORTED
disruption. Only the MCP server may send reports, and it sets the sender from the user's
verified login. The queue's policy refuses everyone else unless their IAM ARN is listed in
`CREWOPS_QUEUE_SENDERS` when the ingestion stack is deployed. This development command
states the sender directly, so to keep using it, list your own IAM user's ARN there. Do the
same before moving messages back from the dead-letter queue, since that sends them again as
you.

```bash
uv run python -m crewops.ingestion.send_report crew_unavailable \
  --user u-17 --role reporter \
  --details '{"crew_id": "C-1042", "from_date": "2026-10-13", "reason": "sick"}'
```

Report types: `crew_unavailable`, `multiple_crew_unavailable`, `certification_lapse`,
`flight_delay`, `aircraft_technical`, `station_disruption`, `gate_closure`, `gate_change`.
Add `--dry-run` to validate without sending. Crew may report only their own unavailability; auditors and admins may not
report.

### Search indexes

After the first deploy, embed the rules, example questions and scenarios into S3 Vectors, and
try a query:

```bash
uv run python -m crewops.search.index --dry-run   # count documents, no AWS calls
uv run python -m crewops.search.index             # embed with Titan V2 and store
uv run python -m crewops.search.index --index rules --query "how much rest does a pilot need"
```

### Disruption analysis

Each new disruption is analysed automatically from the table's change stream and stored as
OPTIONS_READY. Disruptions reported before that existed, or whose analysis was parked after
a failure, can be analysed on demand; it is safe to run repeatedly. Each analysed
disruption goes to the controller desk with the fewest open disruptions; the reporter never
picks one:

```bash
uv run python -m crewops.analysis.run --pending
uv run python -m crewops.analysis.run --id r-demo-0001
```

The `dev` and `test` stages are disposable: destroying them deletes their data. Any other
stage keeps its table, with point-in-time recovery and deletion protection.

### The demo team

Sign-in uses a Cognito user pool with one group per role (the `Groundtime-<stage>-Auth` stack).
Nobody signs themselves up, and no email or phone is stored. The team is defined in
`data/team/demo_team.json`: three controllers (one per desk), three approvers, two
reporters, eleven crew members across the three airlines, an auditor, an admin, a super
admin, and the ops-room speaker device (`ops.speaker`). Usernames are first name and surname
(`ananya.iyer`); a crew member's starts with their crew number (`c1042.nair`). To create or
update the accounts after deploying the stack:

```bash
uv run python -m crewops.auth.provision            # what would change
uv run python -m crewops.auth.provision --apply    # asks for the accounts' password once
```

The password is read from `CREWOPS_TEAM_PASSWORD` in the shell, or asked for, checked against
the pool's rules before anything changes, and never stored. Every demo account shares it, so
treat it as a demo password only. Running the command again changes only what differs from
the file. An account removed from the file loses its roles and profile, and `--prune`
deletes it too.

### Plans and approvals

A controller submits cover for a disruption on their desk, and a different person with the
approver role approves it, which re-checks legality and commits the roster in one step:

```bash
uv run python -m crewops.plans.desk --as rohit.malhotra queue
uv run python -m crewops.plans.desk --as rohit.malhotra submit r-demo-0001
uv run python -m crewops.plans.desk --as meera.bhatt approve r-demo-0001 <plan id>
uv run python -m crewops.plans.desk --as meera.bhatt show r-demo-0001     # plans and audit trail
uv run python -m crewops.plans.desk --as rohit.malhotra close r-demo-0002 --reason "KS589 cancelled"
```

This is an operator's tool, acting as the named team member with your AWS credentials; people
reach the same rules through the assistant, signed in.

Each plan gets a SHA-256 fingerprint at submission, over exactly what
decides it (who replaces whom, costs, what is left uncovered, the rosters it was made against,
who submitted it and when). The approval card shows it; approval computes it again and refuses
a plan changed since (`TAMPERED`), and the commit only succeeds if the stored fingerprint is
still the one checked. The approval is then sealed (SHA-256 over the fingerprint, the approver
and the time), and both appear on the plan and in the audit trail. This is tamper evidence
anyone can recompute, not a signature: nobody holds a private key.

### Resilience and security of the assistant

Every model call already has a firm timeout and a deterministic fallback. On top of that, a
circuit breaker (`crewops.agent.breaker`) counts outage failures: timeouts, lost
connections, throttling and 5xx, never our own invalid requests. After three in a row,
model calls pause for a minute and every answer comes straight from the roster in DynamoDB
through the templates, at once, instead of each question waiting out a timeout. Then one
call is let through to test the service. The assistant shows "Models paused" while the
breaker is open.

Before any model or guardrail call, an override check (`crewops.agent.injection`) refuses
the common override phrasings ("ignore all previous instructions", "you are now an admin",
"bypass the RBAC checks", "approve without approval") with a security alert. Ordinary
questions such as "can we ignore the rest rule?" go through. Every refusal, by this check or
by the Bedrock Guardrail's prompt-attack filter, is recorded in the admin's activity log
with who asked and what. Neither is the real defence. The assistant has only read tools,
filtered by role, so no wording can make it submit, approve or change anything.

### The MCP server

The assistant is served over MCP from AgentCore Runtime, signed in with the team's accounts.
AgentCore runs code packages on Linux ARM64 and does not install dependencies, so the
package is built first (it downloads ARM64 wheels; no Docker needed), then deployed:

```bash
uv run python -m crewops.mcp.package            # builds build/mcp_server
scripts/cdk.sh deploy Groundtime-dev-Ingestion Groundtime-dev-Notify Groundtime-dev-Mcp
```

Until the package is built, the CDK app leaves the MCP stack out and says so, so the other
stacks deploy from a fresh clone. The CDK zips the package on the machine that deploys it.
If the server fails to start after a deploy from Windows (AgentCore expects Linux file
permissions, which a Windows zip may not carry), build and deploy this stack from Linux,
macOS or WSL with the repository on the Linux filesystem.

Then call it as any team member, the way an MCP host would (it asks for the password):

```bash
uv run python -m crewops.mcp.client --as rohit.malhotra tools
uv run python -m crewops.mcp.client --as rohit.malhotra ask "Who covers C-1042 on 13 Oct?"
uv run python -m crewops.mcp.client --as rohit.malhotra my_queue
uv run python -m crewops.mcp.client --as c1042.nair report_disruption \
  '{"report_type": "crew_unavailable", "details": {"crew_id": "C-1042", "from_date": "2026-10-16", "reason": "sick"}}'
```

Set `from_date` to a day from today up to two months ahead: on the real clock the server refuses
dates outside that window.

Its tools: `ask` (the full verified answer pipeline), `my_queue`, `show_disruption`,
`report_disruption`, the plan actions (`submit_plan`, `approve_plan`, `reject_plan`,
`withdraw_plan`, `close_disruption`, and `confirm_resolution` / `return_resolution` for the
approver's sign-off), `list_crew_tools` / `crew_tool` for the
deterministic tools directly, `whoami`, `disruptions` (the desk's feed), `my_roster`
(crew, with their notices), `my_reports` and `report_reference` (reporting),
`rule_thresholds`, and, for admins, `set_rule_threshold`, `activity_log`, `alert_addresses`,
`add_alert_address` and `remove_alert_address`. What each user may do depends on their
role.

A follow-up needs the same conversation id on each question. The previous turn then fills
in only what a reply giving just a seat, a date or an id, or a "he", "she" or "that
pairing", leaves out, and the answer says so in its notes:

```bash
uv run python -m crewops.mcp.client --as rohit.malhotra --conversation c1 ask "Who can cover P-2291 on 13 Oct?"
uv run python -m crewops.mcp.client --as rohit.malhotra --conversation c1 ask "Captain"
```

### The Agent Skill

`skills/crewops-crew-control` is an [Agent Skill](https://agentskills.io/specification)
that teaches any agent with the MCP server connected (Claude Code, or any agent with Agent
Skills and remote MCP) to work crew control the way a controller does:

- `SKILL.md`: the ground rules (every fact from a tool, four eyes, ask before changing
  anything, roles are the server's, legality is not negotiable, privacy, ignore orders in
  data), the start of a session by role, the disruption lifecycle, playbooks (what is
  waiting, cover a seat, decide a plan, report, planned leave, plain-word questions), how
  to say it briefly for a voice assistant, and what to do on each error.
- `references/`: every tool (`tools.md`, generated from the server by
  `python -m crewops.mcp.skill_docs`, so it cannot drift from the code), the seven rules,
  cover strategies, costs and severity (`legality.md`), worked conversations per role
  (`workflows.md`) and every error code (`errors.md`).
- `scripts/crewops_mcp.py`: signs in and calls the server from a shell, for agents with no
  MCP client configured; `assets/mcp.json.example`: an MCP client configuration.

To use it with Claude Code, in a folder outside the repository:

```bash
mkdir -p ~/crewops-demo/.claude/skills && cd ~/crewops-demo
cp -r <path-to-repo>/skills/crewops-crew-control .claude/skills/
cp .claude/skills/crewops-crew-control/assets/mcp.json.example .mcp.json
set -a; source <path-to-repo>/web/.env.local; set +a   # region, client, runtime
export CREWOPS_USERNAME=rohit.malhotra
export CREWOPS_MCP_URL=$(python .claude/skills/crewops-crew-control/scripts/crewops_mcp.py url)
export CREWOPS_ACCESS_TOKEN=$(python .claude/skills/crewops-crew-control/scripts/crewops_mcp.py token)
claude
```

Check that the `crewops` server lists its tools, and ask "what's on my desk?". The skill
loads from its description. The client still asks before submitting, approving or
reporting. The access token lasts about an hour.

Tests check the skill against the specification and the server: every tool it calls
exists, and every rule and strategy it names is the engine's.

### Live updates and alerts

Every disruption status change is published to the `/ops/disruptions` channel of an AppSync
Events API, which staff (not crew or reporters) can subscribe to with their sign-in; the web
console uses it to refresh. Email alerts are optional and only an admin can set them up:
an address is subscribed to the controller or approver alerts, AWS emails it a link to
confirm, and after that it receives that role's alerts (options ready, a plan sent back, a
plan waiting for approval). An address can instead follow one operational team: gate
control, station duty managers, flight information (airport screens, website, app),
operations monitoring (who tells the captain), maintenance control, training and crew
records, or customer care. Each analysed disruption emails the teams it needs, for example
a delay goes to flight information, operations monitoring, the station and customer care.
An address holds one role or team, and at most five addresses can be added a day.

```bash
uv run python -m crewops.mcp.client --as priya.desai add_alert_address \
  '{"email": "you@example.com", "role": "approver"}'
uv run python -m crewops.mcp.client --as priya.desai alert_addresses
```

#### Escalation

When a disruption reaches a desk (analysed, or its plan sent back), the
notifier creates a one-time EventBridge Scheduler schedule for 10 minutes later
(`CREWOPS_ESCALATE_AFTER_MINUTES`), which deletes itself after it runs. If by then nobody has
submitted a plan or closed it, the addresses subscribed to the duty supervisor audience
get an email, and the desk and room speakers announce "Escalated". If anything was done,
nothing happens. Subscribe an address the same way, with `"role": "duty_supervisor"`.

#### Desktop alerts (web push)

A controller or approver can click the bell in the web app's
header to get a notification from the browser when something reaches their desk or waits for
approval, even with Groundtime closed. Clicking the notification opens the disruption. The
browser's push service (Google, Microsoft or Mozilla) delivers it free of charge; each message
is encrypted for that one browser and signed with the app's key. Set up once, after the MCP
package is built and the Notify stack deployed:

```bash
uv run python -m crewops.notify.webpush keys   # the app's key pair, kept in Parameter Store
uv run python -m crewops.web_env               # writes the public key for the web app
```

Signing out turns desktop alerts off in that browser. Without the keys the bell does not show.

#### Severity

Every disruption is rated high, medium or low from its analysis, never by a model. It is
high when a flight is at risk however it is handled (no legal crew, the best way out is
to cancel or fly short, a seat left unfilled, a delay breaking a duty limit), medium when it
needs a real decision or flies today or tomorrow (counted from today, not from when it was
reported), and low when a reserve covers it with time to spare. The console and disruption list show it with the reasons, and the speaker and
desktop alerts say it first ("Medium severity. …").

#### Absent on a day off

Someone reported unavailable on days they fly nothing is recorded, not put on a desk. There
is no alert, no escalation and nothing to plan, but they are not offered as cover on those
days, and the record notes their next duty. If they were on call (reserve)
then, it does go to a desk: the reserve pool at that base is one smaller. A reporter sees on
the Operations board who is out and when, never why.

Alerts and events name the disruption, its status, and for a team the flights, gates and
times it acts on, never a crew member. A crew member whose certificate lapses is told on
their own Groundtime page.

### The web app

The web app in `web/` is the desk's console, the assistant and the crew's view. It needs Node.js 20
or later and the deployed Auth, Mcp and Notify stacks:

```bash
uv run python -m crewops.web_env     # writes web/.env.local from the stack outputs
cd web && npm install && npm run dev # http://localhost:3000
```

| View | Who | What it does |
|---|---|---|
| Disruptions | controllers, approvers, auditors, admins | Every disruption, filtered by desk (mine, other desks, the whole network), state (open, resolved, all) and type |
| Operations | reporters (their landing page) | The operating week: a chart of passengers by day and airline, then every flight of the chosen day with airline, aircraft, captain, first officer, cabin crew and load. Crew reported unavailable are struck through in rose, and each flight shows its open disruptions with their severity. Click a crew name to report them unavailable that day, or "Delay" to report the flight late; the report form opens filled in. A side panel lists everyone out, by whom and for which days |
| Report | reporters | Record any of the eight disruption types, picking crew, flights, gates and stations from the operation (a crew member taken ill part-way through a day from a time, a gate closure as an internal or outside cause), and follow every report you filed, and crew members' own, as waiting, refused with the reason, or its disruption's status |
| Controller | controllers, auditors, admins | Live figures for the role, the ingestion feed of disruptions, and the solution engine: the recommendation, each seat's legal cover ranked by cost with cancellation last, every rule's margin checked on demand, crew another desk also wants, and the plan submitted from there. Each disruption's full record adds coverage figures, its desk, crew another desk is competing for (with a joint plan across both), recommendation cards by policy, a plain explanation of the chosen option, every legal option to choose from (the first ten, then the rest on request; anyone reported unavailable since is struck through), the regulated substitutes, operating short or cancelling, each chosen only after a warning, cover suggested by other desks, every excluded candidate and why, the trip's flights and crew, plans and the audit trail. A committed disruption shows the options as they stood and the choice made. Every record says in one sentence how it gets resolved (re-crew, a decision, or handled internally), shows gate moves and late flights with passengers booked, and lists who has been told and why; one handled internally is resolved with a remark, which an approver then signs off (or sends back) on the Approver view |
| Approver | approvers, auditors | The four-eyes queue: each waiting plan, approved with a second confirming click or sent back with a reason |
| Crew | crew | Notices for me (a certificate about to lapse), this week's duty calendar (days reported unavailable in rose), my flights, duty-limit gauges, reporting myself unavailable (never twice for the same days), and what became of my reports |
| Admin | admins | Who does what (admin against super admin), revoking reports filed in error, password resets (a new random password shown once), rule thresholds (an admin tightens, only a super admin relaxes), the system activity log, alert addresses and planned leave |
| Assistant | everyone | Talk or type, hear the answer (Amazon Polly) with pause, resume and stop, and follow up. The latest exchange stands out from the conversation beside it. A round button in the corner of every page opens it. |

The app opens on sign-in, which offers to continue as whoever is signed in; the session ends
when the browser closes. The "View" menu lists only the views the signed-in roles allow, a
banner slides in with every disruption status change, and a Guide in the top bar and (i)
icons explain each screen and term.

The browser calls no AWS API except the live-events socket. The app's server forwards every
action to the MCP server as the signed-in user, so every role rule is the server's. Voice
input uses the browser's speech recognition (Chrome or Edge); elsewhere, type.

The app is hosted on AWS Amplify Hosting, built from the
`dev` branch by `amplify.yml` (Node 20, root `web/`). The Amplify console holds the same
`CREWOPS_*` variables as `web/.env.local` (without `AWS_PROFILE`); the build copies them into
`.env.production`, because Amplify passes console variables to the build, not to the running
server. Spoken replies on the hosted app need a compute role that may call
`polly:SynthesizeSpeech` (App settings, IAM roles); without one the browser's own voice speaks.

### The desk speaker and "welcome back"

`/speaker` is a desk or ops-room speaker. It belongs to a place, not a person: nobody signs
in on it, and no one's sign-in or sign-out affects it. The app's server signs in as the
speaker device (the speaker role, which hears only alert briefs) and the page polls its
feed. Set it to a desk (`/speaker?for=desk-2`), `approvals` or the whole `room`, and tap "Turn
on the speaker" once (browsers allow sound only after a tap). A new alert chimes, turns the
ring amber and is announced in the Polly voice, then repeated as a reminder 15 seconds after
each announcement ends, three times at most. It stops as soon as the disruption is dealt with
(a plan submitted, resolved or closed takes it off the desk's list) or someone taps "Got it"
or asks "What are my notifications?". Several alerts take turns, oldest first. After the
third announcement the ring stays amber until someone listens. Each alert is built from the
disruption's latest event and its analysis, never from a model.

The speaker also answers questions about the room, spoken (Ask) or typed: who it is, how many desks and
controllers there are and who they are, what is open on each desk or on "my desk", which desk
is busiest, how many disruptions are open, escalated or waiting for approval, and today's
flights, crew out and reserves. The answers come from the ops board by fixed rules
(`web/lib/room-answers.ts`), so they say nothing the wall display doesn't already show.
Anything else is turned away with a pointer to the signed-in assistant, because questions about
people and legality need a signed-in person behind them.

```bash
uv run python -m crewops.web_env --speaker   # after provisioning the team
```

It gives `ops.speaker` a new random password of its own, set on the account (never the
team's), and a random pairing code it prints; both go into `web/.env.local`. Run with
`npm run dev`, a speaker needs no pairing. A hosted app (a production build) hears alerts
only on screens paired once with that code; the pairing cookie is signed with a server-side
secret, so it cannot be guessed. Re-running the command without `--speaker` keeps both;
with it, both are replaced.

When a controller or approver signs in, they see, and can hear, what came to their desk or
to approvals since they last had Groundtime open (an open console says so every few minutes);
nothing on a first sign-in, and a second tab replays nothing.

### Asking a question

Answers come from the tools and are verified before they are printed. Offline, no model is
called. With `--live`, the Nova models triage, advise and reword, the guardrail screens the
question and the answer once `CREWOPS_GUARDRAIL_ID` is set, and the tokens used are printed.

```bash
uv run python -m crewops.agent.ask "Who is on reserve at BLR on 13 Oct?"
uv run python -m crewops.agent.ask --role crew --crew-id C-1042 "How many duty hours do I have?"
uv run python -m crewops.agent.ask --live "C-1042 is sick, who covers?"   # live, with models
uv run python -m crewops.agent.ask --live --no-model "C-1042 is sick, who covers?"
uv run python -m crewops.agent.calibrate      # measure the router's similarity floor (live)
```

The guardrail is its own stack. After deploying it, copy its two outputs into `.env`. A
change to the guardrail publishes a new version number and keeps the old one, so update
`CREWOPS_GUARDRAIL_VERSION` after such a deploy:

```bash
CREWOPS_GUARDRAIL_ID=<GuardrailId output>
CREWOPS_GUARDRAIL_VERSION=<GuardrailVersionNumber output>
```

Set the floor that `calibrate` recommends as `CREWOPS_ROUTER_SEMANTIC_FLOOR` in `.env`.

### Evaluation

`data/eval/heldout.json` was written after the router rules were final and is never used to
change them. It rewords each of the 38 gold questions (same ids and dates, so the two
answers can be compared) and adds behaviour cases: off-topic questions, what each role may
see, questions back, follow-ups and prompt injection. Scoring is deterministic; no model
judges another.

```bash
uv run python -m crewops.agent.evaluate                       # offline, free
uv run python -m crewops.agent.evaluate --live --json build/evals/live.json
```

`--live` asks 99 questions (each rewording with its gold question, and both turns of each
follow-up), each with several Bedrock calls, billed per token, and prints the calls and
tokens used. It reads the deployed table, so live agreement compares two live answers, not
fixed ones. Offline results, with no model and no semantic stage (rules and templates
only):

| Measure | Offline |
|---|---|
| Rewordings whose answer states at least 80% of the gold answer's facts | 25 of 38 |
| Rewordings routed to the gold question's intent | 25 of 38 |
| Mean recall of the gold answer's facts | 0.72 |
| Off-topic questions that ran no tool | 7 of 8 |
| Role, question-back, follow-up and injection cases | 12 of 12 |
| Answers failing an independent re-verification against their tool results | 0 |
| Answers showing a redaction marker (personal data reached them) | 0 |

The rewordings the rules miss are what the semantic stage and the triage model are for;
the live run measures them.

The web app's public `/evaluation` page shows these reports: the figures above, results
by kind, and every question with its answer and checks, searchable; with both reports it
compares them side by side. Publish them by writing the reports into the web app:

```bash
uv run python -m crewops.agent.evaluate --json web/public/evals/offline.json
uv run python -m crewops.agent.evaluate --live --json web/public/evals/live.json   # Bedrock, per token
```

## License

[MIT](LICENSE)
