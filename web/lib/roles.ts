// Which views a signed-in person sees. The MCP server enforces every rule; this only
// decides what to show.

export type Role = "traveller" | "crew" | "customer_care" | "admin";

export type Me = { user_id: string; roles: Role[]; crew_id: string | null; traveller_id: string | null };

export type View = { href: string; label: string; hint: string };

const ALL: Record<string, View> = {
  trip: { href: "/trip", label: "My trip", hint: "Your wait, planned" },
  crew: { href: "/crew", label: "Crew", hint: "My flights and my layover" },
  care: { href: "/care", label: "Customer care", hint: "Delays and every waiting passenger's plan" },
  admin: { href: "/admin", label: "Admin", hint: "Accounts and passwords" },
};

export function viewsFor(roles: Role[]): View[] {
  const has = (role: Role) => roles.includes(role);
  const views: View[] = [];
  if (has("traveller")) views.push(ALL.trip);
  if (has("crew")) views.push(ALL.crew);
  if (has("admin")) views.push(ALL.admin);
  if (has("customer_care")) views.push(ALL.care);
  return views;
}

export function homeFor(roles: Role[]): string {
  return viewsFor(roles)[0]?.href ?? "/login";
}
