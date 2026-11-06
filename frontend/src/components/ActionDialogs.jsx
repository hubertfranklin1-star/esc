import { useEffect, useState } from "react";
import { toast } from "sonner";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { AgreementTerms } from "@/components/AgreementTerms";
import { Textarea } from "@/components/ui/textarea";
import { KV } from "@/components/common";
import { api, errMsg } from "@/lib/api";
import { usd, ethFmt, short } from "@/lib/fmt";
import { useTx } from "@/context/TxContext";

export const AgreementDialog = ({ open, onOpenChange }) => {
  const { tx, act } = useTx();
  return (
    <ConfirmDialog open={open} onOpenChange={onOpenChange} testid="agreement-dialog" title={`Escrow agreement — ${tx.reference}`}
      description="Review the simulated terms before accepting." checkLabel="I have reviewed the simulated escrow terms and accept them for demonstration purposes."
      confirmLabel="Accept simulated agreement" onConfirm={() => act("accept_agreement", { confirmed: true }, "Simulated agreement accepted")}>
      <AgreementTerms tx={tx} />
    </ConfirmDialog>
  );
};

export const DepositDialog = ({ open, onOpenChange }) => {
  const { tx, act } = useTx();
  return (
    <ConfirmDialog open={open} onOpenChange={onOpenChange} testid="deposit-dialog" title="Initiate simulated ETH deposit"
      description="No wallet connection, signature or private key is used. This only creates fictional records."
      checkLabel="I understand this is a simulated deposit and no real ETH will move." confirmLabel="Initiate simulated deposit"
      onConfirm={() => act("initiate_deposit", { confirmed: true }, "Simulated deposit broadcast to the simulated network")}>
      <div className="rounded-md border border-[#26354D] bg-[#0B111E] p-4">
        <KV label="From (simulated sender wallet)" value={short(tx.onboarding.sender.data.wallet_address)} mono sim />
        <KV label="To (simulated escrow address)" value={short(tx.escrow_vault_address)} mono sim />
        <KV label="Quantity" value={ethFmt(tx.eth_quantity, 6)} mono sim />
        <KV label="Illustrative value" value={`${usd(tx.usd_value)} (fictional)`} mono />
      </div>
    </ConfirmDialog>
  );
};

export const PayDialog = ({ open, onOpenChange, invoice, onDone }) => {
  const { refresh } = useTx();
  const pay = async () => {
    try {
      await api.post(`/invoices/${invoice.id}/pay`);
      toast.success("Simulated payment submitted — no real funds moved");
      await refresh();
      onDone && onDone();
      return true;
    } catch (e) {
      toast.error(errMsg(e));
      return false;
    }
  };
  if (!invoice) return null;
  return (
    <ConfirmDialog open={open} onOpenChange={onOpenChange} testid="pay-dialog" title={`Simulated payment — ${invoice.invoice_number}`}
      description="This only updates a demonstration payment record. No card or bank details are requested or used."
      checkLabel="I confirm this is a simulated payment with no real charge." confirmLabel="Submit simulated payment" onConfirm={pay}>
      <div className="rounded-md border border-[#26354D] bg-[#0B111E] p-4">
        <KV label="Responsible party" value={invoice.responsible_name} />
        <KV label="Amount" value={`${usd(invoice.amount, 2)} (fictional)`} mono />
        <KV label="Method" value="Simulated settlement credit" sim />
      </div>
    </ConfirmDialog>
  );
};

export const EngagementPayDialog = ({ open, onOpenChange }) => {
  const { tx } = useTx();
  const [invoice, setInvoice] = useState(null);
  useEffect(() => {
    if (open && tx.payment.invoice_id) {
      api.get(`/invoices?transaction_id=${tx.id}`).then((r) => setInvoice(r.data.find((i) => i.id === tx.payment.invoice_id)));
    }
  }, [open, tx.id, tx.payment.invoice_id]);
  return <PayDialog open={open && !!invoice} onOpenChange={onOpenChange} invoice={invoice} />;
};

export const SettlementDecisionDialog = ({ open, onOpenChange, decision }) => {
  const { tx, act } = useTx();
  const [note, setNote] = useState("");
  const approve = decision === "approved";
  return (
    <ConfirmDialog open={open} onOpenChange={onOpenChange} testid={approve ? "release-dialog" : "reject-dialog"}
      title={approve ? "Approve simulated release" : "Reject settlement request"}
      description={approve ? `Release ${ethFmt(tx.eth_quantity, 6)} (simulated) from the simulated escrow address to ${tx.recipient_name}.` : "The request returns to the sender for a new submission."}
      checkLabel={approve ? "I authorise this simulated release. No real assets are moved." : undefined}
      confirmLabel={approve ? "Approve release" : "Reject request"}
      onConfirm={() => act("decide_settlement", { decision, note }, approve ? "Simulated release approved" : "Settlement request rejected")}>
      {!approve && <Textarea data-testid="reject-note-input" placeholder="Reason (optional)" value={note} onChange={(e) => setNote(e.target.value)} />}
    </ConfirmDialog>
  );
};
