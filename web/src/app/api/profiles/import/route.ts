import { proxyPost } from "@/lib/proxy";

/** Import legacy data/profiles/*.json into SQLite (idempotent). */
export async function POST() {
  return proxyPost("/api/profiles/import", {});
}
