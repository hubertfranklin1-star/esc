import { useEffect, useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, Hourglass, Shuffle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import { KV } from "@/components/common";
import { AgreementTerms } from "@/components/AgreementTerms";
import { Confirmations } from "@/components/DepositTracker";
import { useTx } from "@/context/TxContext";
import { useAuth } from "@/context/AuthContext";
import { api, errMsg, download } from "@/lib/api";
import { usd, ethFmt } from "@/lib/fmt";

const newWallet = () => "0x" + Array.from(crypto.getRandomValues(new Uint8Array(20))).map((b) => b.toString(16).padStart(2, "0")).join("");
const WHO = { admin: "the admin", sender: "the sender", recipient: "the recipient", both: "both parties" };

const Card = ({ title, text, children, done }) => (
  <section data-testid="next-step-card" className="panel rise border-l-2 border-l-amber-400 p-6">
    <div className="flex items-start gap-3">
      {done ? <CheckCircle2 className="mt-1 h-5 w-5 text-emerald-400" /> : <Hourglass className="mt-1 h-5 w-5 text-amber-300" />}
      <div className="min-w-0 flex-1">
        <div className="eyebrow">What you need to do</div>
        <h2 data-testid="next-step-title" className="mt-1 text-xl font-semibold text-white">{title}</h2>
        {text && <p data-testid="next-step-text" className="mt-1 text-sm text-slate-400">{text}</p>}
        {children && <div className="mt-5">{children}</div>}
      </div>
    </div>
  </section>
);

const JoinForm = ({ tx, party, act }) => {
  const [f, setF] = useState({ legal_name: tx[`${party}_name`], contact_name: "", contact_email: tx[`${party}_email`], wallet_address: newWallet() });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const field = (k, label) => (
    <div className="space-y-1.5"><Label>{label}</Label><Input data-testid={`join-${k}-input`} value={f[k]} onChange={set(k)} className="bg-[#0B111E]" /></div>
  );
  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-2">
        {field("legal_name", "Company name")}
        {field("contact_name", "Your full name")}
        {field("contact_email", "Email")}
        <div className="space-y-1.5">
          <Label>ETH wallet address</Label>
          <div className="flex gap-2">
            <Input data-testid="join-wallet_address-input" value={f.wallet_address} onChange={set("wallet_address")} className="bg-[#0B111E] font-mono text-xs" />
            <Button type="button" variant="outline" title="New address" data-testid="join-generate-wallet" onClick={() => setF({ ...f, wallet_address: newWallet() })}><Shuffle className="h-4 w-4" /></Button>
          </div>
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button data-testid="join-submit-button" onClick={() => act("join", f, "You joined the deal")}>Join the deal</Button>
        {tx.invitations[party].status === "pending" && <Button variant="outline" data-testid="join-decline-button" onClick={() => act("decline", {}, "Invitation declined")}>Decline</Button>}
      </div>
    </div>
  );
};

const SignForm = ({ tx, act }) => {
  const [ok, setOk] = useState(false);
  return (
    <div className="space-y-4">
      <AgreementTerms tx={tx} />
      <label className="flex items-center gap-3 text-sm text-slate-200">
        <Checkbox data-testid="sign-agree-checkbox" checked={ok} onCheckedChange={(v) => setOk(!!v)} /> I agree to these terms
      </label>
      <Button data-testid="sign-submit-button" disabled={!ok} onClick={() => act("sign_agreement", {}, "Agreement signed")}>Sign agreement</Button>
    </div>
  );
};

const useFeeInvoice = (tx) => {
  const [inv, setInv] = useState(null);
  useEffect(() => {
    if (tx.payment.invoice_id) api.get(`/invoices?transaction_id=${tx.id}`).then((r) => setInv(r.data.find((i) => i.id === tx.payment.invoice_id)));
  }, [tx.id, tx.payment.invoice_id, tx.payment.submitted_at]);
  return inv;
};

