# Decisions

Short records of the choices that shape this project and what was traded away.

## D1. Python

The rules engine, agents, MCP server and Lambda functions share one language. boto3, the MCP
Python SDK and Strands Agents cover every AWS surface needed, and Qloo's REST API needs only
the standard library.
The web app is the one exception (D9).

## D2. DynamoDB as the operational store

| | DynamoDB (on-demand) | RDS Postgres | Aurora Serverless v2 |
|---|---|---|---|
| Latency from Lambda | Single-digit ms, no connections | Low ms, needs pooling or RDS Proxy | Low ms warm, ~15 s from zero |
| Fits a spoken answer's few seconds | Yes | Yes, if always on | Only if never at zero |
| Idle cost | $0 | Instance runs all the time | $0 at zero, else minimum capacity |
| Networking | IAM only, no VPC | VPC, security groups | Data API avoids most VPC work |
| Joins and ad-hoc SQL | No | Yes | Yes |
| Change events | Streams → Lambda | Build it yourself | Build it yourself |

The data is relational in shape, but small: 150 crew, 39 pairings, one operating week. The
rules engine loads what it needs with a few key lookups and evaluates in memory, so joins are
not needed at query time. Streams give the event-driven disruption analysis for free.

Traded away: ad-hoc SQL. Every access pattern is designed up front.

Not chosen: Aurora DSQL (no foreign keys, new), DocumentDB (VPC and a running instance),
Neptune (overkill), ElastiCache or MemoryDB (caches, not a system of record).

## D3. S3 Vectors with Titan Text Embeddings V2

Semantic search covers two things: finding a rule from a paraphrased question, and matching an
unusual question to a known intent. Exact lookups by crew, pairing or rule id stay in DynamoDB.

| Option | Idle cost | Verdict |
|---|---|---|
| S3 Vectors | Cents | Chosen |
| OpenSearch Serverless | High minimum | Too expensive idle |
| Aurora + pgvector | See D2 | Only if Aurora held everything |

Embeddings are 512-dimensional: enough for short rule texts and questions, at half the storage
of 1024.

Search is hybrid: S3 Vectors provides semantic similarity, and BM25 keyword scoring runs in
Python over the same documents (each index is under a hundred documents, so a query sees all
of them). Keywords catch exact terms such as rule ids and flight numbers that embeddings blur;
embeddings catch paraphrases that share no words. The scenario index returns only the kind of
disruption, never a past answer, so stale crew or costs can never leak into a live answer.

## D4. No Redis and no semantic answer cache

A cache would need a VPC and NAT for no latency gain, since DynamoDB already answers in
milliseconds and model calls take seconds. A semantic answer cache is dangerous here:
"C-1042 sick on P-2291" and "C-1024 sick on P-2219" embed almost identically, so a cached
answer could send the wrong person to the wrong aircraft. If caching is added, it will be
Bedrock prompt caching of the fixed prompt and tool definitions, never of answers.

## D5. AgentCore Runtime for the agent and MCP server

AgentCore Runtime hosts MCP servers over Streamable HTTP, validates Cognito tokens, and bills
only for active compute. Memory and Observability come with it. Lambda runs the short,
event-triggered jobs: the SQS worker, the roster loader and the disruption analysis.

The MCP server is a FastMCP server (the official MCP Python SDK) in stateless streamable
HTTP mode, deployed as an AgentCore code package rather than a container, so no Docker is
needed. AgentCore's JWT authorizer admits only the team pool's access tokens; the server
verifies the token again and acts as that user.

The advisor's tool loop is a short Converse loop in this repository rather than an agent
framework. Every tool call it makes goes through the caller's role checks, the round limit
and a time check before each model call, and its answer through the verifier.

Fallback: the MCP server is stateless between requests, so it can move to Lambda behind a
Function URL without code changes if AgentCore blocks progress.

## D6. Models: Amazon Nova, chosen by evaluation

The rules engine does the hard reasoning; the model only chooses tools and phrases answers,
and the verifier rejects anything it did not get from a tool. That makes a small, fast model
enough. Amazon Nova 2 Lite runs the advisor loop and the explainer; Amazon Nova Micro handles
triage. Both are called through Bedrock's model-neutral Converse API, so every model is a
setting, not code. Nova Micro runs in the deployment region; Nova 2 Lite is only offered
through Bedrock's global cross-region profile.

Traded away: some fluency. A smaller model chooses tools less reliably, so more answers
fall back to the verified template wording. That is safe by construction, and the evaluation
set measures how often it happens. Larger models or fine-tuning can be tried later by
changing configuration and re-running the evaluation.

## D7. Most answers need no model call to route

Ordered regex rules route the common question shapes with zero model calls, and an embedding
match catches paraphrases. The triage model is reached only when both abstain. This cuts
latency on the voice path and makes routing testable.

## D8. A deterministic verifier between the advisor and the user

Every id, number, name and rule verdict in a draft must appear in a tool result from the same
turn. A failing draft is discarded and a deterministic template is spoken instead. The
explainer's rewrite is verified again. Guardrails cannot do this job: they do not know what a
sourced number is.

