import { proxyPost } from "@/lib/proxy";

/** Fetch the model list from a user-supplied OpenAI-compatible endpoint. */
export async function POST(request: Request) {
  return proxyPost("/api/settings/llm/models", await request.json());
}
