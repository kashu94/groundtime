// The MCP tools the web app may call on a user's behalf. The server decides what each user
// may actually do; this list only keeps the proxy from being a door to anything else.
// `list` marks the tools whose result is a list (crewops.mcp.client.LIST_TOOLS).

export const TOOLS = {
  whoami: { list: false, write: false },
  stations: { list: true, write: false },
  find_flights: { list: true, write: false },
  taste_options: { list: false, write: false },
  book_trip: { list: false, write: true },
  my_trip: { list: false, write: false },
  set_position: { list: false, write: true },
  my_groundtime: { list: false, write: false },
  ask: { list: false, write: false },
  my_taste: { list: false, write: false },
  save_my_taste: { list: false, write: true },
  taste_search: { list: true, write: false },
  my_flights: { list: false, write: false },
  my_layover: { list: false, write: false },
  flight_board: { list: true, write: false },
  record_delay: { list: false, write: true },
  delayed_flights: { list: true, write: false },
  flight_care: { list: false, write: false },
  team_accounts: { list: true, write: false },
  reset_password: { list: false, write: true },
} as const;

export type ToolName = keyof typeof TOOLS;

export function isTool(name: string): name is ToolName {
  return Object.prototype.hasOwnProperty.call(TOOLS, name);
}

/** A state-changing request must come from this site: browsers send Origin on POST. Behind a
 * proxy the site's host is the first `x-forwarded-host` entry (a chain of proxies lists
 * several) or `host`, either of which may carry the default port. A cross-site page can set
 * neither, so accepting either match lets no other site in. */
export function sameOrigin(request: Request): boolean {
  const origin = request.headers.get("origin");
  if (!origin) return false;
  let site: URL;
  try {
    site = new URL(origin);
  } catch {
    return false;
  }
  const forwarded = request.headers.get("x-forwarded-host")?.split(",")[0]?.trim();
  return [forwarded, request.headers.get("host")].some((host) => {
    if (!host) return false;
    try {
      return new URL(`${site.protocol}//${host}`).host === site.host;
    } catch {
      return false;
    }
  });
}
