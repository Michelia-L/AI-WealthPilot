import { proxyPost } from "@/lib/proxy";

export async function POST(request: Request) {
  return proxyPost("/api/retirement/simulate", await request.json());
}
