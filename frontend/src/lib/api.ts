import axios from "axios";

export const api = axios.create({ baseURL: "/api/v1", timeout: 30_000 });

export type Invoice = {
  invoice_id: string;
  org_id: string;
  vendor_name: string;
  invoice_number: string;
  total_amount: number;
  currency: string;
  booked: boolean;
  gl_account: string | null;
  payment_status: string;
  confidence_score: number;
  created_at: string;
};

export type BankTransaction = {
  txn_id: string;
  org_id: string;
  account_name: string;
  txn_date: string;
  description: string;
  amount: number;
  txn_type: "debit" | "credit";
  reconciled: boolean;
  matched_invoice_id: string | null;
};

export type Reconciliation = {
  id: number;
  org_id: string;
  account_name: string;
  period_start: string;
  period_end: string;
  matched_count: number;
  unmatched_count: number;
  difference: number;
  status: string;
  completed_at: string;
};

export type TaxEstimate = {
  id: number;
  org_id: string;
  tax_year: number;
  quarter: number | null;
  entity_type: string;
  gross_revenue: number;
  total_expenses: number;
  taxable_income: number;
  federal_tax: number;
  state_tax: number;
  self_employment_tax: number;
  total_estimated_tax: number;
  status: string;
  computed_at: string;
};

export type ReviewItem = {
  id: number;
  org_id: string;
  review_type: string;
  reason: string;
  confidence_score: number;
  status: string;
  sla_deadline: string;
  payload: Record<string, unknown>;
};

export type Document = {
  document_id: string;
  filename: string;
  doc_type: string;
  pages: number;
  confidence: number;
  status: string;
  uploaded_at: string;
};

export type EventStream = {
  stream_id: string;
  aggregate_type: string;
  current_version: number;
  created_at: string;
};
