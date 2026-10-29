import { describe, expect, it } from "vitest";

import { homeFor, viewsFor } from "@/lib/roles";
import { claimsOf, expiresSoon } from "@/lib/tokens";
import { isTool, sameOrigin } from "@/lib/tools";
import { invocationUrl } from "@/lib/config";

function jwt(claims: object) {
  const part = (o: object) => Buffer.from(JSON.stringify(o)).toString("base64url");
  return `${part({ alg: "none" })}.${part(claims)}.sig`;
}

describe("tokens", () => {
  it("reads claims and expiry without trusting them for anything else", () => {
    const token = jwt({ username: "rohit", exp: 1000, "cognito:groups": ["controller"] });
    expect(claimsOf(token)?.username).toBe("rohit");
    expect(expiresSoon(token, 900)).toBe(false);
    expect(expiresSoon(token, 950)).toBe(true); // within the 60 s margin
    expect(expiresSoon(undefined, 0)).toBe(true);
    expect(claimsOf("garbage")).toBeNull();
  });
});

describe("roles and views", () => {
  it("sends each role to its home", () => {
    expect(homeFor(["crew"])).toBe("/crew");
    expect(homeFor(["approver"])).toBe("/approvals");
    expect(homeFor(["controller"])).toBe("/console");
    expect(homeFor(["admin"])).toBe("/admin");
    expect(homeFor(["reporter"])).toBe("/operations");
    expect(homeFor(["traveller"])).toBe("/trip");
    expect(homeFor(["customer_care"])).toBe("/care");
  });

  it("shows only the views a role uses", () => {
    expect(viewsFor(["crew"]).map((v) => v.href)).toEqual(["/crew", "/assistant"]);
    expect(viewsFor(["controller"]).map((v) => v.href)).toEqual(["/console", "/disruptions", "/care", "/assistant"]);
    expect(viewsFor(["approver"]).map((v) => v.href)).toEqual(["/disruptions", "/approvals", "/care", "/assistant"]);
    expect(viewsFor(["admin"]).map((v) => v.href)).toEqual(["/disruptions", "/care", "/admin", "/assistant"]);
    expect(viewsFor(["reporter"]).map((v) => v.href)).toEqual(["/operations", "/report", "/assistant"]);
    expect(viewsFor(["customer_care"]).map((v) => v.href)).toEqual(["/care", "/assistant"]);
  });

  it("shows a traveller only their trip and the assistant", () => {
    expect(viewsFor(["traveller"]).map((v) => v.href)).toEqual(["/trip", "/assistant"]);
    expect(viewsFor(["traveller"])[0]).toMatchObject({ label: "My trip", hint: "Your wait, planned" });
  });
});

describe("the tool proxy", () => {
  it("forwards only known tools", () => {
    expect(isTool("approve_plan")).toBe(true);
    expect(isTool("crew_tool")).toBe(true); // role-checked dispatch on the server
    expect(isTool("my_groundtime")).toBe(true);
    expect(isTool("flight_care")).toBe(true);
    expect(isTool("list_crew_tools")).toBe(false);
    expect(isTool("__proto__")).toBe(false);
    expect(isTool("constructor")).toBe(false);
  });

  it("accepts state-changing requests only from this site", () => {
    const req = (origin: string | null, host = "localhost:3000") =>
      new Request("http://localhost:3000/api/tools/ask", {
        method: "POST",
        headers: { ...(origin ? { origin } : {}), host },
      });
    expect(sameOrigin(req("http://localhost:3000"))).toBe(true);
    expect(sameOrigin(req("https://evil.example"))).toBe(false);
    expect(sameOrigin(req(null))).toBe(false);
    expect(sameOrigin(req("null"))).toBe(false);
  });

  it("knows its own site behind proxies, and still nobody else's", () => {
    const req = (origin: string, headers: Record<string, string>) =>
      new Request("http://internal/api/tools/ask", { method: "POST", headers: { origin, ...headers } });
    const site = "https://crewops.example";
    // a chain of proxies lists every host it passed; the first is the one the browser used
    expect(sameOrigin(req(site, { "x-forwarded-host": "crewops.example, internal:3000", host: "internal:3000" }))).toBe(
      true,
    );
    // a proxy that forwards its own name but keeps the browser's Host
    expect(sameOrigin(req(site, { "x-forwarded-host": "internal:3000", host: "crewops.example" }))).toBe(true);
    // the default port spelled out
    expect(sameOrigin(req(site, { "x-forwarded-host": "crewops.example:443", host: "internal:3000" }))).toBe(true);
    expect(
      sameOrigin(req("https://evil.example", { "x-forwarded-host": "crewops.example", host: "crewops.example" })),
    ).toBe(false);
    expect(sameOrigin(req(site, { "x-forwarded-host": "crewops.example:8443", host: "internal:3000" }))).toBe(false);
  });

  it("encodes the runtime ARN in the invocation URL", () => {
    expect(invocationUrl("us-east-1", "arn:aws:bedrock-agentcore:us-east-1:111111111111:runtime/x")).toBe(
      "https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/" +
        "arn%3Aaws%3Abedrock-agentcore%3Aus-east-1%3A111111111111%3Aruntime%2Fx/invocations?qualifier=DEFAULT",
    );
  });
});
