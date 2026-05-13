import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type Reconciliation } from "../lib/api";
import EmptyState from "../components/ui/EmptyState";
import { ArrowLeftRight, Play } from "lucide-react";

const ORG_ID = "demo-org";

export default function ReconciliationPage() {
  const qc = useQueryClient();
  const [form, setForm] = useState({
    account_name: "Checking",
    period_start: "2026-01-01",
    period_end: "2026-03-31",
  });

  const { data, isLoading } = useQuery({
    queryKey: ["reconciliations"],
    queryFn: () => api.get(`/reconciliation/?org_id=${ORG_ID}`).then(r => r.data),
  });

  const runMutation = useMutation({
    mutationFn: () =>
      api.post("/reconciliation/run", { org_id: ORG_ID, ...form }).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["reconciliations"] }),
  });

  const recons: Reconciliation[] = data?.reconciliations ?? [];

  return (
    <div className="p-6 space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-slate-100">Bank Reconciliation</h1>
        <p className="mt-0.5 text-sm text-slate-500">Match bank transactions to invoices</p>
      </div>

      {/* Run form */}
      <div className="card space-y-4">
        <h2 className="text-sm font-semibold text-slate-300">Run New Reconciliation</h2>
        <div className="grid grid-cols-3 gap-3">
          <div>
            <label className="mb-1 block text-xs text-slate-500">Account</label>
            <input className="input" value={form.account_name}
              onChange={e => setForm(f => ({ ...f, account_name: e.target.value }))} />
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-500">Period Start</label>
            <input className="input" type="date" value={form.period_start}
              onChange={e => setForm(f => ({ ...f, period_start: e.target.value }))} />
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-500">Period End</label>
            <input className="input" type="date" value={form.period_end}
              onChange={e => setForm(f => ({ ...f, period_end: e.target.value }))} />
          </div>
        </div>
        <button className="btn-primary" onClick={() => runMutation.mutate()} disabled={runMutation.isPending}>
          <Play className="h-4 w-4" />
          {runMutation.isPending ? "Running…" : "Run Reconciliation"}
        </button>
        {runMutation.isSuccess && (
          <div className="rounded-lg bg-emerald-500/10 border border-emerald-500/20 p-4 text-sm">
            <p className="font-semibold text-emerald-400">Reconciliation complete</p>
            <p className="mt-1 text-slate-400">
              Matched: {runMutation.data?.matched} · Unmatched: {runMutation.data?.unmatched} ·
              Net difference: ${runMutation.data?.net_difference?.toFixed(2)}
            </p>
          </div>
        )}
      </div>

      {/* History */}
      <div className="card p-0 overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-800">
          <h2 className="text-sm font-semibold text-slate-300">History</h2>
        </div>
        {isLoading ? (
          <div className="py-8 text-center text-sm text-slate-600">Loading…</div>
        ) : recons.length === 0 ? (
          <EmptyState icon={ArrowLeftRight} title="No reconciliations yet" />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-800">
                {["Account", "Period", "Matched", "Unmatched", "Difference", "Status"].map(h => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {recons.map(r => (
                <tr key={r.id} className="table-row-hover">
                  <td className="px-4 py-3 font-medium text-slate-200">{r.account_name}</td>
                  <td className="px-4 py-3 text-xs text-slate-400">{r.period_start} → {r.period_end}</td>
                  <td className="px-4 py-3 text-emerald-400">{r.matched_count}</td>
                  <td className="px-4 py-3 text-amber-400">{r.unmatched_count}</td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-300">
                    ${Number(r.difference).toFixed(2)}
                  </td>
                  <td className="px-4 py-3">
                    <span className={r.status === "completed" ? "badge-green" : "badge-yellow"}>
                      {r.status}
                    </span>
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
