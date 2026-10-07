import { z } from "zod";

export const createValuationSchema = z.object({
  fund_id: z.number().int().positive("Fund is required"),
  start_date: z.string().min(1, "Start date is required"),
  end_date: z.string().min(1, "End date is required"),
  performance_rate: z.number().min(-100).max(1000, "Rate out of range"),
  head_office_total: z.number().positive("Head office total is required"),
});

export type CreateValuationFormData = z.infer<typeof createValuationSchema>;
