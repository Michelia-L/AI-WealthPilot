import { proxyGet } from "@/lib/proxy";

export async function GET(request: Request) {
  // Forward the query string (?profile_id=) untouched.
  return proxyGet(`/api/retirement/cme-suggestion${new URL(request.url).search}`);
}
