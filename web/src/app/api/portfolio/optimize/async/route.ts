import { proxyPost } from "@/lib/proxy";

/** Create an async optimization task (202 + task_id). */
export async function POST(request: Request) {
  const body = await request.json();
  return proxyPost("/api/portfolio/optimize/async", body);
}
