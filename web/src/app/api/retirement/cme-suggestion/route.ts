import { proxyGet } from "@/lib/proxy";

export async function GET() {
  return proxyGet("/api/retirement/cme-suggestion");
}
