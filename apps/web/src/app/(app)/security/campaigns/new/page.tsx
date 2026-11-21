"use client";

import { CampaignForm } from "@/components/security/campaign-form";
import { KillSwitchCard } from "@/components/security/kill-switch-card";
import { OwnershipCard } from "@/components/security/ownership-card";
import { PageHeader } from "@/components/shared/page-header";

export default function NewCampaignPage() {
  return (
    <>
      <PageHeader
        title="Launch campaign"
        breadcrumbs={[{ label: "Security", href: "/security" }, { label: "New campaign" }]}
      />
      <div className="grid items-start gap-6 p-4 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <CampaignForm />
        <aside className="flex flex-col gap-3" aria-label="Safety state">
          <KillSwitchCard />
          <OwnershipCard />
        </aside>
      </div>
    </>
  );
}
