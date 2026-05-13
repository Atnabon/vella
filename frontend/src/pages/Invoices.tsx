import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type Invoice } from "../lib/api";
import EmptyState from "../components/ui/EmptyState";
import { FileText, Upload, CheckCircle, Clock } from "lucide-react";

const ORG_ID = "demo-org";

function statusBadge(inv: Invoice) {
  if (inv.booked) return <span className="badge-green">Booked</span>;
  if (inv.confidence_score < 0.7) return <span className="badge-red">Review</span>;
  return <span className="badge-yellow">Pending</span>;
}

export default function Invoices() {
  const qc = useQueryClient();
  const [filter, setFilter] = useState<"all" | "booked" | "pending">("all");

  const { data, isLoading } = useQuery({
    queryKey: ["invoices", filter],
    queryFn: () => {
      const params = new URLSearchParams({ org_id: ORG_ID, limit: "100" });
      if (filter === "booked") params.set("booked", "true");
      if (filter === "pending") params.set("booked", "false");
      return api.get(`/invoices/?${params}`).then(r => r.data);
    },
  });

  const bookMutation = useMutation({
    mutationFn: (invoiceId: string) =>
      api.post(`/invoices/${invoiceId}/book`, { booked_by: "human" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["invoices"] }),
  });

  const invoices: Invoice[] = data?.invoices ?? [];

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Invoices</h1>
          <p className="mt-0.5 text-sm text-slate-500">{data?.total ?? 0} total</p>
        </div>
        <a href="/documents" className="btn-primary">
          <Upload className="h-4 w-4" /> Upload
        </a>
      </div>

      {/* Filters */}
      <div className="flex gap-2">
        {(["all", "booked", "pending"] as const).map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
              filter === f
                ? "bg-sky-500/20 text-sky-400"
                : "text-slate-500 hover:bg-slate-800 hover:text-slate-300"
            }`}
          >
            {f.charAt(0).toUpperCase() + f.slice(1)}
          </button>
        ))}
      </div>

      <div className="card p-0 overflow-hidden">
        {isLoading ? (
          <div className="py-12 text-center text-sm text-slate-600">Loading…</div>
        ) : invoices.length === 0 ? (
          <EmptyState icon={FileText} title="No invoices yet" description="Upload a PDF invoice to get started." />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-800">
                <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wide">Vendor</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wide">Invoice #</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-slate-500 uppercase tracking-wide">Amount</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wide">GL Account</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-slate-500 uppercase tracking-wide">Confidence</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-slate-500 uppercase tracking-wide">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {invoices.map((inv) => (
                <tr key={inv.invoice_id} className="table-row-hover">
                  <td className="px-4 py-3 font-medium text-slate-200">{inv.vendor_name || "—"}</td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-400">{inv.invoice_number || "—"}</td>
                  <td className="px-4 py-3 text-right font-semibold text-slate-100">
                    ${Number(inv.total_amount).toLocaleString("en-US", { minimumFractionDigits: 2 })}
                  </td>
                  <td className="px-4 py-3 text-slate-400 text-xs">{inv.gl_account || "—"}</td>
                  <td className="px-4 py-3 text-center">
                    <span className={`font-mono text-xs ${inv.confidence_score >= 0.9 ? "text-emerald-400" : inv.confidence_score >= 0.7 ? "text-amber-400" : "text-red-400"}`}>
                      {(inv.confidence_score * 100).toFixed(0)}%
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center">{statusBadge(inv)}</td>
                  <td className="px-4 py-3 text-right">
                    {!inv.booked && (
                      <button
                        className="btn-ghost text-xs py-1"
                        onClick={() => bookMutation.mutate(inv.invoice_id)}
                        disabled={bookMutation.isPending}
                      >
                        <CheckCircle className="h-3.5 w-3.5" /> Book
                      </button>
                    )}
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
