/**
 * Client-side SSE consumption helpers (fetch + ReadableStream; EventSource
 * can't POST). Shared by the advisor and IPS workspaces.
 */

/** Parse one SSE block ("data: {json}") into an event object, or null. */
export function parseSseBlock(block: string): Record<string, unknown> | null {
  for (const line of block.split("\n")) {
    if (line.startsWith("data: ")) {
      try {
        return JSON.parse(line.slice(6));
      } catch {
        return null;
      }
    }
  }
  return null;
}

/** Read an SSE body to completion, dispatching each parsed event. */
export async function readSseStream(
  body: ReadableStream<Uint8Array>,
  onEvent: (event: Record<string, unknown>) => void
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";
    for (const block of blocks) {
      const event = parseSseBlock(block);
      if (event) onEvent(event);
    }
  }
}
