import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Download, FileText, Lock, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PageHeader, Panel, Empty } from "@/components/common";
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
      toast.success("Document shared");
      setTitle(""); setFile(null);
      onDone();
    } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div className="flex flex-col gap-2 sm:flex-row">
      <Input data-testid="upload-title-input" placeholder="Title" value={title} onChange={(e) => setTitle(e.target.value)} className="bg-[#0B111E]" />
      <Input data-testid="upload-file-input" type="file" onChange={(e) => setFile(e.target.files[0])} className="bg-[#0B111E]" />
      <Button data-testid="upload-submit-button" onClick={submit} className="gap-1.5"><Upload className="h-4 w-4" /> Share</Button>
    </div>
  );
};

export default function Documents() {
  const { tx, tick } = useTx();
  const { user } = useAuth();
  const [uploads, setUploads] = useState([]);
  const load = useCallback(() => api.get(`/reports/${tx.id}/uploads?category=document`).then((r) => setUploads(r.data)), [tx.id]);
  useEffect(() => { load(); }, [load, tick]);
  const get = async (r) => {
    try { await download(`/reports/${tx.id}/${r.type}/pdf`, `${tx.reference}-${r.type}.pdf`); } catch (e) { toast.error("Not ready yet"); }
  };
  return (
    <div data-testid="documents-page">
      <PageHeader title="Documents" desc="Documents become available as the deal moves forward." />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {tx.reports.map((r) => (
          <div key={r.type} data-testid={`doc-card-${r.type}`} className={`panel flex flex-col justify-between p-5 ${r.available ? "" : "opacity-55"}`}>
            <div className="flex items-center gap-3">
              {r.available ? <FileText className="h-5 w-5 text-sky-300" /> : <Lock className="h-5 w-5 text-slate-500" />}
              <span className="text-sm font-semibold text-white">{r.title}</span>
            </div>
            <Button size="sm" variant={r.available ? "default" : "outline"} disabled={!r.available} className="mt-4 gap-1.5 self-start" data-testid={`doc-download-${r.type}`} onClick={() => get(r)}>
              <Download className="h-3.5 w-3.5" /> {r.available ? "Download" : "Not ready yet"}
            </Button>
          </div>
        ))}
      </div>
      <Panel title="Shared files" className="mt-6" testid="uploads-panel">
        {user.role === "admin" && <div className="mb-4"><UploadForm txId={tx.id} onDone={load} /></div>}
        {uploads.length === 0 ? <Empty testid="uploads-empty">No shared files.</Empty> : uploads.map((u) => (
          <div key={u.id} data-testid={`upload-row-${u.id}`} className="flex items-center justify-between border-b border-[#26354D]/60 py-2.5 last:border-0">
            <div><div className="text-sm text-white">{u.title}</div><div className="text-xs text-slate-500">{u.filename} · {(u.size / 1024).toFixed(1)} KB · {dt(u.uploaded_at)}</div></div>
            <Button size="sm" variant="outline" data-testid={`upload-download-${u.id}`} onClick={() => download(`/reports/uploads/${u.id}/download`, u.filename)}><Download className="h-3.5 w-3.5" /></Button>
          </div>
        ))}
      </Panel>
    </div>
  );
}
