import { z } from "zod";

export const createInvestmentSchema = z.object({
  batch_id: z.number().int().positive(),
  investor_name: z
    .string()
    .min(3)
    .refine((val) => val.trim().split(/\s+/).length >= 2, "Full name required"),
  investor_email: z.string().email(),
  investor_phone: z.string().optional(),
  internal_client_code: z.string().min(1, "Client code is required"),
  amount_deposited: z.number().positive("Amount must be positive"),
  date_deposited: z.string(),
  fund_name: z.string().optional(),
  wealth_manager: z.string().optional(),
  IFA: z.string().optional(),
  contract_note: z.string().optional(),
});

export type CreateInvestmentFormData = z.infer<typeof createInvestmentSchema>;
