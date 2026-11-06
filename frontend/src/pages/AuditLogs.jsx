import { useEffect, useState } from "react";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHeader, Panel, Empty } from "@/components/common";
import { useTx } from "@/context/TxContext";
import { api } from "@/lib/api";
import { dt, cap } from "@/lib/fmt";

export default function AuditLogs() {
  const { tx, tick } = useTx();
  const [logs, setLogs] = useState([]);
  const [all, setAll] = useState(false);
  const [q, setQ] = useState("");
  useEffect(() => {
    api.get(all ? "/audit" : `/audit?transaction_id=${tx.id}`).then((r) => setLogs(r.data));
  }, [all, tx.id, tick]);
  const rows = logs.filter((l) => !q || `${l.action} ${l.detail} ${l.actor} ${l.reference}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <div data-testid="audit-page">
      <PageHeader eyebrow="Audit Logs" title="Demonstration audit history" desc="Every simulated action is recorded with actor, role and timestamp." />
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center">
        <Input data-testid="audit-search-input" placeholder="Search actions, actors, details…" value={q} onChange={(e) => setQ(e.target.value)} className="max-w-sm bg-[#111827]" />
        <label className="flex items-center gap-2 text-sm text-slate-300"><Switch data-testid="audit-all-toggle" checked={all} onCheckedChange={setAll} /> All transactions & system events</label>
        <span data-testid="audit-count" className="font-mono text-xs text-slate-500 sm:ml-auto">{rows.length} entries</span>
      </div>
      <Panel>
        {rows.length === 0 ? <Empty>No entries.</Empty> : (
          <div className="overflow-x-auto">
            <Table className="vb-table">
              <TableHeader><TableRow><TableHead>Timestamp</TableHead><TableHead>Reference</TableHead><TableHead>Actor</TableHead><TableHead>Action</TableHead><TableHead>Detail</TableHead></TableRow></TableHeader>
              <TableBody>
                {rows.map((l) => (
                  <TableRow key={l.id} data-testid="audit-row">
                    <TableCell className="whitespace-nowrap font-mono text-xs text-slate-400">{dt(l.timestamp)}</TableCell>
                    <TableCell className="font-mono text-xs">{l.reference || "SYSTEM"}</TableCell>
                    <TableCell className="text-xs">{l.actor}<div className="font-mono text-[10px] uppercase text-amber-300/80">{cap(l.actor_role)}</div></TableCell>
                    <TableCell className="text-sm text-white">{l.action}</TableCell>
                    <TableCell className="max-w-md text-xs text-slate-400">{l.detail || "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Panel>
    </div>
  );
}
