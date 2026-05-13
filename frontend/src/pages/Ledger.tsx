import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { api, type EventStream } from "../lib/api";
import EmptyState from "../components/ui/EmptyState";
import { BookOpen, ShieldCheck, Package, ChevronDown, ChevronRight } from "lucide-react";
import { formatDistanceToNow } from "date-fns";

const ORG_ID = "demo-org";

export default function Ledger() {
  const [expanded, setExpanded] = useState<string | null>(null);
  const [streamFilter, setStreamFilter] = useState("");
  const [auditStreamId, setAuditStreamId] = useState("");

  const { data: streamsData, isLoading } = useQuery({
    queryKey: ["streams"],
    queryFn: () => api.get(`/ledger/streams?org_id=${ORG_ID}&limit=50`).then(r => r.data),
  });

  const { data: eventsData } = useQuery({
    queryKey: ["stream-events", expanded],
    queryFn: () => api.get(`/ledger/streams/${expanded}/events`).then(r => r.data),
    enabled: !!expanded,
  });

  const { data: verifyData, refetch: refetchVerify } = useQuery({
    queryKey: ["verify", expanded],
    queryFn: () => api.get(`/ledger/streams/${expanded}/verify`).then(r => r.data),
    enabled: false,
  });

  const auditMutation = useMutation({
    mutationFn: () =>
      api.post(`/ledger/audit-package?org_id=${ORG_ID}&stream_id=${auditStreamId}`).then(r => r.data),
  });

  const streams: EventStream[] = streamsData?.streams ?? [];
  const filtered = streamFilter
    ? streams.filter(s => s.stream_id.includes(streamFilter))
    : streams;

  return (
    <div className="p-6 space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-slate-100">Audit Ledger</h1>
        <p className="mt-0.5 text-sm text-slate-500">Event-sourced, hash-chained, tamper-evident</p>
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        {/* Stream list */}
        <div className="lg:col-span-2 space-y-3">
          <div className="flex items-center gap-3">
            <input className="input" placeholder="Filter streams…" value={streamFilter}
              onChange={e => setStreamFilter(e.target.value)} />
          </div>

          <div className="card p-0 overflow-hidden">
            {isLoading ? (
              <div className="py-8 text-center text-sm text-slate-600">Loading…</div>
            ) : filtered.length === 0 ? (
              <EmptyState icon={BookOpen} title="No event streams" description="Events will appear as documents are processed." />
            ) : (
              <div className="divide-y divide-slate-800">
                {filtered.map(stream => {
                  const isOpen = expanded === stream.stream_id;
                  return (
                    <div key={stream.stream_id}>
                      <button
                        className="w-full px-4 py-3 flex items-center gap-3 text-left hover:bg-slate-800/50 transition-colors"
                        onClick={() => setExpanded(isOpen ? null : stream.stream_id)}
                      >
                        {isOpen ? (
                          <ChevronDown className="h-4 w-4 text-slate-500 flex-shrink-0" />
                        ) : (
                          <ChevronRight className="h-4 w-4 text-slate-500 flex-shrink-0" />
                        )}
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-mono text-slate-200 truncate">{stream.stream_id}</p>
                          <p className="text-xs text-slate-500 mt-0.5">
                            {stream.aggregate_type} · v{stream.current_version} ·{" "}
                            {formatDistanceToNow(new Date(stream.created_at), { addSuffix: true })}
                          </p>
                        </div>
                        <span className="badge-slate ml-2">{stream.current_version} events</span>
                      </button>
                      {isOpen && eventsData && (
                        <div className="bg-slate-950 border-t border-slate-800 px-4 py-3 space-y-2">
                          <div className="flex items-center justify-between mb-2">
                            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                              Events ({eventsData.event_count})
                            </p>
                            <button
                              className="btn-ghost text-xs py-1"
                              onClick={() => refetchVerify()}
                            >
                              <ShieldCheck className="h-3.5 w-3.5" /> Verify Chain
                            </button>
                          </div>
                          {verifyData && (
                            <div className={`rounded-lg border px-3 py-2 text-xs mb-2 ${
                              verifyData.integrity === "ok"
                                ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-400"
                                : "border-red-500/20 bg-red-500/10 text-red-400"
                            }`}>
                              Chain integrity: {verifyData.integrity} · {verifyData.events_checked} events checked
                            </div>
                          )}
                          {eventsData.events.map((ev: { position: number; type: string; recorded_at: string; payload: Record<string, unknown> }) => (
                            <div key={ev.position} className="rounded-lg bg-slate-900 px-3 py-2">
                              <div className="flex items-center gap-2">
                                <span className="badge-blue text-xs">#{ev.position}</span>
                                <span className="text-xs font-semibold text-slate-300">{ev.type}</span>
                                <span className="ml-auto text-xs text-slate-600">
                                  {formatDistanceToNow(new Date(ev.recorded_at), { addSuffix: true })}
                                </span>
                              </div>
                              <pre className="mt-1.5 text-xs text-slate-500 overflow-x-auto whitespace-pre-wrap break-all">
                                {JSON.stringify(ev.payload, null, 2)}
                              </pre>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Audit package */}
        <div className="space-y-4">
          <div className="card space-y-3">
            <div className="flex items-center gap-2">
              <Package className="h-4 w-4 text-sky-400" />
              <h2 className="text-sm font-semibold text-slate-300">Generate Audit Package</h2>
            </div>
            <p className="text-xs text-slate-500">
              Produces a self-contained examination package with hash chain verification,
              lifecycle narrative, and source document provenance.
            </p>
            <div>
              <label className="mb-1 block text-xs text-slate-500">Stream ID</label>
              <input className="input" placeholder="e.g. invoice-demo-org-abc123"
                value={auditStreamId} onChange={e => setAuditStreamId(e.target.value)} />
            </div>
            <button
              className="btn-primary w-full justify-center"
              onClick={() => auditMutation.mutate()}
              disabled={!auditStreamId || auditMutation.isPending}
            >
              <Package className="h-4 w-4" />
              {auditMutation.isPending ? "Generating…" : "Generate Package"}
            </button>
            {auditMutation.isSuccess && (
              <div className="rounded-lg bg-emerald-500/10 border border-emerald-500/20 p-3 text-xs space-y-1">
                <p className="font-semibold text-emerald-400">{auditMutation.data?.package_id}</p>
                <p className="text-slate-400">
                  {auditMutation.data?.event_count} events ·
                  Chain: {auditMutation.data?.hash_chain?.integrity}
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
