import { z } from "zod";

export const createBatchSchema = z.object({
  batch_name: z.string().min(3, "At least 3 characters").max(100, "100 characters max"),
  date_deployed: z.string().optional(),
  certificate_number: z.string().optional(),
  duration_days: z.number().int().positive("Must be positive").optional(),
});

export const patchBatchSchema = z.object({
  is_transferred: z.boolean().optional(),
  is_active: z.boolean().optional(),
  date_deployed: z.string().optional(),
  deployment_confirmed: z.boolean().optional(),
  stage: z.number().int().min(1).max(4).optional(),
});

export type CreateBatchFormData = z.infer<typeof createBatchSchema>;
export type PatchBatchFormData = z.infer<typeof patchBatchSchema>;
