"use client";

import { Toast } from "@animate-ui/react/primitives/base-ui/toast";

import { toApiError } from "@/lib/api/errors";

/** Toast helpers: errors show the API `message`. */
export function useToast() {
  const manager = Toast.useToastManager();
  return {
    success: (title: string, description?: string) =>
      manager.add({ title, description, type: "success" }),
    error: (e: unknown, title = "Something went wrong") =>
      manager.add({ title, description: toApiError(e).message, type: "error" }),
    /** Run a mutation promise with loading / success / error toasts. */
    promise: <T,>(p: Promise<T>, msgs: { loading: string; success: string; error?: string }) =>
      manager.promise(p, {
        loading: msgs.loading,
        success: msgs.success,
        error: (e: unknown) => ({
          title: msgs.error ?? "Something went wrong",
          description: toApiError(e).message,
        }),
      }),
  };
}
