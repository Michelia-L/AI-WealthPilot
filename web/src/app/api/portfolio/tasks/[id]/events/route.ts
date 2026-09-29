import { proxyStreamGet } from "@/lib/proxy";

type Params = { params: Promise<{ id: string }> };

/** SSE progress feed for an optimization task. */
export async function GET(request: Request, { params }: Params) {
  const { id } = await params;
  const query = new URLSearchParams();
  const contextId = new URL(request.url).searchParams.get("context_profile_id");
  if (contextId !== null) query.set("context_profile_id", contextId);
  return proxyStreamGet(`/api/portfolio/tasks/${id}/events?${query}`);
}
