import { proxyStream } from "@/lib/proxy";

/** Stream an advisory report as SSE (token events + terminal done event). */
export async function POST(request: Request) {
  return proxyStream("/api/advisor/report/stream", await request.json());
}
