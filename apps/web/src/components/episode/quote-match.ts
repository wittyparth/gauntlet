const CURLY: Record<string, string> = {
  "‘": "'",
  "’": "'",
  "“": '"',
  "”": '"',
};

type Normalized = { text: string; map: number[] };

/** Lower-case, collapse whitespace runs to one space, curly quotes to straight (contract D4).
 * `map[i]` is the offset in the original string of normalised char `i`. */
export function normalize(input: string): Normalized {
  let text = "";
  const map: number[] = [];
  for (let i = 0; i < input.length; i++) {
    const ch = CURLY[input[i]] ?? input[i];
    if (/\s/.test(ch)) {
      if (text.length > 0 && !text.endsWith(" ")) {
        text += " ";
        map.push(i);
      }
      continue;
    }
    for (const c of ch.toLowerCase()) {
      text += c;
      map.push(i);
    }
  }
  return { text, map };
}

/** Where `quote` sits in `text`, as offsets into the original `text`; null on a miss. */
export function findQuote(
  text: string,
  quote: string | null | undefined,
): { start: number; end: number } | null {
  if (!quote) return null;
  const q = normalize(quote).text.trim();
  if (!q) return null;
  const hay = normalize(text);
  const at = hay.text.indexOf(q);
  if (at < 0) return null;
  const last = at + q.length - 1;
  return { start: hay.map[at], end: hay.map[last] + 1 };
}
