/** Next normalizes loopback URL hostnames; Host retains the browser's authority. */
export function hasSameOrigin(request: Request): boolean {
  const url = new URL(request.url);
  const host = request.headers.get("host") ?? url.host;
  return request.headers.get("origin") === `${url.protocol}//${host}`;
}
