import { proxyPost } from "@/lib/proxy";

/** Create a client profile. */
export async function POST(request: Request) {
  return proxyPost("/api/profiles", await request.json());
}
