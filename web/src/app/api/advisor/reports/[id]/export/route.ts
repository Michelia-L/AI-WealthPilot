import { proxyFile } from "@/lib/proxy";

type Params = { params: Promise<{ id: string }> };

/** Download one advisor report in the given export format (passthrough). */
export async function GET(request: Request, { params }: Params) {
  const { id } = await params;
  const format =
    new URL(request.url).searchParams.get("format") ?? "html";
  return proxyFile(
    `/api/advisor/reports/${encodeURIComponent(id)}/export?format=${encodeURIComponent(format)}`
  );
}
