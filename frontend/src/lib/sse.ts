export interface SseEvent {
  event: string;
  data: any; // eslint-disable-line @typescript-eslint/no-explicit-any
}

/** Splits an SSE text buffer into complete events; returns [events, remaining buffer]. */
export function parseSseBuffer(buffer: string): [SseEvent[], string] {
  const events: SseEvent[] = [];
  const blocks = buffer.replace(/\r\n/g, "\n").split("\n\n");
  const rest = blocks.pop() ?? "";
  for (const block of blocks) {
    let event = "message";
    const data: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    }
    if (data.length) {
      try {
        events.push({ event, data: JSON.parse(data.join("\n")) });
      } catch {
        /* ignore malformed event */
      }
    }
  }
  return [events, rest];
}

/** POSTs JSON and yields SSE events as they arrive (fetch streaming, works with cookies). */
export async function* postSse(path: string, body: unknown, signal?: AbortSignal): AsyncGenerator<SseEvent> {
  const res = await fetch(`/api${path}`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    const err = await res.json().catch(() => null);
    if (res.status === 401) window.dispatchEvent(new Event("briha:logged-out"));
    yield { event: "error", data: err?.error ?? { code: "INTERNAL", message: "Something went wrong." } };
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const [events, rest] = parseSseBuffer(buffer);
    buffer = rest;
    for (const e of events) yield e;
  }
  const [events] = parseSseBuffer(buffer + "\n\n");
  for (const e of events) yield e;
}
