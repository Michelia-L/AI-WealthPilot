import { proxyGet } from "@/lib/proxy";

type Params = { params: Promise<{ id: string }> };

/** Fetch one IPS document rendered as Markdown. */
export async function GET(_request: Request, { params }: Params) {
  const { id } = await params;
  return proxyGet(`/api/ips/${id}`);
}
