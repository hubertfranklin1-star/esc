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
import { usd, dt, cap, ethExact } from "@/lib/fmt";

const amt = (inv, v = inv.amount) => (inv.currency === "ETH" ? ethExact(v) : usd(v, 2));
const KIND = { engagement: "Escrow fee", onboarding: "Onboarding fee" };

const OnboardingFee = ({ isAdmin }) => {
  const [v, setV] = useState("");
  const [w, setW] = useState("");
  useEffect(() => { api.get("/onboarding-fee").then((r) => { setV(r.data.amount_eth); setW(r.data.wallet || ""); }); }, []);
  const save = async () => {
    try { await api.put("/onboarding-fee", { amount_eth: Number(v), ...(w.trim() ? { wallet: w.trim() } : {}) }); toast.success("Onboarding fee saved"); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <Panel title="Onboarding fee" sub="Paid by each party when they join" testid="onboarding-fee-config" actions={isAdmin && <Button size="sm" data-testid="onboarding-fee-save" onClick={save}>Save</Button>}>
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm text-white">Per party</span>
        {isAdmin ? <Input type="number" min="0" step="0.1" data-testid="onboarding-fee-input" value={v} onChange={(e) => setV(e.target.value)} className="h-8 w-32 bg-[#0B111E] text-right font-mono text-xs" />
          : <span data-testid="onboarding-fee-value" className="font-mono text-sm">{ethExact(v)}</span>}
      </div>
      <div className="mt-3 space-y-1.5">
        <span className="text-sm text-white">Pay-to wallet</span>
        {isAdmin ? <Input data-testid="fee-wallet-input" value={w} onChange={(e) => setW(e.target.value)} placeholder="0x… your receiving wallet" className="h-8 bg-[#0B111E] px-2 font-mono text-[10px]" />
          : <div data-testid="fee-wallet-value" className="break-all font-mono text-xs text-slate-300">{w || "Not set yet"}</div>}
      </div>
      {isAdmin && <p className="mt-2 text-[11px] text-slate-500">The amount applies to parties who join after you save. Parties send the fee to this wallet.</p>}
    </Panel>
  );
};

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
  const [items, setItems] = useState([]);
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
    <TableCell className="font-mono text-xs text-white">{inv.invoice_number}{KIND[inv.kind] && <div className="text-[10px] text-amber-300">{KIND[inv.kind]}</div>}</TableCell>
    <TableCell className="max-w-[240px] text-xs text-slate-300">{inv.items.map((l) => l.description).join(", ")}</TableCell>
    <TableCell className="font-mono text-xs">{amt(inv)}</TableCell>
    <TableCell className="text-xs">{inv.responsible_name}<div className="text-slate-500">{cap(inv.party)}</div></TableCell>
    <TableCell>
      <StatusPill status={inv.status} testid={`invoice-status-${inv.invoice_number}`} />
      {inv.verified_onchain && <a data-testid={`invoice-tx-${inv.invoice_number}`} href={`https://etherscan.io/tx/${inv.payment_tx_hash}`} target="_blank" rel="noreferrer" className="mt-1 block text-[10px] text-emerald-300 underline">Verified on-chain</a>}
      {inv.verified_onchain && inv.payment_from_matches === false && user.role === "admin" && <div data-testid={`invoice-from-warning-${inv.invoice_number}`} className="mt-0.5 text-[10px] text-amber-300">Sent from another wallet</div>}
    </TableCell>
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
      <div className="grid gap-6 xl:grid-cols-[1fr_340px] [&>*]:min-w-0">
        <Panel title="Invoices" testid="invoices-table">
          {invoices.length === 0 ? <Empty testid="invoices-empty">No invoices yet. Onboarding fee invoices are created when each party joins; the escrow fee invoice when the recipient requests the funds.</Empty> : (
            <div className="overflow-x-auto">
              <Table className="vb-table">
                <TableHeader><TableRow><TableHead>Invoice</TableHead><TableHead>For</TableHead><TableHead>Amount</TableHead><TableHead>Billed to</TableHead><TableHead>Status</TableHead><TableHead>Issued</TableHead><TableHead>Paid</TableHead><TableHead /></TableRow></TableHeader>
                <TableBody>{invoices.map((inv) => <Row key={inv.id} inv={inv} user={user} run={run} />)}</TableBody>
              </Table>
            </div>
          )}
        </Panel>
        <div className="space-y-6"><OnboardingFee isAdmin={isAdmin} /><Fees fees={fees} setFees={setFees} isAdmin={isAdmin} /></div>
      </div>
      {isAdmin && <NewInvoice open={open} onOpenChange={setOpen} fees={fees} onDone={load} />}
    </div>
  );
}
