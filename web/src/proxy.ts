import { hasSameOrigin } from "@/lib/request-origin";
import { NextRequest, NextResponse } from "next/server";
import { dictionaries } from "@/lib/i18n/dictionaries";
import { DEFAULT_LOCALE, LOCALE_COOKIE, isLocale } from "@/lib/i18n/locale";

export function proxy(request: NextRequest) {
  if (!["GET", "HEAD", "OPTIONS"].includes(request.method) && !hasSameOrigin(request)) {
    const value = request.cookies.get(LOCALE_COOKIE)?.value;
    const t = dictionaries[isLocale(value) ? value : DEFAULT_LOCALE];
    return NextResponse.json({ detail: t.auth.failed }, { status: 403, headers: { "Cache-Control": "no-store" } });
  }
  const response = NextResponse.next();
  response.headers.set("Cache-Control", "no-store");
  return response;
}
export const config = { matcher: "/api/:path*" };
