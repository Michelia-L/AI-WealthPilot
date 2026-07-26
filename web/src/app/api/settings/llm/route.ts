import { proxyGet, proxyPut } from "@/lib/proxy";

/** Current effective LLM settings (api key always masked). */
export async function GET() {
  return proxyGet("/api/settings/llm");
}

/** Save custom endpoint settings (empty api_key reverts to env defaults). */
export async function PUT(request: Request) {
  return proxyPut("/api/settings/llm", await request.json());
}
