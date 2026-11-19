import { cookies, headers } from "next/headers";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";

import { AppShell } from "@/components/shared/app-shell";

export default async function AppLayout({ children }: { children: ReactNode }) {
  const jar = await cookies();
  if (!jar.get("gauntlet_key")) {
    const h = await headers();
    const path = h.get("x-pathname") ?? "/";
    redirect(`/login?next=${encodeURIComponent(path)}`);
  }
  const defaultOpen = jar.get("sidebar_state")?.value !== "false";
  return <AppShell defaultOpen={defaultOpen}>{children}</AppShell>;
}
