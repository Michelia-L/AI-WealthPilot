import { proxyGet } from "@/lib/proxy";

/** Compare 2–6 profiles (src compare_profiles + behavioral biases). */
export async function GET(request: Request) {
  const ids = new URL(request.url).searchParams.get("ids") ?? "";
  return proxyGet(`/api/profiles/compare?ids=${encodeURIComponent(ids)}`);
}
