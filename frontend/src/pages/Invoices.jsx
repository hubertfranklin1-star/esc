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
import { PayDialog } from "@/components/ActionDialogs";
import { ENGAGEMENT_ITEMS } from "@/components/NextActions";
import { useTx } from "@/context/TxContext";
import { useAuth } from "@/context/AuthContext";
import { api, errMsg, download } from "@/lib/api";
import { usd, dt, cap } from "@/lib/fmt";

const FeeConfig = ({ fees, setFees, isAdmin }) => {
  const save = async () => {
    try { const r = await api.put("/fees", fees); setFees(r.data); toast.success("Demonstration fees saved"); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <Panel title={isAdmin ? "Fee engine" : "Proposed escrow charges"} sub="Fictional demonstration amounts (USD)" testid="fee-config"
      actions={isAdmin && <Button size="sm" data-testid="fees-save-button" onClick={save}>Save fees</Button>}>
      <div className="space-y-2">
        {fees.map((f, i) => (
          <div key={f.code} className="flex items-center justify-between gap-3 border-b border-[#26354D]/60 pb-2 last:border-0">
            <div><div className="text-sm text-white">{f.label}</div><div className="font-mono text-[10px] uppercase text-slate-500">Billed to {f.party}</div></div>
            {isAdmin ? (
              <Input type="number" min="0" data-testid={`fee-input-${f.code}`} value={f.amount} className="h-8 w-36 bg-[#0B111E] text-right font-mono text-xs"
                onChange={(e) => setFees(fees.map((x, j) => (j === i ? { ...x, amount: Number(e.target.value) } : x)))} />
            ) : <span data-testid={`fee-value-${f.code}`} className="font-mono text-sm">{usd(f.amount)}</span>}
          </div>
        ))}
      </div>
    </Panel>
  );
};

const GenerateDialog = ({ open, onOpenChange, fees, onDone }) => {
  const { tx, refresh } = useTx();
  const [party, setParty] = useState("sender");
  const [items, setItems] = useState(["sender_onboarding"]);
  const engagement = tx.current_step === 8 && party === "recipient";
  const toggle = (c) => setItems(items.includes(c) ? items.filter((x) => x !== c) : [...items, c]);
  const create = async () => {
    try {
      await api.post("/invoices", { transaction_id: tx.id, party, items, kind: engagement ? "engagement" : "standard" });
      toast.success("Demonstration invoice generated");
      await refresh();
      onDone();
      return true;
    } catch (e) { toast.error(errMsg(e)); return false; }
  };
  return (
    <ConfirmDialog open={open} onOpenChange={onOpenChange} testid="generate-invoice-dialog" title="Generate demonstration invoice" confirmLabel="Generate invoice" onConfirm={create}>
      <div className="space-y-4">
        <div className="space-y-1.5">
          <Label>Responsible party</Label>
          <Select value={party} onValueChange={(v) => { setParty(v); setItems(v === "recipient" ? ENGAGEMENT_ITEMS : ["sender_onboarding"]); }}>
            <SelectTrigger data-testid="invoice-party-select" className="bg-[#0B111E]"><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="sender">Sender — {tx.sender_name}</SelectItem><SelectItem value="recipient">Recipient — {tx.recipient_name}</SelectItem></SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          {fees.map((f) => (
            <label key={f.code} className="flex items-center justify-between gap-3 text-sm">
              <span className="flex items-center gap-2"><Checkbox data-testid={`invoice-item-${f.code}`} checked={items.includes(f.code)} onCheckedChange={() => toggle(f.code)} />{f.label}</span>
              <span className="font-mono text-xs text-slate-400">{usd(f.amount)}</span>
            </label>
          ))}
        </div>
        {engagement && <p className="text-xs text-amber-300">This will be issued as the engagement invoice (workflow step 8).</p>}
      </div>
    </ConfirmDialog>
  );
};

const InvoiceRow = ({ inv, user, onPay, onConfirm }) => (
  <TableRow data-testid={`invoice-row-${inv.invoice_number}`}>
    <TableCell className="font-mono text-xs text-white">{inv.invoice_number}<div className="text-[10px] text-amber-300">SIMULATED{inv.kind === "engagement" ? " · ENGAGEMENT" : ""}</div></TableCell>
    <TableCell className="font-mono text-xs">{inv.reference}</TableCell>
    <TableCell className="max-w-[220px] text-xs text-slate-300">{inv.items.map((l) => l.description).join(", ")}</TableCell>
    <TableCell className="font-mono text-xs">{usd(inv.amount, 2)}</TableCell>
    <TableCell className="text-xs">{inv.responsible_name}<div className="text-slate-500">{cap(inv.party)}</div></TableCell>
    <TableCell><StatusPill status={inv.status} testid={`invoice-status-${inv.invoice_number}`} /></TableCell>
    <TableCell className="text-xs text-slate-400">{dt(inv.issued_at)}</TableCell>
    <TableCell className="text-xs text-slate-400">{dt(inv.paid_at)}</TableCell>
    <TableCell>
      <div className="flex gap-1.5">
        {inv.status === "Issued" && user.id === inv.responsible_user_id && <Button size="sm" data-testid={`invoice-pay-${inv.invoice_number}`} onClick={() => onPay(inv)}>Pay (sim)</Button>}
        {inv.status.startsWith("Payment Submitted") && user.role === "admin" && <Button size="sm" data-testid={`invoice-confirm-${inv.invoice_number}`} onClick={() => onConfirm(inv)}>Confirm</Button>}
        <Button size="sm" variant="outline" data-testid={`invoice-pdf-${inv.invoice_number}`} onClick={() => download(`/invoices/${inv.id}/pdf`, `${inv.invoice_number}-SIMULATION.pdf`)}><Download className="h-3.5 w-3.5" /></Button>
      </div>
    </TableCell>
  </TableRow>
);

export default function Invoices() {
  const { tx, tick, refresh } = useTx();
  const { user } = useAuth();
  const isAdmin = user.role === "admin";
  const [fees, setFees] = useState([]);
  const [invoices, setInvoices] = useState([]);
  const [gen, setGen] = useState(false);
  const [paying, setPaying] = useState(null);
  const load = useCallback(() => api.get(`/invoices?transaction_id=${tx.id}`).then((r) => setInvoices(r.data)), [tx.id]);
  useEffect(() => { api.get("/fees").then((r) => setFees(r.data)); }, []);
  useEffect(() => { load(); }, [load, tick]);
  const confirm = async (inv) => {
    try { await api.post(`/invoices/${inv.id}/confirm`); toast.success("Simulated payment confirmed"); await refresh(); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div data-testid="invoices-page">
      <PageHeader eyebrow="Invoices and Fees" title="Demonstration billing" desc="Payment buttons only update simulated records. No card, bank or real payment details are ever requested."
        actions={isAdmin && <Button data-testid="generate-invoice-button" disabled={tx.on_hold || !!tx.completed_at} onClick={() => setGen(true)}>Generate invoice</Button>} />
      <div className="grid gap-6 xl:grid-cols-[1fr_360px]">
        <Panel title="Invoices" sub={tx.reference} testid="invoices-table">
          {invoices.length === 0 ? <Empty testid="invoices-empty">No demonstration invoices yet.</Empty> : (
            <div className="overflow-x-auto">
              <Table className="vb-table">
                <TableHeader><TableRow><TableHead>Invoice</TableHead><TableHead>Tx ref</TableHead><TableHead>Service</TableHead><TableHead>Amount</TableHead><TableHead>Responsible</TableHead><TableHead>Status</TableHead><TableHead>Issued</TableHead><TableHead>Paid</TableHead><TableHead /></TableRow></TableHeader>
                <TableBody>{invoices.map((inv) => <InvoiceRow key={inv.id} inv={inv} user={user} onPay={setPaying} onConfirm={confirm} />)}</TableBody>
              </Table>
            </div>
          )}
        </Panel>
        <FeeConfig fees={fees} setFees={setFees} isAdmin={isAdmin} />
      </div>
      {isAdmin && <GenerateDialog open={gen} onOpenChange={setGen} fees={fees} onDone={load} />}
      <PayDialog open={!!paying} onOpenChange={(o) => !o && setPaying(null)} invoice={paying} onDone={load} />
    </div>
  );
}
