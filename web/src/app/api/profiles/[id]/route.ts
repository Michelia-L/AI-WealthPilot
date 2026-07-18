import { proxyDelete, proxyGet, proxyPut } from "@/lib/proxy";

type Params = { params: Promise<{ id: string }> };

/** Fetch one profile's full detail (edit form prefill). */
export async function GET(_request: Request, { params }: Params) {
  const { id } = await params;
  return proxyGet(`/api/profiles/${id}`);
}

/** Update a client profile. */
export async function PUT(request: Request, { params }: Params) {
  const { id } = await params;
  return proxyPut(`/api/profiles/${id}`, await request.json());
}

/** Delete a client profile. */
export async function DELETE(_request: Request, { params }: Params) {
  const { id } = await params;
  return proxyDelete(`/api/profiles/${id}`);
}
