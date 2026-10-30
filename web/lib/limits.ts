// Request limits for the server routes. Next applies no body-size limit to route handlers,
// so each route refuses an oversized request from its declared length before reading it.

export function declaredTooLarge(request: Request, maxBytes: number): boolean {
  const length = Number(request.headers.get("content-length") ?? "0");
  return !Number.isFinite(length) || length > maxBytes;
}