const InvoiceBox = ({ inv, children }) => (
  <div className="space-y-4">
    <div className="rounded-md border border-[#26354D] bg-[#0B111E] p-4">
      {inv.items.map((l) => <KV key={l.code} label={l.description} value={usd(l.amount)} mono />)}
      <KV label="Total" value={<b data-testid="fee-total">{usd(inv.amount)}</b>} mono />
    </div>
    {children}
  </div>
);

const call = async (fn, ok, refresh) => {
  try { await fn(); toast.success(ok); await refresh(); } catch (e) { toast.error(errMsg(e)); }
};

const PartyStep = ({ tx, party, act, refresh }) => {
  const s = tx.current_step;
  const inv = useFeeInvoice(tx);
  const ob = tx.onboarding[party];
  if (tx.invitations[party].status === "declined") return <Card title="You declined this invitation" text="Ask the admin to re-send it if you change your mind." />;
  if (["not_started", "rejected"].includes(ob.status))
    return (
      <Card title="Join the deal" text={ob.status === "rejected" ? `The admin asked you to update your details${ob.note ? `: ${ob.note}` : "."}` : `You're invited to deal ${tx.reference}. Fill in your details to join.`}>
        <JoinForm tx={tx} party={party} act={act} />
      </Card>
    );
  if (s === 4 && !tx.agreement[`${party}_accepted_at`]) return <Card title="Sign the agreement" text="Read the short terms and sign."><SignForm tx={tx} act={act} /></Card>;
  if (party === "recipient" && s === 5 && inv)
    return (
      <Card title="Pay the escrow fee" text="Pay the fee so the sender can deposit the ETH.">
        <InvoiceBox inv={inv}><Button data-testid="pay-fee-button" onClick={() => call(() => api.post(`/invoices/${inv.id}/pay`), "Payment sent", refresh)}>Pay {usd(inv.amount)}</Button></InvoiceBox>
      </Card>
    );
  if (party === "sender" && s === 7)
    return (
      <Card title="Deposit ETH into escrow" text={`Send ${ethFmt(tx.eth_quantity, 2)} to the escrow wallet.`}>
        <div className="mb-4 rounded-md border border-[#26354D] bg-[#0B111E] p-4">
          <KV label="Amount" value={ethFmt(tx.eth_quantity, 6)} mono />
          <KV label="Escrow wallet" value={tx.escrow_vault_address} mono />
        </div>
        <Button data-testid="deposit-button" onClick={() => act("deposit", {}, "Deposit sent")}>Deposit {ethFmt(tx.eth_quantity, 2)}</Button>
      </Card>
    );
  if (party === "sender" && s === 9)
    return <Card title="Release the funds" text="When you're happy, ask us to release the ETH to the recipient."><Button data-testid="request-release-button" onClick={() => act("request_release", {}, "Release requested")}>Release funds to recipient</Button></Card>;
  const step = tx.steps[s - 1];
  return <Card title="Nothing to do right now" text={`Waiting for ${WHO[step.actor]}: ${step.title.toLowerCase()}.`} />;
};

const PartyBox = ({ tx, p }) => {
  const d = tx.onboarding[p].data;
  return (
    <div data-testid={`approve-${p}-details`} className="rounded-md border border-[#26354D] bg-[#0B111E] p-4">
      <div className="eyebrow mb-1">{p}</div>
      <KV label="Company" value={d.legal_name} />
      <KV label="Contact" value={`${d.contact_name} · ${d.contact_email}`} />
      <KV label="Wallet" value={d.wallet_address} mono />
    </div>
  );
};

const ApproveParties = ({ tx, act }) => {
  const [note, setNote] = useState("");
  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-2"><PartyBox tx={tx} p="sender" /><PartyBox tx={tx} p="recipient" /></div>
      <Button data-testid="approve-parties-button" onClick={() => act("approve_parties", {}, "Both parties approved")}>Approve both</Button>
      <details className="text-sm text-slate-400">
        <summary className="cursor-pointer" data-testid="approve-ask-update-toggle">Something wrong? Ask a party to update their details</summary>
        <div className="mt-3 space-y-2">
          <Textarea data-testid="reject-note-input" placeholder="What needs fixing?" value={note} onChange={(e) => setNote(e.target.value)} className="bg-[#0B111E]" />
          <div className="flex gap-2">
            <Button variant="outline" size="sm" data-testid="reject-sender-button" onClick={() => act("reject_party", { party: "sender", note }, "Sender asked to update")}>Ask sender</Button>
            <Button variant="outline" size="sm" data-testid="reject-recipient-button" onClick={() => act("reject_party", { party: "recipient", note }, "Recipient asked to update")}>Ask recipient</Button>
          </div>
        </div>
      </details>
    </div>
  );
};

