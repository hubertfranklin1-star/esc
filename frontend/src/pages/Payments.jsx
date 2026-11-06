import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHeader, Panel, StatusPill, Empty } from "@/components/common";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { useTx } from "@/context/TxContext";
import { useAuth } from "@/context/AuthContext";
import { api, errMsg, download } from "@/lib/api";
import { usd, dt, cap } from "@/lib/fmt";

const Fees = ({ fees, setFees, isAdmin }) => {
  const save = async () => {
    try { const r = await api.put("/fees", fees); setFees(r.data); toast.success("Fees saved"); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <Panel title="Fees" testid="fee-config" actions={isAdmin && <Button size="sm" data-testid="fees-save-button" onClick={save}>Save</Button>}>
      {fees.map((f, i) => (
        <div key={f.code} className="flex items-center justify-between gap-3 border-b border-[#26354D]/60 py-2 last:border-0">
          <div><div className="text-sm text-white">{f.label}</div><div className="text-[11px] text-slate-500">Paid by {f.party}</div></div>
          {isAdmin ? (
            <Input type="number" min="0" data-testid={`fee-input-${f.code}`} value={f.amount} className="h-8 w-36 bg-[#0B111E] text-right font-mono text-xs"
              onChange={(e) => setFees(fees.map((x, j) => (j === i ? { ...x, amount: Number(e.target.value) } : x)))} />
          ) : <span data-testid={`fee-value-${f.code}`} className="font-mono text-sm">{usd(f.amount)}</span>}
        </div>
      ))}
    </Panel>
  );
};

const NewInvoice = ({ open, onOpenChange, fees, onDone }) => {
  const { tx } = useTx();
  const [party, setParty] = useState("sender");
  const [items, setItems] = useState(["sender_onboarding"]);
  const toggle = (c) => setItems(items.includes(c) ? items.filter((x) => x !== c) : [...items, c]);
  const create = async () => {
    try {
      await api.post("/invoices", { transaction_id: tx.id, party, items });
      toast.success("Invoice created");
      onDone();
      return true;
    } catch (e) { toast.error(errMsg(e)); return false; }
  };
  return (
    <ConfirmDialog open={open} onOpenChange={onOpenChange} testid="new-invoice-dialog" title="New invoice" confirmLabel="Create invoice" onConfirm={create}>
      <div className="space-y-4">
        <div className="space-y-1.5">
          <Label>Bill to</Label>
          <Select value={party} onValueChange={setParty}>
            <SelectTrigger data-testid="invoice-party-select" className="bg-[#0B111E]"><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="sender">Sender — {tx.sender_name}</SelectItem><SelectItem value="recipient">Recipient — {tx.recipient_name}</SelectItem></SelectContent>
          </Select>
        </div>
        {fees.map((f) => (
          <label key={f.code} className="flex items-center justify-between gap-3 text-sm">
            <span className="flex items-center gap-2"><Checkbox data-testid={`invoice-item-${f.code}`} checked={items.includes(f.code)} onCheckedChange={() => toggle(f.code)} />{f.label}</span>
            <span className="font-mono text-xs text-slate-400">{usd(f.amount)}</span>
          </label>
        ))}
      </div>
    </ConfirmDialog>
  );
};

const Row = ({ inv, user, run }) => (
  <TableRow data-testid={`invoice-row-${inv.invoice_number}`}>
    <TableCell className="font-mono text-xs text-white">{inv.invoice_number}{inv.kind === "engagement" && <div className="text-[10px] text-amber-300">Escrow fee</div>}</TableCell>
    <TableCell className="max-w-[240px] text-xs text-slate-300">{inv.items.map((l) => l.description).join(", ")}</TableCell>
    <TableCell className="font-mono text-xs">{usd(inv.amount, 2)}</TableCell>
    <TableCell className="text-xs">{inv.responsible_name}<div className="text-slate-500">{cap(inv.party)}</div></TableCell>
    <TableCell><StatusPill status={inv.status} testid={`invoice-status-${inv.invoice_number}`} /></TableCell>
    <TableCell className="text-xs text-slate-400">{dt(inv.issued_at)}</TableCell>
    <TableCell className="text-xs text-slate-400">{dt(inv.paid_at)}</TableCell>
    <TableCell>
      <div className="flex gap-1.5">
        {inv.status === "Unpaid" && user.id === inv.responsible_user_id && <Button size="sm" data-testid={`invoice-pay-${inv.invoice_number}`} onClick={() => run(`/invoices/${inv.id}/pay`, "Payment sent")}>Pay</Button>}
        {inv.status === "Payment Sent" && user.role === "admin" && <Button size="sm" data-testid={`invoice-confirm-${inv.invoice_number}`} onClick={() => run(`/invoices/${inv.id}/confirm`, "Payment confirmed")}>Confirm</Button>}
        <Button size="sm" variant="outline" data-testid={`invoice-pdf-${inv.invoice_number}`} onClick={() => download(`/invoices/${inv.id}/pdf`, `${inv.invoice_number}.pdf`)}><Download className="h-3.5 w-3.5" /></Button>
      </div>
    </TableCell>
  </TableRow>
);

export default function Payments() {
  const { tx, tick, refresh } = useTx();
  const { user } = useAuth();
  const isAdmin = user.role === "admin";
  const [fees, setFees] = useState([]);
  const [invoices, setInvoices] = useState([]);
  const [open, setOpen] = useState(false);
  const load = useCallback(() => api.get(`/invoices?transaction_id=${tx.id}`).then((r) => setInvoices(r.data)), [tx.id]);
  useEffect(() => { api.get("/fees").then((r) => setFees(r.data)); }, []);
  useEffect(() => { load(); }, [load, tick]);
  const run = async (path, ok) => {
    try { await api.post(path); toast.success(ok); await refresh(); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div data-testid="payments-page">
      <PageHeader title="Payments" desc="Invoices and fees for this deal."
        actions={isAdmin && <Button data-testid="new-invoice-button" disabled={tx.on_hold || !!tx.completed_at} onClick={() => setOpen(true)}>New invoice</Button>} />
      <div className="grid gap-6 xl:grid-cols-[1fr_340px]">
        <Panel title="Invoices" testid="invoices-table">
          {invoices.length === 0 ? <Empty testid="invoices-empty">No invoices yet. The escrow fee invoice is created when both parties sign.</Empty> : (
            <div className="overflow-x-auto">
              <Table className="vb-table">
                <TableHeader><TableRow><TableHead>Invoice</TableHead><TableHead>For</TableHead><TableHead>Amount</TableHead><TableHead>Billed to</TableHead><TableHead>Status</TableHead><TableHead>Issued</TableHead><TableHead>Paid</TableHead><TableHead /></TableRow></TableHeader>
                <TableBody>{invoices.map((inv) => <Row key={inv.id} inv={inv} user={user} run={run} />)}</TableBody>
              </Table>
            </div>
          )}
        </Panel>
        <Fees fees={fees} setFees={setFees} isAdmin={isAdmin} />
      </div>
      {isAdmin && <NewInvoice open={open} onOpenChange={setOpen} fees={fees} onDone={load} />}
    </div>
  );
}
