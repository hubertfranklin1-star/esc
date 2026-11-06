import { useEffect, useState } from "react";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHeader, Panel, Empty } from "@/components/common";
import { useTx } from "@/context/TxContext";
import { api } from "@/lib/api";
import { dt, cap } from "@/lib/fmt";

export default function Activity() {
  const { tx, tick } = useTx();
  const [logs, setLogs] = useState([]);
  const [q, setQ] = useState("");
  useEffect(() => {
    api.get(`/audit?transaction_id=${tx.id}`).then((r) => setLogs(r.data));
  }, [tx.id, tick]);
  const rows = logs.filter((l) => !q || `${l.action} ${l.detail} ${l.actor}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <div data-testid="activity-page">
      <PageHeader title="Activity" desc="Everything that happened on this deal." />
      <Input data-testid="activity-search-input" placeholder="Search…" value={q} onChange={(e) => setQ(e.target.value)} className="mb-4 max-w-sm bg-[#111827]" />
      <Panel>
        {rows.length === 0 ? <Empty>No activity yet.</Empty> : (
          <div className="overflow-x-auto">
            <Table className="vb-table">
              <TableHeader><TableRow><TableHead>When</TableHead><TableHead>Who</TableHead><TableHead>What</TableHead></TableRow></TableHeader>
              <TableBody>
                {rows.map((l) => (
                  <TableRow key={l.id} data-testid="activity-row">
                    <TableCell className="whitespace-nowrap text-xs text-slate-400">{dt(l.timestamp)}</TableCell>
                    <TableCell className="text-xs">{l.actor === "system" ? "System" : l.actor}<div className="text-[10px] uppercase text-amber-300/80">{cap(l.actor_role)}</div></TableCell>
                    <TableCell className="text-sm text-white">{l.action}{l.detail && <div className="text-xs text-slate-400">{l.detail}</div>}</TableCell>
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
