import Link from "next/link";
import type { ReactNode } from "react";

/** Frame for the public pages (arena, benchmarks): no sign-in, no sidebar. */
export function PublicShell({ title, intro, children }: { title: string; intro?: string; children: ReactNode }) {
  return (
    <div className="mx-auto flex min-h-screen w-full max-w-6xl flex-col gap-6 p-4 sm:p-6">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b pb-3">
        <Link href="/" className="font-semibold">
          Gauntlet
        </Link>
        <nav aria-label="Public pages" className="text-muted-foreground flex gap-4 text-sm">
          <Link href="/arena" className="hover:text-foreground">Arena</Link>
          <Link href="/benchmarks" className="hover:text-foreground">Benchmarks</Link>
        </nav>
      </header>
      <main className="flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <h1 className="text-xl font-semibold">{title}</h1>
          {intro ? <p className="text-muted-foreground max-w-prose text-sm">{intro}</p> : null}
        </div>
        {children}
      </main>
    </div>
  );
}
