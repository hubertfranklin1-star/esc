import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Download, FileText, Lock, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PageHeader, Panel, Empty, StatusPill } from "@/components/common";
import { useTx } from "@/context/TxContext";
import { useAuth } from "@/context/AuthContext";
import { api, errMsg, download } from "@/lib/api";
import { dt } from "@/lib/fmt";

const UploadForm = ({ txId, onDone }) => {
  const [title, setTitle] = useState("");
  const [file, setFile] = useState(null);
  const submit = async () => {
    if (!file) return toast.error("Choose a file");
    const fd = new FormData();
    fd.append("title", title || file.name);
    fd.append("file", file);
    try {
      await api.post(`/reports/${txId}/uploads`, fd);
      toast.success("Demonstration report uploaded");
      setTitle(""); setFile(null);
      onDone();
    } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div className="flex flex-col gap-2 sm:flex-row">
      <Input data-testid="upload-title-input" placeholder="Report title" value={title} onChange={(e) => setTitle(e.target.value)} className="bg-[#0B111E]" />
      <Input data-testid="upload-file-input" type="file" onChange={(e) => setFile(e.target.files[0])} className="bg-[#0B111E]" />
      <Button data-testid="upload-submit-button" onClick={submit} className="gap-1.5"><Upload className="h-4 w-4" /> Upload</Button>
    </div>
  );
};

export default function Reports() {
  const { tx, refresh, tick } = useTx();
  const { user } = useAuth();
  const [uploads, setUploads] = useState([]);
  const load = useCallback(() => api.get(`/reports/${tx.id}/uploads`).then((r) => setUploads(r.data)), [tx.id]);
  useEffect(() => { load(); }, [load, tick]);
  const get = async (r) => {
    try {
      await download(`/reports/${tx.id}/${r.type}/pdf`, `${tx.reference}-${r.type}-SIMULATION.pdf`);
      toast.success(`${r.title} downloaded`);
      refresh();
    } catch (e) { toast.error("Report not available yet"); }
  };
  return (
    <div data-testid="reports-page">
      <PageHeader eyebrow="Reports" title="Demonstration reports" desc="Every PDF carries a SIMULATION watermark. None is a genuine financial, regulatory or third-party certification." />
      <div className="mb-4 flex flex-wrap gap-2 text-xs">
        <StatusPill status={tx.report_access.sender ? "Sender accessed verification reports" : "Sender has not accessed verification reports"} testid="report-access-sender" />
        <StatusPill status={tx.report_access.recipient ? "Recipient accessed verification reports" : "Recipient has not accessed verification reports"} testid="report-access-recipient" />
      </div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {tx.reports.map((r) => (
          <div key={r.type} data-testid={`report-card-${r.type}`} className={`panel flex flex-col justify-between p-5 transition-colors ${r.available ? "hover:border-sky-400/40" : "opacity-55"}`}>
            <div className="flex items-start gap-3">
              {r.available ? <FileText className="h-5 w-5 text-sky-300" /> : <Lock className="h-5 w-5 text-slate-500" />}
              <div>
                <div className="text-sm font-semibold text-white">{r.title}</div>
                <div className="font-mono text-[10px] uppercase tracking-wider text-amber-300">PDF · SIMULATION watermark{r.type === "compliance" ? " · verification" : ""}</div>
              </div>
            </div>
            <Button size="sm" variant={r.available ? "default" : "outline"} disabled={!r.available} className="mt-4 gap-1.5 self-start" data-testid={`report-download-${r.type}`} onClick={() => get(r)}>
              <Download className="h-3.5 w-3.5" /> {r.available ? "Download" : "Not yet available"}
            </Button>
          </div>
        ))}
      </div>
      <Panel title="Uploaded demonstration documents" className="mt-6" testid="uploads-panel" sub="Shared with both parties">
        {user.role === "admin" && <div className="mb-4"><UploadForm txId={tx.id} onDone={load} /></div>}
        {uploads.length === 0 ? <Empty testid="uploads-empty">No uploaded documents.</Empty> : uploads.map((u) => (
          <div key={u.id} data-testid={`upload-row-${u.id}`} className="flex items-center justify-between border-b border-[#26354D]/60 py-2.5 last:border-0">
            <div><div className="text-sm text-white">{u.title} <span className="sim-tag ml-1">Demonstration</span></div><div className="text-xs text-slate-500">{u.filename} · {(u.size / 1024).toFixed(1)} KB · {dt(u.uploaded_at)}</div></div>
            <Button size="sm" variant="outline" data-testid={`upload-download-${u.id}`} onClick={() => download(`/reports/uploads/${u.id}/download`, `SIMULATION-${u.filename}`)}><Download className="h-3.5 w-3.5" /></Button>
          </div>
        ))}
      </Panel>
    </div>
  );
}
