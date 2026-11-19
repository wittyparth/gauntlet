"use client";

import type { ReactNode } from "react";
import { useDefaultLayout } from "react-resizable-panels";

import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";

/** Two panes; sizes persist per `id`. */
export function SplitPane({
  id,
  left,
  right,
  defaultLeft = 60,
}: {
  id: string;
  left: ReactNode;
  right: ReactNode;
  defaultLeft?: number;
}) {
  const layout = useDefaultLayout({ id, storage: typeof window === "undefined" ? undefined : window.localStorage });
  return (
    <ResizablePanelGroup
      orientation="horizontal"
      id={id}
      defaultLayout={layout.defaultLayout}
      onLayoutChanged={layout.onLayoutChanged}
      className="min-h-0 flex-1"
    >
      <ResizablePanel id="left" defaultSize={`${defaultLeft}%`} minSize="35%" className="min-w-0">
        {left}
      </ResizablePanel>
      <ResizableHandle withHandle />
      <ResizablePanel id="right" defaultSize={`${100 - defaultLeft}%`} minSize="35%" className="min-w-0">
        {right}
      </ResizablePanel>
    </ResizablePanelGroup>
  );
}
