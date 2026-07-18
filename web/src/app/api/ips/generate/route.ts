import { proxyPost } from "@/lib/proxy";

/** Start an IPS generation task (returns 202 + task_id). */
export async function POST(request: Request) {
  return proxyPost("/api/ips/generate", await request.json());
}
