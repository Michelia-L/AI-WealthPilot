import { NextRequest, NextResponse } from "next/server";
import { proxyPost } from "@/lib/proxy";
import { getDict } from "@/lib/i18n/server";

export async function POST(request: NextRequest) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { detail: (await getDict()).clientPortal.assistantFailed },
      { status: 400, headers: { "Cache-Control": "no-store" } },
    );
  }
  return proxyPost("/api/me/assistant", body);
}
