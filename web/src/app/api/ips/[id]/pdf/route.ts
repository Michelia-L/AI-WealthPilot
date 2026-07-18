import { proxyFile } from "@/lib/proxy";

type Params = { params: Promise<{ id: string }> };

/** Download one IPS document as a PDF (binary passthrough). */
export async function GET(_request: Request, { params }: Params) {
  const { id } = await params;
  return proxyFile(`/api/ips/${encodeURIComponent(id)}/pdf`);
}
