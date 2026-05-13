import { useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type Document } from "../lib/api";
import EmptyState from "../components/ui/EmptyState";
import { FileText, Upload, CloudUpload } from "lucide-react";

const ORG_ID = "demo-org";

function docTypeBadge(type: string) {
  const map: Record<string, string> = {
    invoice: "badge-blue",
    bank_statement: "badge-green",
    tax_form: "badge-yellow",
    w2: "badge-yellow",
    "1099": "badge-yellow",
    receipt: "badge-slate",
    purchase_order: "badge-blue",
  };
  return <span className={map[type] ?? "badge-slate"}>{type.replace(/_/g, " ")}</span>;
}

export default function Documents() {
  const qc = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["documents"],
    queryFn: () => api.get(`/documents/?org_id=${ORG_ID}&limit=100`).then(r => r.data),
  });

  const uploadMutation = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      form.append("org_id", ORG_ID);
      return api.post("/documents/upload", form, {
        headers: { "Content-Type": "multipart/form-data" },
      }).then(r => r.data);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["documents"] }),
  });

  function handleFiles(files: FileList | null) {
    if (!files) return;
    Array.from(files).forEach(f => {
      if (f.type === "application/pdf") uploadMutation.mutate(f);
    });
  }

  const docs: Document[] = data?.documents ?? [];

  return (
    <div className="p-6 space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-slate-100">Documents</h1>
        <p className="mt-0.5 text-sm text-slate-500">{data?.total ?? 0} total · PDF ingestion</p>
      </div>

      {/* Drop zone */}
      <div
        className={`rounded-xl border-2 border-dashed p-10 text-center transition-colors cursor-pointer ${
          dragging ? "border-sky-500 bg-sky-500/5" : "border-slate-700 hover:border-slate-600"
        }`}
        onClick={() => inputRef.current?.click()}
        onDragOver={e => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={e => { e.preventDefault(); setDragging(false); handleFiles(e.dataTransfer.files); }}
      >
        <CloudUpload className="mx-auto h-10 w-10 text-slate-600 mb-3" />
        <p className="text-sm font-medium text-slate-300">Drop PDF files here or click to browse</p>
        <p className="mt-1 text-xs text-slate-500">Invoices, bank statements, tax forms, W-2, 1099, receipts</p>
        <input ref={inputRef} type="file" accept=".pdf" multiple className="hidden"
          onChange={e => handleFiles(e.target.files)} />
      </div>

      {uploadMutation.isPending && (
        <div className="rounded-lg bg-sky-500/10 border border-sky-500/20 px-4 py-3 text-sm text-sky-400">
          Uploading and ingesting document…
        </div>
      )}
      {uploadMutation.isSuccess && uploadMutation.data && (
        <div className="rounded-lg bg-emerald-500/10 border border-emerald-500/20 px-4 py-3 text-sm space-y-1">
          <p className="font-semibold text-emerald-400">
            Document ingested · {uploadMutation.data.doc_type}
          </p>
          <p className="text-slate-400 text-xs">
            {uploadMutation.data.pages} pages · {(uploadMutation.data.confidence * 100).toFixed(0)}% confidence ·
            strategy: {uploadMutation.data.strategy_used} ·
            {uploadMutation.data.needs_human_review ? " → sent to review queue" : " → extracted"}
          </p>
        </div>
      )}

      {/* Table */}
      <div className="card p-0 overflow-hidden">
        {isLoading ? (
          <div className="py-8 text-center text-sm text-slate-600">Loading…</div>
        ) : docs.length === 0 ? (
          <EmptyState icon={FileText} title="No documents yet" description="Upload a PDF to start processing." />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-800">
                {["Filename", "Type", "Pages", "Confidence", "Status", "Uploaded"].map(h => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {docs.map(doc => (
                <tr key={doc.document_id} className="table-row-hover">
                  <td className="px-4 py-3 font-medium text-slate-200 max-w-xs truncate">{doc.filename}</td>
                  <td className="px-4 py-3">{docTypeBadge(doc.doc_type)}</td>
                  <td className="px-4 py-3 text-slate-400">{doc.pages ?? "—"}</td>
                  <td className="px-4 py-3">
                    <span className={`font-mono text-xs ${
                      Number(doc.confidence) >= 0.9 ? "text-emerald-400" :
                      Number(doc.confidence) >= 0.7 ? "text-amber-400" : "text-red-400"
                    }`}>
                      {doc.confidence != null ? `${(Number(doc.confidence) * 100).toFixed(0)}%` : "—"}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={doc.status === "extracted" ? "badge-green" : doc.status === "review" ? "badge-yellow" : "badge-slate"}>
                      {doc.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-500">
                    {doc.uploaded_at ? new Date(doc.uploaded_at).toLocaleDateString() : "—"}
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
