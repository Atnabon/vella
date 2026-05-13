import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import StatCard from "../components/ui/StatCard";
import {
  FileText, ArrowLeftRight, Calculator, Clock,
  TrendingUp, AlertTriangle,
} from "lucide-react";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";

const ORG_ID = "demo-org";

export default function Overview() {
  const { data: invoices } = useQuery({
    queryKey: ["invoices", "overview"],
    queryFn: () => api.get(`/invoices/?org_id=${ORG_ID}&limit=200`).then(r => r.data),
  });
  const { data: review } = useQuery({
    queryKey: ["review", "pending"],
    queryFn: () => api.get(`/ledger/review-queue?org_id=${ORG_ID}&status=pending`).then(r => r.data),
  });
  const { data: recon } = useQuery({
    queryKey: ["recon", "overview"],
    queryFn: () => api.get(`/reconciliation/?org_id=${ORG_ID}&limit=10`).then(r => r.data),
  });
  const { data: tax } = useQuery({
    queryKey: ["tax", "overview"],
    queryFn: () => api.get(`/tax/estimates?org_id=${ORG_ID}&tax_year=2026`).then(r => r.data),
  });

  const totalInvoiced = invoices?.invoices?.reduce(
    (s: number, i: { total_amount: number }) => s + i.total_amount, 0
  ) ?? 0;
  const bookedCount = invoices?.invoices?.filter((i: { booked: boolean }) => i.booked).length ?? 0;
  const pendingReview = review?.total ?? 0;
  const totalTax = tax?.estimates?.reduce(
    (s: number, e: { total_estimated_tax: number }) => s + e.total_estimated_tax, 0
  ) ?? 0;
  const lastRecon = recon?.reconciliations?.[0];

  const chartData = invoices?.invoices?.slice(0, 12).reverse().map(
    (inv: { vendor_name: string; total_amount: number }, i: number) => ({
      name: `#${i + 1}`,
      amount: inv.total_amount,
    })
  ) ?? [];

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-100">Financial Overview</h1>
        <p className="mt-1 text-sm text-slate-500">Real-time summary · {ORG_ID}</p>
      </div>

      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <StatCard
          label="Total Invoiced"
          value={`$${totalInvoiced.toLocaleString("en-US", { maximumFractionDigits: 0 })}`}
          sub={`${bookedCount} booked`}
          icon={FileText}
          accent="blue"
        />
        <StatCard
          label="Pending Review"
          value={pendingReview}
          sub="items in queue"
          icon={Clock}
          accent={pendingReview > 5 ? "red" : "yellow"}
        />
        <StatCard
          label="Estimated Tax"
          value={`$${totalTax.toLocaleString("en-US", { maximumFractionDigits: 0 })}`}
          sub="2026 YTD"
          icon={Calculator}
          accent="green"
        />
        <StatCard
          label="Last Reconciliation"
          value={lastRecon?.status ?? "—"}
          sub={lastRecon ? `${lastRecon.matched_count} matched` : "No data yet"}
          icon={ArrowLeftRight}
          accent={lastRecon?.status === "completed" ? "green" : "yellow"}
        />
      </div>

      {/* Invoice trend chart */}
      <div className="card">
        <h2 className="mb-4 text-sm font-semibold text-slate-300">Recent Invoice Amounts</h2>
        {chartData.length > 0 ? (
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={chartData}>
              <defs>
                <linearGradient id="g1" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#0ea5e9" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="#0ea5e9" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="name" tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false}
                tickFormatter={(v: number) => `$${(v / 1000).toFixed(0)}k`} />
              <Tooltip
                contentStyle={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: 8 }}
                labelStyle={{ color: "#94a3b8" }}
                formatter={(v: number) => [`$${v.toLocaleString()}`, "Amount"]}
              />
              <Area type="monotone" dataKey="amount" stroke="#0ea5e9" strokeWidth={2} fill="url(#g1)" />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <p className="py-12 text-center text-sm text-slate-600">No invoice data yet</p>
        )}
      </div>

      {/* Latest review items */}
      {pendingReview > 0 && (
        <div className="card border-amber-500/20">
          <div className="mb-3 flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-amber-400" />
            <h2 className="text-sm font-semibold text-slate-300">Action Required</h2>
          </div>
          <p className="text-sm text-slate-400">
            <span className="font-semibold text-amber-400">{pendingReview} items</span> are waiting
            in the review queue. Low-confidence extractions need human approval before booking.
          </p>
          <a href="/review" className="mt-3 inline-block text-sm font-medium text-sky-400 hover:text-sky-300">
            Go to Review Queue →
          </a>
        </div>
      )}
    </div>
  );
}
