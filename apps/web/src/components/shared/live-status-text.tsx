"use client";

import { ShimmeringText } from "@animate-ui/react/primitives/texts/shimmering";

export function LiveStatusText({ text, className }: { text: string; className?: string }) {
  return (
    <span className={className} role="status">
      <ShimmeringText text={text} duration={1.6} />
    </span>
  );
}