const AdminStep = ({ tx, act, refresh }) => {
  const s = tx.current_step;
  const inv = useFeeInvoice(tx);
  if (tx.on_hold) return <Card title="This deal is on hold" text="Resume it to continue."><Button data-testid="resume-button" onClick={() => act("resume", {}, "Deal resumed")}>Resume deal</Button></Card>;
  const declined = ["sender", "recipient"].filter((p) => tx.invitations[p].status === "declined");
  if (declined.length)
    return (
      <Card title="An invitation was declined" text="Re-send it to continue.">
        {declined.map((p) => <Button key={p} className="mr-2" data-testid={`resend-${p}-button`} onClick={() => act("resend_invitation", { party: p }, "Invitation re-sent")}>Re-send to {p}</Button>)}
      </Card>
    );
  if (s <= 2) return <Card title="Waiting for both parties to join" text={`Sender: ${tx.onboarding.sender.status === "not_started" ? "not joined yet" : "joined"} · Recipient: ${tx.onboarding.recipient.status === "not_started" ? "not joined yet" : "joined"}`} />;
  if (s === 3) return <Card title="Approve both parties" text="Check their details, then approve."><ApproveParties tx={tx} act={act} /></Card>;
  if (s === 6 && inv)
    return (
      <Card title="Confirm the fee payment" text="The recipient has paid. Confirm you received it.">
        <InvoiceBox inv={inv}><Button data-testid="confirm-fee-button" onClick={() => call(() => api.post(`/invoices/${inv.id}/confirm`), "Payment confirmed", refresh)}>Confirm payment</Button></InvoiceBox>
      </Card>
    );
  if (s === 8) {
    const ready = tx.deposit.confirmations >= 12;
    return (
      <Card title="Verify the deposit" text={ready ? "The deposit is confirmed. Approve the checks to hold it in escrow." : "Waiting for the deposit to confirm…"}>
        <Confirmations n={tx.deposit.confirmations} />
        <Button className="mt-4" disabled={!ready} data-testid="verify-deposit-button" onClick={() => act("verify_deposit", {}, "Deposit verified")}>Verify & approve checks</Button>
      </Card>
    );
  }
  if (s === 10)
    return (
      <Card title="Release the funds" text={`The sender asked to release ${ethFmt(tx.eth_quantity, 2)} to ${tx.recipient_name}.`}>
        <div className="flex gap-2">
          <Button data-testid="release-approve-button" onClick={() => act("release", { decision: "approved" }, "Funds released — deal completed")}>Release funds</Button>
          <Button variant="outline" data-testid="release-decline-button" onClick={() => act("release", { decision: "rejected" }, "Release request declined")}>Decline</Button>
        </div>
      </Card>
    );
  const step = tx.steps[s - 1];
  return <Card title="Nothing to do right now" text={`Waiting for ${WHO[step.actor]}: ${step.title.toLowerCase()}.`} />;
};

export const NextStep = () => {
  const { tx, act, refresh } = useTx();
  const { user } = useAuth();
  if (tx.completed_at)
    return (
      <Card done title="Deal completed" text={`${ethFmt(tx.eth_quantity, 2)} was released to ${tx.recipient_name}.`}>
        <Button variant="outline" data-testid="download-final-button" onClick={() => download(`/reports/${tx.id}/final/pdf`, `${tx.reference}-final.pdf`)}>Download final statement</Button>
      </Card>
    );
  if (user.role === "admin") return <AdminStep tx={tx} act={act} refresh={refresh} />;
  if (tx.on_hold) return <Card title="This deal is on hold" text="The admin has paused this deal." />;
  return <PartyStep tx={tx} party={user.role} act={act} refresh={refresh} />;
};
