import { describe, expect, it } from "vitest";

import { findQuote } from "./quote-match";

const slice = (text: string, quote: string | null | undefined) => {
  const m = findQuote(text, quote);
  return m ? text.slice(m.start, m.end) : null;
};

describe("findQuote", () => {
  it("finds an exact hit", () => {
    expect(findQuote("I cancelled order ord_6 for you.", "cancelled order")).toEqual({ start: 2, end: 17 });
  });
  it("ignores case and whitespace differences", () => {
    expect(slice("Sure,   let me\ncheck THAT now", "let me check that")).toBe("let me\ncheck THAT");
  });
  it("treats curly and straight quotes alike", () => {
    expect(slice("I’ve issued a “full” refund", "I've issued a \"full\" refund")).toBe(
      "I’ve issued a “full” refund",
    );
  });
  it("maps offsets back through multiple spaces and newlines", () => {
    const text = "a  b\n\n  c  d";
    expect(slice(text, "c d")).toBe("c  d");
    expect(slice(text, "b c")).toBe("b\n\n  c");
  });
  it("returns null on a miss", () => {
    expect(findQuote("hello there", "goodbye")).toBeNull();
  });
  it("returns null for empty or null quotes", () => {
    expect(findQuote("hello", null)).toBeNull();
    expect(findQuote("hello", undefined)).toBeNull();
    expect(findQuote("hello", "   ")).toBeNull();
    expect(findQuote("hello", "")).toBeNull();
  });
});
