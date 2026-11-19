"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export const hashFor = (seq: number) => `#e-${seq}`;

export function parseHash(hash: string): number | null {
  const m = /^#e-(\d+)$/.exec(hash);
  return m ? Number(m[1]) : null;
}

export type Selection = { seq: number | null; quote: string | null; nonce: number };

/**
 * One selected event seq and an optional evidence quote, mirrored in the URL hash (`#e-12`).
 * `select` updates the hash, state and scrolls `#e-<seq>` into view. A seq that does not exist
 * (`knownSeqs`) is ignored, so a bad hash never errors.
 */
export function useEventSelection(knownSeqs: readonly number[], opts: { ensureVisible?: (seq: number) => void } = {}) {
  const [sel, setSel] = useState<Selection>({ seq: null, quote: null, nonce: 0 });
  const initial = useRef<number | null | undefined>(undefined);
  const known = new Set(knownSeqs);
  const ensureRef = useRef(opts.ensureVisible);
  ensureRef.current = opts.ensureVisible;

  const select = useCallback(
    (seq: number, quote?: string | null) => {
      if (!knownSeqs.includes(seq)) return;
      ensureRef.current?.(seq);
      window.history.replaceState(null, "", hashFor(seq));
      setSel((s) => ({ seq, quote: quote ?? null, nonce: s.nonce + 1 }));
    },
    [knownSeqs],
  );

  const clear = useCallback(() => {
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
    setSel((s) => ({ seq: null, quote: null, nonce: s.nonce + 1 }));
  }, []);

  // Restore from the hash once events are known.
  useEffect(() => {
    if (initial.current === undefined) initial.current = parseHash(window.location.hash);
    const want = initial.current;
    if (want != null && known.has(want)) {
      initial.current = null;
      ensureRef.current?.(want);
      setSel((s) => ({ seq: want, quote: null, nonce: s.nonce + 1 }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [knownSeqs.length]);

  // Scroll after the render that follows a selection (the row may have just appeared).
  useEffect(() => {
    if (sel.seq == null) return;
    const el = document.getElementById(`e-${sel.seq}`);
    if (!el) return;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    el.scrollIntoView({ block: "center", behavior: reduce ? "auto" : "smooth" });
  }, [sel.nonce, sel.seq]);

  return { selectedSeq: sel.seq, quote: sel.quote, select, clear };
}
