import { proxyDelete, proxyGet } from "@/lib/proxy";

type Params = { params: Promise<{ id: string }> };

/** View one stored report (full Markdown content). */
export async function GET(_request: Request, { params }: Params) {
  const { id } = await params;
  return proxyGet(`/api/advisor/reports/${id}`);
}

/** Delete a stored report. */
export async function DELETE(_request: Request, { params }: Params) {
  const { id } = await params;
  return proxyDelete(`/api/advisor/reports/${id}`);
}