## D9. Next.js web app as the main channel

The web app (Next.js, TypeScript, Tailwind, a handful of its own components rather than a
component library, hosted on Amplify) gives the assistant with voice in and out, the
controller and approver console, an admin page and a mobile crew view. It is a backend for
frontend: apart from the live-events socket, the browser talks only to the app's server
routes, which call the MCP server as the signed-in user, so the web app holds no rule of its
own and never holds the Qloo key. A standard MCP host proves the server follows the spec.

## D10. Real-time through events, not polling

Reports go to SQS (with a dead-letter queue), a worker stores them, and DynamoDB Streams wake
the disruption analysis. AppSync Events pushes updates to the console over WebSockets. SNS is
used only for optional email alerts that the admin assigns to roles; nothing depends on them.
Kinesis is unnecessary at this volume. One notifier on the stream feeds both, so whatever
stores a change (the worker, the analysis, a plan action) is reported the same way.

Conversation memory is deliberately narrow: AgentCore Memory keeps each conversation's
previous turn, and only a short reply or a pronoun may borrow from it, with a note on the
answer. Long-term extraction is not used: a remembered "fact" about a roster goes stale
within hours, and pending work is always read from the table instead.

## D11. Agents recommend; people decide, with four eyes

No agent can change the roster. A controller submits one plan, a different person with the
approver role approves it, and only approval commits every assignment in one DynamoDB
transaction. Legality is re-checked at approval, because the roster may have changed while the
plan waited. Admins configure the system but cannot operate it unless they also hold an
operational role. All of this is enforced in code in the MCP server, never by a prompt.

Traded away: speed on routine cover. One extra human step is accepted because a crew change
moves a real person and is costly to undo. An admin-set auto-approval threshold for low-cost
reserve callouts is a possible later addition, not part of the first build.

## D12. Infrastructure as code from the first AWS resource

Every AWS resource is defined in a Python CDK app from the commit that first needs it, and
deployed as it is built. Problems with a service surface the day it is added, not in the last
week. CDK's high-level constructs cover DynamoDB, SQS with dead-letter queues, SNS, Lambda
event sources, Cognito, AppSync Events and AgentCore; S3 Vectors and Bedrock Guardrails use
the lower-level CloudFormation constructs.

## D13. One region, and names no other deployment uses

Everything deploys to `us-east-1` by default, where every service the system uses is
available: DynamoDB, SQS, SNS, Lambda, S3 Vectors, AgentCore and Bedrock with Nova and Titan.
Model IDs were chosen so they also work unchanged in other regions. Every resource name is
`groundtime-<stage>-...` and every stack `Groundtime-<stage>-...`, derived in one place
(`crewops.config`), so a stage can share an account with anything else and never touch it.

## D14. Tools answer or ask; they never guess

Every tool resolves what the user named against the real data. An id that does not exist is
an error listing the nearest real ids, never a silent correction: C-1042 and C-1024 differ by
one transposed digit, and acting on the wrong one sends a different person to an aircraft. A
name or flight number with several matches is a question naming them. Who may call which
tool is decided in code from the caller's verified roles, and the model is only shown the
tools its caller may use.

Traded away: a turn or two of back-and-forth when the user was vague. A wrong confident
answer costs far more than one clarifying question.

## D15. Qloo for taste; the engine for everything that must be true

Recommending somewhere to eat is where a model on its own is at its worst: it names places
that sound right, some closed, some never there, with no idea of opening hours, dietary
options or how loud a room is. Qloo knows the places and what people who love what this crew
loves think of them. So Qloo ranks, and fixed rules decide: open for the whole meal in the
window the roster gives, every dietary need met, quiet after a long day, within reach. The
model never picks a place, and a brief needs no model at all.

Qloo is called over its REST API from the server, not through the `qloo` command-line
harness: AgentCore and Lambda run code packages, not a Node.js process per request, and the
API needs only the standard library. The allow-list guard, bounded retries and a day's cache
in DynamoDB keep the event quota and personal data safe.

Not chosen: sending crew names or ids for Qloo to profile. Qloo results describe aggregate
affinities, and a crew member's picks are mixed with their colleagues' before they are sent.


## D16. Passengers first: Groundtime plans the wait a disruption creates

A disruption is handled twice. The roster is repaired, and people are left waiting:
passengers on the delayed flight, connecting passengers, the crew. Airlines are good at the
first and leave the second to a meal voucher. Taste is what the second needs, so that is where
Qloo goes: every Groundtime plan is Qloo's picks for this traveller, checked here. Crew control
stays as the backbone. It is where a delay is reported once and becomes true for every plan,
and what keeps the crew's side legal.

Where a traveller is decides what may be planned, before taste does. Past security they stay
in the terminal, however long the delay: Indian airports don't let screened passengers walk
back out. The plan says so rather than offering an outing they can't take.

Not chosen: a model that plans the afternoon from the delay alone. It would name a fort
without knowing it shuts at five, and a beach without counting the ride back. The concierge's
model may only word what the tools returned, and an answer naming anything else is replaced
by the plan itself.
