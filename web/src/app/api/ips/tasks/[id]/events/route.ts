import { proxyStreamGet } from "@/lib/proxy";

type Params = { params: Promise<{ id: string }> };

/** SSE progress feed for one IPS generation task. */
export async function GET(_request: Request, { params }: Params) {
  const { id } = await params;
  return proxyStreamGet(`/api/ips/tasks/${id}/events`);
}
