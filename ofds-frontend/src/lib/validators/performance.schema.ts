import { z } from "zod";

export const createPerformanceSchema = z.object({
  gross_profit: z.number().min(0, "Gross profit cannot be negative"),
  transaction_costs: z.number().min(0, "Costs cannot be negative"),
  date_closed: z.string().optional(),
  fund_name: z.string().optional(),
});

export const performanceExcelRowSchema = z.object({
  date: z.string().refine((d) => !isNaN(Date.parse(d)), "Invalid date"),
  fund_name: z.string().min(1, "Fund name required"),
  duration: z.number().int().positive("Duration must be positive"),
  performance_percentage: z.number().min(-100).max(1000, "Rate out of range"),
});

export type CreatePerformanceFormData = z.infer<typeof createPerformanceSchema>;
export type PerformanceExcelRow = z.infer<typeof performanceExcelRowSchema>;
