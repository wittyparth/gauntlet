"use client";

import { Toast } from "@animate-ui/react/primitives/base-ui/toast";
import type { ReactNode } from "react";

function ToastList() {
  const { toasts } = Toast.useToastManager();
  return toasts.map((toast) => (
    <Toast.Root
      key={toast.id}
      toast={toast}
      className="data-[type=error]:border-destructive/60 absolute right-0 bottom-0 w-80 rounded-lg border bg-popover p-3 text-popover-foreground shadow-lg"
    >
      <Toast.Content>
        <Toast.Title className="text-sm font-medium" />
        <Toast.Description className="text-muted-foreground mt-0.5 text-xs" />
        <Toast.Close
          aria-label="Dismiss"
          className="text-muted-foreground hover:text-foreground absolute top-2 right-2 text-base leading-none"
        >
          ×
        </Toast.Close>
      </Toast.Content>
    </Toast.Root>
  ));
}

export function Toaster({ children }: { children: ReactNode }) {
  return (
    <Toast.Provider>
      {children}
      <Toast.Portal>
        <Toast.Viewport className="fixed right-4 bottom-4 z-[100] h-16 w-80">
          <ToastList />
        </Toast.Viewport>
      </Toast.Portal>
    </Toast.Provider>
  );
}

export { useToast } from "./use-toast";
