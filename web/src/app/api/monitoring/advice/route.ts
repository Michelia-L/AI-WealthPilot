import { proxyStream } from "@/lib/proxy";

/** Stream AI rebalancing advice for a monitored IPS document (SSE). */
export async function POST(request: Request) {
  return proxyStream("/api/monitoring/advice", await request.json());
}
