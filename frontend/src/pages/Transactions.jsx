import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { PageHeader, Panel, StatusPill } from "@/components/common";
import { useTx } from "@/context/TxContext";
import { useAuth } from "@/context/AuthContext";
import { api, errMsg } from "@/lib/api";
import { usd, ethFmt, dt } from "@/lib/fmt";
import { useEthPrice, savedAt } from "@/lib/useEthPrice";

const CreateDialog = ({ open, onOpenChange }) => {
  const { loadList, select } = useTx();
  const price = useEthPrice(open);
  const [f, setF] = useState({ usd_value: "250000000", sender_name: "", sender_email: "", recipient_name: "", recipient_email: "" });
  const create = async () => {
    try {
      const r = await api.post("/transactions", { ...f, usd_value: Number(f.usd_value) });
      toast.success(`${r.data.reference} created — invitation emails sent`);
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
    <ConfirmDialog open={open} onOpenChange={onOpenChange} testid="create-tx-dialog" title="New deal"
      description={`An invitation email with the deal details and escrow rules is sent to both parties as soon as you create the deal. ETH amount uses the saved ETH price${price ? `: ${usd(price.usd, 2)} (saved ${savedAt(price.fetched_at)}, updated every ${price.refresh_minutes} minutes)` : ""}.`} confirmLabel="Create deal & send invitations" onConfirm={create}>
      <div className="space-y-3">
        {field("usd_value", "Deal value (USD)", "number")}
        <div className="grid gap-3 sm:grid-cols-2">
          {field("sender_name", "Sender company")}
          {field("sender_email", "Sender email", "email")}
          {field("recipient_name", "Recipient company")}
          {field("recipient_email", "Recipient email", "email")}
        </div>
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
    if (t.id !== tx?.id) select(t.id);
    else await act(t.on_hold ? "resume" : "hold", {}, t.on_hold ? "Deal resumed" : "Deal on hold");
  };
  return (
    <div data-testid="transactions-page">
      <PageHeader title="Deals" desc="Tap a deal to open it."
        actions={isAdmin && <Button data-testid="create-transaction-button" onClick={() => setOpen(true)} className="gap-1.5"><Plus className="h-4 w-4" /> New deal</Button>} />
      <Panel>
        <div className="overflow-x-auto">
          <Table className="vb-table">
            <TableHeader>
              <TableRow><TableHead>Reference</TableHead><TableHead>Parties</TableHead><TableHead>Value</TableHead><TableHead>ETH</TableHead><TableHead>Step</TableHead><TableHead>Status</TableHead><TableHead>Created</TableHead><TableHead /></TableRow>
            </TableHeader>
            <TableBody>
              {list.map((t) => (
                <TableRow key={t.id} data-testid={`tx-row-${t.reference}`} className={`cursor-pointer ${t.id === selectedId ? "bg-sky-500/5" : ""}`} onClick={() => { select(t.id); nav("/"); }}>
                  <TableCell className="font-mono text-xs text-white">{t.reference}</TableCell>
                  <TableCell className="text-xs">{t.sender_name}<div className="text-slate-500">→ {t.recipient_name}</div></TableCell>
                  <TableCell className="font-mono text-xs">{usd(t.usd_value)}</TableCell>
                  <TableCell className="font-mono text-xs">{ethFmt(t.eth_quantity, 2)}</TableCell>
                  <TableCell className="font-mono text-xs">{Math.min(t.current_step, 10)}/10</TableCell>
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
