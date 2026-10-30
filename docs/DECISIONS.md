# Decisions

Short records of the choices that shape this project and what was traded away.

## D1. Plan the wait a delay creates, for the people in it

Airlines handle a delay operationally and leave the people waiting with an SMS and a meal
voucher. Every one of them has hours they didn't plan for, and what would make those hours
good is different for each: a beach, a quiet café, a film that ends before the gate. That is
a taste problem, so that is where Qloo goes: every Groundtime plan is Qloo's picks for this
traveller, checked here.

Traded away: crew scheduling, re-rostering and approvals. Groundtime takes the delay as given
(customer care records it as operations confirm it) and plans around it; it doesn't try to
repair the operation.

## D2. Qloo chooses; the engine decides what is true

Recommending where to go is where a model on its own is at its worst: it names places that
sound right, some closed, some never there, with no idea of opening hours, dietary options,
or how long the ride back takes. Qloo knows the places, and what people who love what this
traveller loves think of them. So Qloo ranks, and fixed rules decide: open for the whole
visit, every dietary need met, a real sight rather than a hotel tagged as one, back in time
for the gate. The model never picks a place, and a plan needs no model at all.

Qloo is called over its REST API from the server: AgentCore runs code packages, and the API
needs only the standard library. An allow-list guard, bounded retries and a day's cache in
DynamoDB keep the quota and personal data safe.

Not chosen: sending names or ids for Qloo to profile. Qloo receives only the ids of the
things a person loves.

## D3. Where you are decides the plan, before taste does

Someone already at the airport is never sent out of it: once inside the departure terminal,
Indian airports only let a passenger back out with the airline's and security's clearance,
and a connecting passenger stays airside. Only someone who hasn't left for the airport yet
gets an outing, and it is near the airport, on their way in, ending at the terminal in time.
The plan says which case it is in plain words, so it never reads as "walk out of the
terminal".

The network is domestic India, so no visa rule applies. An international transit would add
one more check before any outing.

Traded away: an outing for someone at the terminal before security with hours to spare. It
is sometimes possible with clearance, but a plan that depends on a guard's discretion isn't a
plan.

## D4. Taste is asked for at booking, and saved only when the booking is

A traveller says what they love when they book: a short list of artists, films, series and
books to tap (each looked up in Qloo's catalogue, so what is saved is Qloo's id), a search for
anything else, and what they can eat. The trip and the taste are saved together when they
confirm, and not before. When a delay comes, the plan is already personal; nobody is asked a
questionnaire at the gate.

Traded away: guessing taste from booking history. It would need data an airline holds and a
hackathon doesn't, and it would be less honest than asking.

## D5. The concierge is an agent, and is checked like one

A traveller can ask in their own words. Amazon Nova chooses which tools to call (the wait, the
plan, where they are, something to watch, Qloo's catalogue) and words the answer. Every
capitalised name in the answer must appear in what the tools returned; one that doesn't means
the model made it up, and the traveller gets the checked plan written out instead. The
answer is never worse than the plan.

Nova 2 Lite through Bedrock's Converse API: small and fast is enough when the engine has done
the reasoning, and the model is a setting, not code.

## D6. One MCP server for every capability

Everything a person can do is an MCP tool on one server, hosted on AgentCore Runtime
(stateless streamable HTTP, Cognito's JWT authorizer in front, billed only while a session
runs). The web app is one MCP host; any other host can use the same tools, with the same role
checks, because they live in the server and nowhere else.

Fallback: the server is stateless between requests, so it can move to Lambda behind a Function
URL without code changes.

## D7. DynamoDB for what changes; the network in memory

What changes at run time (accounts, bookings, taste, delays, Qloo's cached answers) is a few
hundred items in one on-demand DynamoDB table: no idle cost, no VPC, millisecond reads.
The airline network doesn't change at run time, so it ships with the server and is held in
memory, repeated weekly from the seed week to the end of the year.

Traded away: editing the schedule without a deploy. In production the schedule would come
from the airline's systems instead.

## D8. Next.js as a backend for frontend

The browser talks only to the web app's server routes, which call the MCP server as the
signed-in user. The app holds no role rule of its own and never the Qloo key, and needs no AWS
credentials: sign-in is Cognito's public API and every call carries the user's token.

## D9. Infrastructure as code, in one region, under one prefix

Three CDK stacks in Python (Data, Auth, Mcp). Everything deploys to `ap-southeast-2` (Sydney)
by default, the region the target account's organization allows, with every service used:
DynamoDB, Cognito, AgentCore, Bedrock with Nova 2 Lite (the `global.` profile) and Parameter
Store. Region and model are settings, so another region is a change to `.env`. Every resource
is `groundtime-<stage>-...` and every stack `Groundtime-<stage>-...`, derived in one place
(`crewops.config`), so a stage can share an account with anything else and never touch it.
