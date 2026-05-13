import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type ReviewItem } from "../lib/api";
import EmptyState from "../components/ui/EmptyState";
import { Clock, CheckCircle, XCircle, AlertTriangle } from "lucide-react";
import { formatDistanceToNow } from "date-fns";

const ORG_ID = "demo-org";

function slaColor(deadline: string) {
  const hours = (new Date(deadline).getTime() - Date.now()) / 3_600_000;
  if (hours < 0) return "text-red-400";
  if (hours < 1) return "text-red-400";
  if (hours < 2) return "text-amber-400";
  return "text-slate-400";
}

export default function ReviewQueue() {
  const qc = useQueryClient();
  const [status, setStatus] = useState<"pending" | "approved" | "rejected">("pending");

  const { data, isLoading } = useQuery({
    queryKey: ["review-queue", status],
    queryFn: () =>
      api.get(`/ledger/review-queue?org_id=${ORG_ID}&status=${status}&limit=50`).then(r => r.data),
    refetchInterval: status === "pending" ? 15_000 : false,
  });

  const decideMutation = useMutation({
    mutationFn: ({ id, decision }: { id: number; decision: "approved" | "rejected" }) =>
      api.post(`/ledger/review-queue/${id}/decide`, { decision, reviewer_id: "human-dashboard" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["review-queue"] }),
  });

  const items: ReviewItem[] = data?.items ?? [];

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Review Queue</h1>
          <p className="mt-0.5 text-sm text-slate-500">Human-in-the-loop approval · {data?.total ?? 0} items</p>
        </div>
        {status === "pending" && data?.total > 0 && (
          <div className="flex items-center gap-2 rounded-lg bg-amber-500/10 border border-amber-500/20 px-3 py-1.5">
            <AlertTriangle className="h-4 w-4 text-amber-400" />
            <span className="text-sm text-amber-400 font-medium">{data.total} pending</span>
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 rounded-lg bg-slate-900 border border-slate-800 p-1 w-fit">
        {(["pending", "approved", "rejected"] as const).map(s => (
          <button
            key={s}
            onClick={() => setStatus(s)}
            className={`rounded-md px-4 py-1.5 text-xs font-medium transition-colors ${
              status === s ? "bg-slate-700 text-slate-100" : "text-slate-500 hover:text-slate-300"
            }`}
          >
            {s.charAt(0).toUpperCase() + s.slice(1)}
          </button>
        ))}
      </div>

      <div className="space-y-3">
        {isLoading ? (
          <div className="card py-12 text-center text-sm text-slate-600">Loading…</div>
        ) : items.length === 0 ? (
          <div className="card">
            <EmptyState icon={Clock} title={`No ${status} items`}
              description={status === "pending" ? "All caught up! No items need review." : undefined} />
          </div>
        ) : (
          items.map(item => (
            <div key={item.id} className="card flex items-start gap-4">
              <div className="mt-0.5 rounded-lg bg-amber-500/10 p-2">
                <AlertTriangle className="h-4 w-4 text-amber-400" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-semibold text-slate-200">
                    {item.review_type.replace(/_/g, " ")}
                  </span>
                  <span className="badge-slate">#{item.id}</span>
                  <span className={`text-xs font-mono ${
                    item.confidence_score >= 0.7 ? "text-amber-400" : "text-red-400"
                  }`}>
                    {(item.confidence_score * 100).toFixed(0)}% confidence
                  </span>
                </div>
                <p className="mt-1 text-sm text-slate-400">{item.reason}</p>
                <div className="mt-2 flex items-center gap-4 text-xs">
                  <span className="text-slate-600">org: {item.org_id}</span>
                  {item.sla_deadline && (
                    <span className={slaColor(item.sla_deadline)}>
                      SLA: {formatDistanceToNow(new Date(item.sla_deadline), { addSuffix: true })}
                    </span>
                  )}
                </div>
              </div>
              {status === "pending" && (
                <div className="flex gap-2 flex-shrink-0">
                  <button
                    className="btn-ghost text-emerald-400 hover:bg-emerald-500/10 text-xs py-1"
                    onClick={() => decideMutation.mutate({ id: item.id, decision: "approved" })}
                    disabled={decideMutation.isPending}
                  >
                    <CheckCircle className="h-4 w-4" /> Approve
                  </button>
                  <button
                    className="btn-danger text-xs py-1"
                    onClick={() => decideMutation.mutate({ id: item.id, decision: "rejected" })}
                    disabled={decideMutation.isPending}
                  >
                    <XCircle className="h-4 w-4" /> Reject
                  </button>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
