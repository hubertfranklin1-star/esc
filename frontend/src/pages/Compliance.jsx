import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHeader, Panel, StatusPill } from "@/components/common";
import { useTx } from "@/context/TxContext";
import { useAuth } from "@/context/AuthContext";
import { api, errMsg } from "@/lib/api";
import { dt } from "@/lib/fmt";

const STATUSES = ["Pending", "Under Review", "Additional Information Required", "Simulated Approval", "Simulated Rejection"];

const CheckRow = ({ k, c, isAdmin, locked, act }) => {
  const [note, setNote] = useState(c.note || "");
  return (
    <TableRow data-testid={`compliance-row-${k}`}>
      <TableCell className="text-sm text-white">{c.label}</TableCell>
      <TableCell>
        {isAdmin && !locked ? (
          <Select value={c.status} onValueChange={(v) => act("set_compliance", { check: k, status: v, note }, `${c.label}: ${v}`)}>
            <SelectTrigger data-testid={`compliance-status-select-${k}`} className="w-[240px] bg-[#0B111E] text-xs"><SelectValue /></SelectTrigger>
            <SelectContent>{STATUSES.map((s) => <SelectItem key={s} value={s} data-testid={`compliance-option-${k}-${s.replace(/ /g, "-").toLowerCase()}`}>{s}</SelectItem>)}</SelectContent>
          </Select>
        ) : <StatusPill status={c.status} testid={`compliance-status-${k}`} />}
      </TableCell>
      <TableCell>
        {isAdmin && !locked ? (
          <Input data-testid={`compliance-note-${k}`} value={note} onChange={(e) => setNote(e.target.value)} onBlur={() => note !== (c.note || "") && act("set_compliance", { check: k, status: c.status, note }, "Note saved")} placeholder="Reviewer note" className="h-8 bg-[#0B111E] text-xs" />
        ) : <span className="text-xs text-slate-400">{c.note || "—"}</span>}
      </TableCell>
      <TableCell className="text-xs text-slate-500">{dt(c.updated_at)}</TableCell>
    </TableRow>
  );
};

export default function Compliance() {
  const { tx, act, refresh } = useTx();
  const { user } = useAuth();
  const isAdmin = user.role === "admin";
  const locked = !!tx.aml.completed_at;
  const entries = Object.entries(tx.compliance);
  const approveAll = async () => {
    try {
      for (const [k] of entries) await api.post(`/transactions/${tx.id}/actions/set_compliance`, { data: { check: k, status: "Simulated Approval", note: tx.compliance[k].note } });
      toast.success("All checks set to Simulated Approval");
    } catch (e) { toast.error(errMsg(e)); }
    refresh();
  };
  const approved = entries.filter(([, c]) => c.status === "Simulated Approval").length;
  return (
    <div data-testid="compliance-page">
      <PageHeader eyebrow="Compliance Centre" title="Verification centre" desc="Fictional verification outcomes. These are not real AML, KYC or sanctions approvals."
        actions={isAdmin && !locked && (
          <>
            <Button variant="outline" data-testid="compliance-approve-all" onClick={approveAll}>Set all to Simulated Approval</Button>
            <Button data-testid="compliance-complete-aml" disabled={tx.current_step !== 14} onClick={() => act("complete_aml", {}, "Simulated AML review completed")}>Complete AML review</Button>
          </>
        )} />
      <div className="mb-4 flex flex-wrap gap-3 text-xs text-slate-400">
        <span data-testid="compliance-approved-count" className="font-mono">{approved}/7 at Simulated Approval</span>
        <StatusPill status={locked ? `AML review completed ${dt(tx.aml.completed_at)}` : "AML review open"} testid="aml-status" />
      </div>
      <Panel>
        <div className="overflow-x-auto">
          <Table className="vb-table">
            <TableHeader><TableRow><TableHead>Check</TableHead><TableHead>Status</TableHead><TableHead>Note</TableHead><TableHead>Updated</TableHead></TableRow></TableHeader>
            <TableBody>{entries.map(([k, c]) => <CheckRow key={`${k}-${c.updated_at}`} k={k} c={c} isAdmin={isAdmin} locked={locked} act={act} />)}</TableBody>
          </Table>
        </div>
      </Panel>
      {isAdmin && !locked && tx.current_step < 14 && <p className="mt-3 text-xs text-slate-500">The AML review can be completed after the simulated blockchain analysis (step 13). Statuses may be updated at any time.</p>}
    </div>
  );
}
