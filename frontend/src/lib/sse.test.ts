import { describe, expect, it } from "vitest";
import { guessLanguage } from "./i18n";
import { parseSseBuffer } from "./sse";

describe("parseSseBuffer", () => {
  it("parses complete events and keeps the partial tail", () => {
    const buf =
      'event: meta\ndata: {"run_id": "1"}\n\nevent: delta\ndata: {"text": "Aaj "}\n\nevent: delta\ndata: {"te';
    const [events, rest] = parseSseBuffer(buf);
    expect(events).toEqual([
      { event: "meta", data: { run_id: "1" } },
      { event: "delta", data: { text: "Aaj " } },
    ]);
    expect(rest).toBe('event: delta\ndata: {"te');
  });

  it("handles CRLF and ignores malformed JSON", () => {
    const [events] = parseSseBuffer('event: done\r\ndata: {"status": "answered"}\r\n\r\nevent: x\ndata: {bad\n\n');
    expect(events).toEqual([{ event: "done", data: { status: "answered" } }]);
  });
});

describe("guessLanguage", () => {
  it("detects Roman Urdu vs English", () => {
    expect(guessLanguage("Aaj kitne papers kate?")).toBe("roman_urdu");
    expect(guessLanguage("How many sheets were cut today?")).toBe("english");
  });
});
