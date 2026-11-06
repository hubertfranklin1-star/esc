import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { PageHeader, Panel, StatusPill, SimTag } from "@/components/common";
import { useTx } from "@/context/TxContext";
import { useAuth } from "@/context/AuthContext";
import { api, errMsg } from "@/lib/api";
import { usd, ethFmt, dt } from "@/lib/fmt";

const CreateDialog = ({ open, onOpenChange }) => {
  const { loadList, select } = useTx();
  const [f, setF] = useState({ usd_value: "250000000", sender_name: "Demo Sender Holdings", recipient_name: "Demo Buyer Ltd" });
  const create = async () => {
    try {
      const r = await api.post("/transactions", { ...f, usd_value: Number(f.usd_value) });
      toast.success(`${r.data.reference} created (simulated)`);
      await loadList();
      select(r.data.id);
      return true;
    } catch (e) {
      toast.error(errMsg(e));
      return false;
    }
  };
  const field = (k, label, type = "text") => (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      <Input type={type} data-testid={`create-tx-${k}-input`} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} className="bg-[#0B111E]" />
    </div>
  );
  return (
    <ConfirmDialog open={open} onOpenChange={onOpenChange} testid="create-tx-dialog" title="Create simulated transaction"
      description="Parties are linked to the demo sender and recipient accounts. ETH quantity uses the fixed $2,350 demonstration rate." confirmLabel="Create transaction" onConfirm={create}>
      <div className="space-y-3">
        {field("usd_value", "Illustrative value (USD, fictional)", "number")}
        {field("sender_name", "Sender entity (fictional)")}
        {field("recipient_name", "Recipient entity (fictional)")}
      </div>
    </ConfirmDialog>
  );
};

export default function Transactions() {
  const { list, select, selectedId, act, tx } = useTx();
  const { user } = useAuth();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const isAdmin = user.role === "admin";
  const toggleHold = async (t) => {
    if (t.id !== tx.id) select(t.id);
    else await act(t.on_hold ? "resume" : "hold", {}, t.on_hold ? "Transaction resumed" : "Transaction placed on hold");
  };
  return (
    <div data-testid="transactions-page">
      <PageHeader eyebrow="Transactions" title="Escrow transactions" desc="All records are fictional simulation data."
        actions={isAdmin && <Button data-testid="create-transaction-button" onClick={() => setOpen(true)} className="gap-1.5"><Plus className="h-4 w-4" /> New transaction</Button>} />
      <Panel>
        <div className="overflow-x-auto">
          <Table className="vb-table">
            <TableHeader>
              <TableRow><TableHead>Reference</TableHead><TableHead>Parties</TableHead><TableHead>Illustrative value</TableHead><TableHead>Simulated ETH</TableHead><TableHead>Step</TableHead><TableHead>Status</TableHead><TableHead>Created</TableHead><TableHead /></TableRow>
            </TableHeader>
            <TableBody>
              {list.map((t) => (
                <TableRow key={t.id} data-testid={`tx-row-${t.reference}`} className={`cursor-pointer ${t.id === selectedId ? "bg-sky-500/5" : ""}`} onClick={() => { select(t.id); nav("/"); }}>
                  <TableCell className="font-mono text-xs text-white">{t.reference} <SimTag className="ml-1" /></TableCell>
                  <TableCell className="text-xs">{t.sender_name}<div className="text-slate-500">→ {t.recipient_name}</div></TableCell>
                  <TableCell className="font-mono text-xs">{usd(t.usd_value)}</TableCell>
                  <TableCell className="font-mono text-xs">{ethFmt(t.eth_quantity, 2)}</TableCell>
                  <TableCell className="font-mono text-xs">{Math.min(t.current_step, 19)}/19</TableCell>
                  <TableCell><StatusPill status={t.status} /></TableCell>
                  <TableCell className="text-xs text-slate-400">{dt(t.created_at)}</TableCell>
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    {isAdmin && !t.completed_at && t.id === selectedId && (
                      <Button size="sm" variant="outline" data-testid={`tx-hold-toggle-${t.reference}`} onClick={() => toggleHold(t)}>{t.on_hold ? "Resume" : "Hold"}</Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Panel>
      {isAdmin && <CreateDialog open={open} onOpenChange={setOpen} />}
    </div>
  );
}
