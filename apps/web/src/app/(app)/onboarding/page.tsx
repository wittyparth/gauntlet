"use client";

import { Suspense } from "react";

import { Wizard } from "@/components/onboarding/wizard";
import { PageHeader } from "@/components/shared/page-header";

export default function OnboardingPage() {
  return (
    <>
      <PageHeader title="Set up your first agent" breadcrumbs={[{ label: "Agents", href: "/agents" }, { label: "Set up" }]} />
      <div className="p-4">
        <Suspense>
          <Wizard />
        </Suspense>
      </div>
    </>
  );
}
