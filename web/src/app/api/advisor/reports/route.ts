import { proxyPost } from "@/lib/proxy";

/** Save a generated advisory report to the library. */
export async function POST(request: Request) {
  return proxyPost("/api/advisor/reports", await request.json());
}
