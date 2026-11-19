import { z } from "zod";

import { dollarsToMicros } from "@/lib/format";

export const runStepSchema = z.object({
  suite_id: z.string().min(1, "Choose a suite."),
  repetitions: z.number().int("Use a whole number.").min(1, "At least 1.").max(50),
  budget_dollars: z.number().positive("Enter a budget above $0.").max(10_000),
});
export type RunStep = z.infer<typeof runStepSchema>;

/** Dollars from the form become integer micro-dollars before sending. */
export const budgetMicros = (dollars: number) => dollarsToMicros(dollars);
