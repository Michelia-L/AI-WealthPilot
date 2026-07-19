import { proxyFile } from "@/lib/proxy";

type Params = { params: Promise<{ id: string }> };

/** Download one IPS document as Markdown (passthrough). */
export async function GET(_request: Request, { params }: Params) {
  const { id } = await params;
  return proxyFile(`/api/ips/${encodeURIComponent(id)}/export`);
}
