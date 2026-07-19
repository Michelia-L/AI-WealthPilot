import { proxyStreamGet } from "@/lib/proxy";

type Params = { params: Promise<{ id: string }> };

/** SSE progress feed for an optimization task. */
export async function GET(_request: Request, { params }: Params) {
  const { id } = await params;
  return proxyStreamGet(`/api/portfolio/tasks/${id}/events`);
}
