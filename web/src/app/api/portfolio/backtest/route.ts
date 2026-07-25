import { proxyPost } from "@/lib/proxy";

/** Backtest an optimizer portfolio (arbitrary weight map). */
export async function POST(request: Request) {
  return proxyPost("/api/portfolio/backtest", await request.json());
}
