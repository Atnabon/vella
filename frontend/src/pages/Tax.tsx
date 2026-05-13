import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type TaxEstimate } from "../lib/api";
import EmptyState from "../components/ui/EmptyState";
import { Calculator, Zap } from "lucide-react";

const ORG_ID = "demo-org";
const STATES = ["CA", "NY", "TX", "FL", "WA", "IL", "PA", "OH", "GA", "NC", "NJ", "VA", "MA", "CO", "OR", "default"];

export default function Tax() {
  const qc = useQueryClient();
  const [form, setForm] = useState({
    tax_year: 2026,
    quarter: "" as string | number,
    entity_type: "llc",
    state: "default",
    filing_status: "single",
  });

  const { data, isLoading } = useQuery({
    queryKey: ["tax-estimates"],
    queryFn: () => api.get(`/tax/estimates?org_id=${ORG_ID}&tax_year=2026`).then(r => r.data),
  });

  const estimateMutation = useMutation({
    mutationFn: () =>
      api.post("/tax/estimate", {
        org_id: ORG_ID,
        ...form,
        quarter: form.quarter === "" ? null : Number(form.quarter),
      }).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tax-estimates"] }),
  });

  const estimates: TaxEstimate[] = data?.estimates ?? [];
  const result = estimateMutation.data;

  return (
    <div className="p-6 space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-slate-100">Tax Estimates</h1>
        <p className="mt-0.5 text-sm text-slate-500">2026 federal + state + self-employment</p>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        {/* Form */}
        <div className="card space-y-4">
          <h2 className="text-sm font-semibold text-slate-300">Compute Estimate</h2>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs text-slate-500">Tax Year</label>
              <input className="input" type="number" value={form.tax_year}
                onChange={e => setForm(f => ({ ...f, tax_year: Number(e.target.value) }))} />
            </div>
            <div>
              <label className="mb-1 block text-xs text-slate-500">Quarter (blank = annual)</label>
              <select className="input" value={form.quarter}
                onChange={e => setForm(f => ({ ...f, quarter: e.target.value }))}>
                <option value="">Annual</option>
                <option value="1">Q1</option>
                <option value="2">Q2</option>
                <option value="3">Q3</option>
                <option value="4">Q4</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs text-slate-500">Entity Type</label>
              <select className="input" value={form.entity_type}
                onChange={e => setForm(f => ({ ...f, entity_type: e.target.value }))}>
                <option value="llc">LLC</option>
                <option value="sole_prop">Sole Proprietorship</option>
                <option value="s_corp">S-Corp</option>
                <option value="c_corp">C-Corp</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs text-slate-500">State</label>
              <select className="input" value={form.state}
                onChange={e => setForm(f => ({ ...f, state: e.target.value }))}>
                {STATES.map(s => <option key={s} value={s}>{s === "default" ? "Other" : s}</option>)}
              </select>
            </div>
            <div className="col-span-2">
              <label className="mb-1 block text-xs text-slate-500">Filing Status</label>
              <select className="input" value={form.filing_status}
                onChange={e => setForm(f => ({ ...f, filing_status: e.target.value }))}>
                <option value="single">Single</option>
                <option value="married_filing_jointly">Married Filing Jointly</option>
                <option value="head_of_household">Head of Household</option>
              </select>
            </div>
          </div>
          <button className="btn-primary w-full justify-center" onClick={() => estimateMutation.mutate()}
            disabled={estimateMutation.isPending}>
            <Zap className="h-4 w-4" />
            {estimateMutation.isPending ? "Computing…" : "Compute Estimate"}
          </button>
        </div>

        {/* Result */}
        {result && (
          <div className="card space-y-3">
            <h2 className="text-sm font-semibold text-slate-300">
              {result.tax_year} {result.quarter ? `Q${result.quarter}` : "Annual"} Estimate
            </h2>
            <div className="space-y-2 text-sm">
              {[
                ["Gross Revenue", result.gross_revenue],
                ["Total Expenses", result.total_expenses],
                ["Taxable Income", result.taxable_income],
              ].map(([label, val]) => (
                <div key={label as string} className="flex justify-between text-slate-400">
                  <span>{label}</span>
                  <span className="font-mono">${Number(val).toLocaleString("en-US", { minimumFractionDigits: 2 })}</span>
                </div>
              ))}
              <div className="my-2 border-t border-slate-800" />
              {[
                ["Federal Tax", result.federal_tax, "text-slate-300"],
                ["State Tax", result.state_tax, "text-slate-300"],
                ["Self-Employment Tax", result.self_employment_tax, "text-slate-300"],
              ].map(([label, val, cls]) => (
                <div key={label as string} className="flex justify-between">
                  <span className="text-slate-400">{label}</span>
                  <span className={`font-mono ${cls}`}>
                    ${Number(val).toLocaleString("en-US", { minimumFractionDigits: 2 })}
                  </span>
                </div>
              ))}
              <div className="mt-3 flex justify-between rounded-lg bg-sky-500/10 px-3 py-2">
                <span className="font-semibold text-sky-400">Total Estimated Tax</span>
                <span className="font-mono font-bold text-sky-400">
                  ${Number(result.total_estimated_tax).toLocaleString("en-US", { minimumFractionDigits: 2 })}
                </span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* History */}
      <div className="card p-0 overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-800">
          <h2 className="text-sm font-semibold text-slate-300">Estimate History</h2>
        </div>
        {isLoading ? (
          <div className="py-8 text-center text-sm text-slate-600">Loading…</div>
        ) : estimates.length === 0 ? (
          <EmptyState icon={Calculator} title="No estimates yet" />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-800">
                {["Year", "Period", "Revenue", "Expenses", "Taxable", "Total Tax"].map(h => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {estimates.map(e => (
                <tr key={e.id} className="table-row-hover">
                  <td className="px-4 py-3 text-slate-200">{e.tax_year}</td>
                  <td className="px-4 py-3 text-slate-400">{e.quarter ? `Q${e.quarter}` : "Annual"}</td>
                  <td className="px-4 py-3 font-mono text-xs">${Number(e.gross_revenue).toLocaleString()}</td>
                  <td className="px-4 py-3 font-mono text-xs">${Number(e.total_expenses).toLocaleString()}</td>
                  <td className="px-4 py-3 font-mono text-xs">${Number(e.taxable_income).toLocaleString()}</td>
                  <td className="px-4 py-3 font-mono text-xs font-semibold text-sky-400">
                    ${Number(e.total_estimated_tax).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
