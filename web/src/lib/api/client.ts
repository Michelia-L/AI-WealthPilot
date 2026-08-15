/**
 * Typed client for the AI WealthPilot FastAPI backend.
 *
 * Server Components call the API over the internal network (API_ORIGIN),
 * so requests never cross the browser and no CORS is involved. Local dev
 * defaults to localhost:8000; Docker Compose injects http://api:8000.
 *
 * Responses are NOT cached here — freshness is owned by the API layer
 * (TTL caches + the CME file cache). Slow sections stream via <Suspense>.
 */

const API_ORIGIN = process.env.API_ORIGIN ?? "http://localhost:8000";

export async function getJson<T>(path: string, locale?: string): Promise<T | null> {
  try {
    // NOTE (P22): this module is in the client bundle too (dashboard-controls /
    // retirement-workspace import runtime constants), so it cannot read the
    // locale cookie via next/headers — RSC callers pass `locale` explicitly.
    const res = await fetch(`${API_ORIGIN}${path}`, {
      cache: "no-store",
      headers: locale ? { "X-Locale": locale } : undefined,
    });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    // API unreachable (not started, network partition) — callers render a
    // degraded panel instead of crashing the page.
    return null;
  }
}

export function tickersParam(tickers: string[]): string {
  return tickers.map(encodeURIComponent).join(",");
}
