import { ArenaPage } from "@/components/arena/arena-page";
import { PublicShell } from "@/components/shared/public-shell";

export const metadata = { title: "Arena | Gauntlet" };

export default function Page() {
  return (
    <PublicShell
      title="Challenge arena"
      intro="Talk Pip, a support agent, into giving up its escalation token or calling a tool it must never use. Five levels, each with more defenses. Everything here is fake data; no accounts, no emails."
    >
      <ArenaPage />
    </PublicShell>
  );
}
