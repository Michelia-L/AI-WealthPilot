/**
 * Typed client for the AI WealthPilot FastAPI backend.
 *
 * Server Components call the API over the internal network (API_ORIGIN),
 * so requests never cross the browser and no CORS is involved. Local dev
 * defaults to localhost:8000; Docker Compose injects http://api:8000.
 *
 * Responses are NOT cached here — freshness is owned by the API layer
 * (TTL caches + the CME file cache). Slow sections stream via <Suspense>.
 *
 * Implementation is split per domain under ./api/; this barrel re-exports
 * everything so existing `@/lib/api` import sites stay unchanged.
 */
export * from "./api/market";
export * from "./api/portfolio";
export * from "./api/retirement";
export * from "./api/profiles";
export * from "./api/advisor";
export * from "./api/settings";
export * from "./api/ips";
export * from "./api/monitoring";
export * from "./api/backtest";
