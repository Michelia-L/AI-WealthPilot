import { proxyDelete, proxyGet } from "@/lib/proxy";

type Params = { params: Promise<{ id: string }> };

/** Fetch one IPS document rendered as Markdown. */
export async function GET(_request: Request, { params }: Params) {
  const { id } = await params;
  return proxyGet(`/api/ips/${encodeURIComponent(id)}`);
}

/** Delete the stored IPS source artifact. */
export async function DELETE(_request: Request, { params }: Params) {
  const { id } = await params;
  return proxyDelete(`/api/ips/${encodeURIComponent(id)}`);
}
