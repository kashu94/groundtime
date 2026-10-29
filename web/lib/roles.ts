// Which views a signed-in person sees. The MCP server enforces every rule; this only
// decides what to show.

export type Role =
  | "crew"
  | "reporter"
  | "controller"
  | "approver"
  | "auditor"
  | "admin"
  | "super_admin"
  | "speaker"
  | "traveller"
  | "customer_care";

export type Me = { user_id: string; roles: Role[]; crew_id: string | null; desk: string | null };

export type View = { href: string; label: string; hint: string };

const ALL: Record<string, View> = {
  trip: { href: "/trip", label: "My trip", hint: "Your wait, planned" },
  care: { href: "/care", label: "Customer care", hint: "Delayed flights and every passenger's plan" },
  console: { href: "/console", label: "Controller", hint: "Disruptions, assistant, options" },
  disruptions: { href: "/disruptions", label: "Disruptions", hint: "Every disruption, by desk and state" },
  operations: { href: "/operations", label: "Operations", hint: "The week's flights, crew and who is out" },
  report: { href: "/report", label: "Report", hint: "Record a disruption" },
  approvals: { href: "/approvals", label: "Approver", hint: "Plans waiting for your approval" },
  crew: { href: "/crew", label: "Crew", hint: "My duty, my flights, report unavailable" },
  admin: { href: "/admin", label: "Admin", hint: "Revoke reports, passwords, thresholds, alerts" },
  assistant: { href: "/assistant", label: "Assistant", hint: "Talk to Groundtime" },
};

export function viewsFor(roles: Role[]): View[] {
  const has = (...r: Role[]) => roles.some((role) => r.includes(role));
  const views: View[] = [];
  // A passenger sees their own trip and the concierge, nothing of the operation.
  if (has("traveller")) return [ALL.trip, ALL.assistant];
  // Admins look after the system and the team, not the cover: no controller console for them.
  if (has("controller", "auditor")) views.push(ALL.console);
  if (has("controller", "approver", "auditor", "admin", "super_admin")) views.push(ALL.disruptions);
  if (has("approver", "auditor")) views.push(ALL.approvals);
  if (has("customer_care", "controller", "approver", "auditor", "admin", "super_admin")) views.push(ALL.care);
  if (has("reporter")) views.push(ALL.operations, ALL.report);
  if (has("crew")) views.push(ALL.crew);
  if (has("admin", "super_admin")) views.push(ALL.admin);
  views.push(ALL.assistant);
  return views;
}

export function homeFor(roles: Role[]): string {
  if (roles.includes("traveller")) return "/trip";
  if (roles.includes("crew")) return "/crew";
  if (roles.includes("reporter") && !roles.some((r) => ["controller", "approver"].includes(r))) return "/operations";
  if (roles.includes("approver")) return "/approvals";
  if (roles.some((r) => ["controller", "auditor"].includes(r))) return "/console";
  if (roles.some((r) => ["admin", "super_admin"].includes(r))) return "/admin";
  if (roles.includes("customer_care")) return "/care";
  return "/assistant";
}
