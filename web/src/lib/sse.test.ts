import { describe, expect, it } from "vitest";
import { parseSseBlock, readSseStream } from "./sse";

describe("parseSseBlock", () => {
  it("parses a data line into an event object", () => {
    const event = parseSseBlock('data: {"type":"node","node":"fetch"}');
    expect(event).toEqual({ type: "node", node: "fetch" });
  });

  it("ignores non-data lines and returns the first data payload", () => {
    const event = parseSseBlock('event: message\ndata: {"a":1}\ndata: {"b":2}');
    expect(event).toEqual({ a: 1 });
  });

  it("returns null for malformed JSON and data-less blocks", () => {
    expect(parseSseBlock("data: {oops")).toBeNull();
    expect(parseSseBlock("event: ping")).toBeNull();
    expect(parseSseBlock("")).toBeNull();
  });
});

function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
}

describe("readSseStream", () => {
  it("dispatches every event in order", async () => {
    const events: unknown[] = [];
    await readSseStream(
      streamOf([
        'data: {"type":"node","node":"fetch"}\n\ndata: {"type":"done","result":{}}\n\n',
      ]),
      (e) => events.push(e)
    );
    expect(events).toEqual([
      { type: "node", node: "fetch" },
      { type: "done", result: {} },
    ]);
  });

  it("reassembles blocks split across chunk boundaries", async () => {
    const events: unknown[] = [];
    await readSseStream(
      streamOf(['data: {"type":"no', 'de","node":"solve"}\n\ndata: {"type":"done"', '}\n\n']),
      (e) => events.push(e)
    );
    expect(events).toEqual([
      { type: "node", node: "solve" },
      { type: "done" },
    ]);
  });

  it("skips malformed blocks without aborting the stream", async () => {
    const events: unknown[] = [];
    await readSseStream(
      streamOf(['data: {broken}\n\ndata: {"ok":true}\n\n']),
      (e) => events.push(e)
    );
    expect(events).toEqual([{ ok: true }]);
  });
});
