import { useEffect, useState } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHeader, Panel, Empty } from "@/components/common";
import { useTx } from "@/context/TxContext";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { dt, cap } from "@/lib/fmt";

export default function Activity() {
  const { tx, tick } = useTx();
  const { user } = useAuth();
  const isAdmin = user.role === "admin";
  const [logs, setLogs] = useState([]);
  const [q, setQ] = useState("");
  const [scope, setScope] = useState("deal");
  const txId = tx?.id;
  const all = isAdmin && (scope === "all" || !txId);
  useEffect(() => {
    if (!all && !txId) { setLogs([]); return; }
    api.get(all ? "/audit" : `/audit?transaction_id=${txId}`).then((r) => setLogs(r.data)).catch(() => {});
  }, [all, txId, tick]);
  const rows = logs.filter((l) => !q || `${l.action} ${l.detail} ${l.actor} ${l.reference || ""}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <div data-testid="activity-page">
      <PageHeader title="Activity" desc={all ? "Everything on the platform, including settings changes and deleted accounts." : "Everything that happened on this deal."}
        actions={isAdmin && (
          <div className="flex rounded-md border border-[#26354D] p-0.5">
            <Button size="sm" variant={all ? "ghost" : "secondary"} disabled={!txId} data-testid="activity-scope-deal" onClick={() => setScope("deal")}>This deal</Button>
            <Button size="sm" variant={all ? "secondary" : "ghost"} data-testid="activity-scope-all" onClick={() => setScope("all")}>All activity</Button>
          </div>
        )} />
      <Input data-testid="activity-search-input" placeholder="Search…" value={q} onChange={(e) => setQ(e.target.value)} className="mb-4 max-w-sm bg-[#111827]" />
      <Panel>
        {rows.length === 0 ? <Empty>No activity yet.</Empty> : (
          <div className="overflow-x-auto">
            <Table className="vb-table">
              <TableHeader><TableRow><TableHead>When</TableHead>{all && <TableHead>Deal</TableHead>}<TableHead>Who</TableHead><TableHead>What</TableHead></TableRow></TableHeader>
              <TableBody>
                {rows.map((l) => (
                  <TableRow key={l.id} data-testid="activity-row">
                    <TableCell className="whitespace-nowrap text-xs text-slate-400">{dt(l.timestamp)}</TableCell>
                    {all && <TableCell className="whitespace-nowrap font-mono text-xs text-slate-300">{l.reference || "Platform"}</TableCell>}
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
