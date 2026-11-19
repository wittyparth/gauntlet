"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { ErrorState } from "@/components/shared/error-state";
import { LoadingCard } from "@/components/shared/loading";
import { useAgentList } from "@/lib/api/hooks/read";

/** No agents: onboarding. Otherwise the agent list. */
export default function HomePage() {
  const router = useRouter();
  const agents = useAgentList();
  useEffect(() => {
    if (agents.data) router.replace(agents.data.items.length === 0 ? "/onboarding" : "/agents");
  }, [agents.data, router]);
  return (
    <div className="p-4">
      <h1 className="sr-only">Gauntlet</h1>
      {agents.error ? <ErrorState error={agents.error} onRetry={() => agents.refetch()} /> : <LoadingCard />}
    </div>
  );
}
