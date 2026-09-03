import { proxyPost } from "@/lib/proxy";

/** Upload browser-picked profile JSON files (raw text) for server validation. */
export async function POST(req: Request) {
  return proxyPost("/api/profiles/import/upload", await req.json());
}
