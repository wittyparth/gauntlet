"use client";

import { ModelsForm } from "@/components/models/models-form";
import { PageHeader } from "@/components/shared/page-header";

export default function ModelsSettingsPage() {
  return (
    <>
      <PageHeader title="Models" breadcrumbs={[{ label: "Settings" }, { label: "Models" }]} />
      <div className="p-4">
        <ModelsForm />
      </div>
    </>
  );
}
