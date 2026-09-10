import { proxyPost } from "@/lib/proxy";

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return proxyPost(`/api/monitoring/${encodeURIComponent(id)}/holdings`, await request.json());
}
