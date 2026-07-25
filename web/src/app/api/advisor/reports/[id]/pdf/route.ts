import { proxyFile } from "@/lib/proxy";

type Params = { params: Promise<{ id: string }> };

/** Download one advisor report as a PDF (binary passthrough). */
export async function GET(_request: Request, { params }: Params) {
  const { id } = await params;
  return proxyFile(`/api/advisor/reports/${encodeURIComponent(id)}/pdf`);
}
