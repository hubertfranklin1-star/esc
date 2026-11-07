import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { CheckCircle2, Copy, Hourglass } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import { KV } from "@/components/common";
import { AgreementTerms } from "@/components/AgreementTerms";
import { useTx } from "@/context/TxContext";
import { useAuth } from "@/context/AuthContext";
import { api, errMsg, download } from "@/lib/api";
import { usd, ethFmt, ethExact } from "@/lib/fmt";

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
  const prev = tx.onboarding[party].data || {};
  const { user } = useAuth();
  const [f, setF] = useState({ legal_name: prev.legal_name || tx[`${party}_name`], contact_name: prev.contact_name || user?.name || "", contact_email: prev.contact_email || tx[`${party}_email`], wallet_address: prev.wallet_address || "" });
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
          <Label>Your ETH wallet address</Label>
          <Input data-testid="join-wallet_address-input" value={f.wallet_address} onChange={set("wallet_address")} placeholder="0x… a wallet you control" className="bg-[#0B111E] font-mono text-xs" />
          <p className="text-[11px] text-slate-500">{party === "recipient" ? "The escrow funds are released to this wallet — double-check it." : "Send the deposit from this wallet."}</p>
        </div>
      </div>
      <AgreementTerms tx={tx} />
      <label className="flex items-center gap-3 text-sm text-slate-200">
        <Checkbox data-testid="join-rules-checkbox" checked={!!f.rules_accepted} onCheckedChange={(v) => setF({ ...f, rules_accepted: !!v })} /> I have read and accept the escrow rules
      </label>
      <div className="flex flex-wrap gap-2">
        <Button data-testid="join-submit-button" disabled={!f.rules_accepted} onClick={() => act("join", f, "You joined the deal")}>Enter the escrow</Button>
        {tx.invitations[party].status === "pending" && <Button variant="outline" data-testid="join-decline-button" onClick={() => act("decline", {}, "Invitation declined")}>Decline</Button>}
      </div>
    </div>
  );
};

const useInvoice = (tx, id, stamp) => {
  const [inv, setInv] = useState(null);
  useEffect(() => {
    if (id) api.get(`/invoices?transaction_id=${tx.id}`).then((r) => setInv(r.data.find((i) => i.id === id)));
  }, [tx.id, id, stamp]);
  return inv;
};
const fee = (inv, v = inv.amount) => (inv.currency === "ETH" ? ethExact(v) : usd(v));

const InvoiceBox = ({ inv, children }) => (
  <div className="space-y-4">
    <div className="rounded-md border border-[#26354D] bg-[#0B111E] p-4">
      {inv.items.map((l) => <KV key={l.code} label={l.description} value={fee(inv, l.amount)} mono />)}
      <KV label="Total" value={<b data-testid="fee-total">{fee(inv)}</b>} mono />
    </div>
    {children}
  </div>
);

const call = async (fn, ok, refresh) => {
  try { await fn(); toast.success(ok); await refresh(); } catch (e) { toast.error(errMsg(e)); }
};

const PayBox = ({ amount, wallet, onPay, manualLabel, prefix = "fee" }) => {
  const [hash, setHash] = useState("");
  const [busy, setBusy] = useState(false);
  const pay = async (body) => { setBusy(true); await onPay(body); setBusy(false); };
  return (
    <div className="space-y-4">
      <div className="rounded-md border border-sky-400/40 bg-sky-400/5 p-4">
        <div className="eyebrow mb-2">Send exactly {amount} on Ethereum mainnet to</div>
        <div className="flex items-center gap-2">
          <code data-testid={`${prefix}-wallet-address`} className="break-all font-mono text-sm text-white">{wallet}</code>
          <Button size="sm" variant="outline" data-testid={`${prefix}-wallet-copy`} onClick={() => { navigator.clipboard?.writeText(wallet); toast.success("Wallet address copied"); }}><Copy className="h-3.5 w-3.5" /></Button>
        </div>
      </div>
      <div className="space-y-1.5">
        <Label>Transaction hash</Label>
        <Input data-testid={`${prefix}-tx-hash-input`} value={hash} onChange={(e) => setHash(e.target.value.trim())} placeholder="0x… (64 characters)" className="bg-[#0B111E] font-mono text-xs" />
        <p className="text-[11px] text-slate-500">Paste it after sending; we check it on Etherscan and mark it paid straight away.</p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button data-testid={`${prefix}-verify-button`} disabled={busy || !hash} onClick={() => pay({ tx_hash: hash })}>{busy ? "Checking…" : "Verify payment"}</Button>
        <Button variant="outline" data-testid={`${prefix}-manual-button`} disabled={busy} onClick={() => pay({})}>{manualLabel}</Button>
      </div>
    </div>
  );
};

const InvoicePay = ({ inv, refresh, prefix }) => {
  const [wallet, setWallet] = useState(null);
  useEffect(() => { api.get("/onboarding-fee").then((r) => setWallet(r.data.wallet || "")); }, []);
  if (wallet === null) return null;
  if (!wallet) return <p data-testid="fee-wallet-missing" className="text-sm text-amber-300">The admin hasn't set the payment wallet yet. You'll be able to pay as soon as it's added.</p>;
  return <PayBox prefix={prefix} amount={fee(inv)} wallet={wallet} manualLabel="I've paid — admin will confirm"
    onPay={(body) => call(() => api.post(`/invoices/${inv.id}/pay`, body), body.tx_hash ? "Payment verified on-chain" : "Marked as paid — the admin will confirm", refresh)} />;
};

const shareState = (s) => (s?.verified ? "Paid · verified on-chain" : s?.confirmed_at ? "Paid · confirmed" : s?.submitted_at ? "Paid · awaiting confirmation" : "Not paid yet");

export const FeeSplit = ({ tx }) => {
  const sf = tx.settlement_fees || {};
  if (!sf.sender) return null;
  const pr = tx.settlement_fee_price || {};
  return (
    <div data-testid="fee-split" className="mb-4 rounded-md border border-[#26354D] bg-[#0B111E] p-4">
      <div className="eyebrow mb-2">Escrow fees — split 50/50</div>
      {["sender", "recipient"].map((p) => (
        <div key={p} data-testid={`fee-split-${p}`} className="flex flex-wrap items-center justify-between gap-2 border-b border-[#26354D]/60 py-2 last:border-0">
          <div><div className="text-sm text-white">{tx[`${p}_name`]}</div><div className="text-[11px] capitalize text-slate-500">{p}</div></div>
          <div className="text-right">
            <div className="font-mono text-sm text-white">{ethExact(sf[p].eth_amount)}</div>
            <div className="font-mono text-[11px] text-slate-400">{usd(sf[p].usd_amount)}</div>
            <div data-testid={`fee-split-${p}-status`} className={`text-[11px] ${sf[p].submitted_at ? "text-emerald-300" : "text-amber-300"}`}>{shareState(sf[p])}</div>
          </div>
        </div>
      ))}
      {pr.eth_usd && <p className="mt-2 text-[11px] text-slate-500">Priced at {usd(pr.eth_usd, 2)} per ETH (live market price when the funds were requested).</p>}
    </div>
  );
};

const PartyStep = ({ tx, party, act, refresh }) => {
  const s = tx.current_step;
  const sf = tx.settlement_fees?.[party] || {};
  const inv = useInvoice(tx, sf.invoice_id, sf.submitted_at);
  const of = tx.onboarding_fees?.[party] || {};
  const obInv = useInvoice(tx, of.invoice_id, of.submitted_at);
  const ob = tx.onboarding[party];
  if (tx.invitations[party].status === "declined") return <Card title="You declined this invitation" text="Ask the admin to re-send it if you change your mind." />;
  if (!tx.invitations_sent_at) return <Card title="No invitation yet" text="You'll receive an invitation email from VaultBridge Escrow when the admin opens this deal." />;
  if (["not_started", "rejected"].includes(ob.status))
    return (
      <Card title="Join the deal" text={ob.status === "rejected" ? `The admin asked you to update your details${ob.note ? `: ${ob.note}` : "."}` : `You're invited to deal ${tx.reference}. Fill in your details to join.`}>
        <JoinForm tx={tx} party={party} act={act} />
      </Card>
    );
  if (s <= 3 && obInv && !of.submitted_at)
    return (
      <Card title="Pay the onboarding fee" text="Because of the size of this deal, each party pays an onboarding fee to open their escrow account. Both parties must pay before the admin can approve.">
        <InvoiceBox inv={obInv}><InvoicePay inv={obInv} refresh={refresh} prefix="fee" /></InvoiceBox>
      </Card>
    );
  if (party === "sender" && s === 5)
    return (
      <Card title="Deposit ETH into escrow" text={`The escrow is open. Send ${ethExact(tx.eth_quantity)} from your registered wallet to the escrow wallet below.`}>
        <PayBox prefix="deposit" amount={ethExact(tx.eth_quantity)} wallet={tx.escrow_vault_address} manualLabel="I've sent it — admin will confirm"
          onPay={(body) => act("deposit", body, body.tx_hash ? "Deposit verified on-chain" : "Deposit marked as sent — the admin will confirm")} />
      </Card>
    );
  if (party === "recipient" && s === 8)
    return (
      <Card title="Request your funds" text={`The AML report has been released (see Forensics). When you request the funds, the escrow fees are split 50/50 between you and the sender at the live ETH price. Funds go to ${tx.onboarding.recipient.data.wallet_address}.`}>
        <Button data-testid="request-release-button" onClick={() => act("request_release", {}, "Funds requested — escrow fees are now due")}>Request {ethFmt(tx.eth_quantity, 2)}</Button>
      </Card>
    );
  if (s === 9 && inv && !sf.submitted_at)
    return (
      <Card title="Pay your half of the escrow fees" text="The escrow fees are shared equally between the sender and the recipient. Once both halves are paid, the admin releases the funds and closes the escrow.">
        <FeeSplit tx={tx} />
        <InvoiceBox inv={inv}><InvoicePay inv={inv} refresh={refresh} prefix="share" /></InvoiceBox>
      </Card>
    );
  if (s >= 9 && sf.submitted_at)
    return <Card title="Your half of the escrow fees is paid" text={s === 9 ? "Waiting for the other party to pay their half." : "Both halves are paid. Waiting for the admin to release the funds."}><FeeSplit tx={tx} /></Card>;
  const step = tx.steps[s - 1];
  if (s === 3 && of.submitted_at)
    return <Card title="Your onboarding fee is paid" text={of.confirmed_at ? "Payment confirmed. Waiting for the other party to pay theirs." : "The admin will confirm your payment. Waiting for the other party to pay too."} />;
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
      <KV label="Onboarding fee" value={tx.onboarding_fees?.[p]?.submitted_at ? "Paid" : "Not paid"} testid={`approve-${p}-fee`} />
      <WalletScan tx={tx} p={p} />
    </div>
  );
};

const BAND = { Low: "text-emerald-300", Medium: "text-amber-300", High: "text-orange-400", Severe: "text-red-400" };

const WalletScan = ({ tx, p }) => {
  const { act } = useTx();
  const s = tx.onboarding[p].scan;
  if (!s) return null;
  return (
    <div data-testid={`approve-${p}-scan`} className="mt-3 rounded border border-[#26354D] bg-[#111827] p-3 text-xs">
      <div className="eyebrow mb-1">Wallet forensic scan</div>
      {s.status === "running" && <div data-testid={`approve-${p}-scan-running`} className="flex items-center gap-2 text-slate-300"><Hourglass className="h-3.5 w-3.5 animate-pulse text-sky-300" /> Scanning the wallet on Ethereum mainnet…</div>}
      {s.status === "failed" && (
        <div className="space-y-2">
          <div data-testid={`approve-${p}-scan-error`} className="text-red-300">Scan failed: {s.error}</div>
          <Button size="sm" variant="outline" data-testid={`approve-${p}-rescan`} onClick={() => act("rescan_wallet", { party: p }, "Scan restarted")}>Scan again</Button>
        </div>
      )}
      {s.status === "done" && (
        <div className="space-y-1">
          <div data-testid={`approve-${p}-scan-risk`}>Risk: <span className={`font-semibold ${BAND[s.band] || "text-white"}`}>{s.band}</span> ({s.score}/100)</div>
          <div data-testid={`approve-${p}-scan-sanctions`} className={s.sanctioned ? "font-semibold text-red-400" : "text-slate-300"}>{s.sanctioned ? "Sanctions list match" : "No sanctions list match"}</div>
          <div className="text-slate-400">Balance: {ethFmt(s.balance_eth)}</div>
          <button type="button" data-testid={`approve-${p}-scan-pdf`} className="text-sky-300 underline" onClick={() => download(`/forensics/scans/${s.scan_id}/pdf`, `wallet-due-diligence-${p}.pdf`)}>Download wallet report (PDF)</button>
        </div>
      )}
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

const InviteForm = ({ tx }) => {
  const { refresh } = useTx();
  const [e, setE] = useState({ sender: tx.invite_emails?.sender || "", recipient: tx.invite_emails?.recipient || "" });
  const [busy, setBusy] = useState(false);
  const send = async () => {
    setBusy(true);
    try { await api.post(`/transactions/${tx.id}/send-invitations`, e); toast.success("Invitation emails sent"); await refresh(); } catch (err) { toast.error(errMsg(err)); }
    setBusy(false);
  };
  return (
    <div className="space-y-3">
      <div className="grid gap-3 md:grid-cols-2">
        {["sender", "recipient"].map((p) => (
          <div key={p} className="space-y-1.5"><Label>{p === "sender" ? `Sender email — ${tx.sender_name}` : `Recipient email — ${tx.recipient_name}`}</Label>
            <Input type="email" data-testid={`invite-${p}-email-input`} value={e[p]} onChange={(ev) => setE({ ...e, [p]: ev.target.value })} className="bg-[#0B111E]" /></div>
        ))}
      </div>
      <Button data-testid="send-invitations-button" disabled={busy} onClick={send}>{busy ? "Sending…" : tx.invitations_sent_at ? "Re-send invitation emails" : "Send invitation emails"}</Button>
      <p className="text-[11px] text-slate-500">The email shows the deal details and escrow rules, with a button to enter the escrow.</p>
    </div>
  );
};

const ReleaseCard = ({ tx, act }) => {
  const [hash, setHash] = useState("");
  const { refresh } = useTx();
  const to = tx.onboarding.recipient.data.wallet_address;
  const sf = tx.settlement_fees;
  const pending = ["sender", "recipient"].filter((p) => !sf[p].confirmed_at);
  return (
    <Card title="Release the funds & close the escrow" text={pending.length ? "Both parties say they've paid their half. Check each payment reached your wallet and confirm it before releasing." : `Both halves of the escrow fees are paid. Send ${ethExact(tx.eth_quantity)} to ${tx.recipient_name}, then record the release.`}>
      <FeeSplit tx={tx} />
      {pending.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-2">
          {pending.map((p) => <Button key={p} variant="outline" data-testid={`release-confirm-${p}`} onClick={() => call(() => api.post(`/invoices/${sf[p].invoice_id}/confirm`), `${p} payment confirmed`, refresh)}>Confirm {p} payment received</Button>)}
        </div>
      )}
      <div className="mb-4 space-y-1.5">
        <KV label="Recipient wallet" value={to} mono testid="release-recipient-wallet" />
        <Label>Release transaction hash (optional)</Label>
        <Input data-testid="release-tx-hash-input" value={hash} onChange={(e) => setHash(e.target.value.trim())} placeholder="0x… checked on Etherscan if provided" className="bg-[#0B111E] font-mono text-xs" />
      </div>
      <div className="flex flex-wrap gap-2">
        <Button data-testid="release-approve-button" disabled={pending.length > 0} onClick={() => act("release", { decision: "approved", tx_hash: hash }, "Funds released — escrow closed")}>Release funds & close</Button>
        <Button variant="outline" data-testid="release-decline-button" onClick={() => act("release", { decision: "rejected" }, "Release request declined")}>Decline</Button>
      </div>
    </Card>
  );
};

const AdminStep = ({ tx, act }) => {
  const s = tx.current_step;
  const nav = useNavigate();
  if (tx.on_hold) return <Card title="This deal is on hold" text="Resume it to continue."><Button data-testid="resume-button" onClick={() => act("resume", {}, "Deal resumed")}>Resume deal</Button></Card>;
  const declined = ["sender", "recipient"].filter((p) => tx.invitations[p].status === "declined");
  if (declined.length)
    return (
      <Card title="An invitation was declined" text="Re-send it to continue.">
        {declined.map((p) => <Button key={p} className="mr-2" data-testid={`resend-${p}-button`} onClick={() => act("resend_invitation", { party: p }, "Invitation re-sent")}>Re-send to {p}</Button>)}
      </Card>
    );
  const joinState = (p) => ({ not_started: "not joined yet", rejected: "asked to update" }[tx.onboarding[p].status] || "joined");
  if (!tx.invitations_sent_at) return <Card title="Invite both parties by email" text="Onboarding starts with an invitation email to the sender and the recipient."><InviteForm tx={tx} /></Card>;
  if (s <= 2) return <Card title="Waiting for both parties to join" text={`Invitations sent. Sender: ${joinState("sender")} · Recipient: ${joinState("recipient")}`}><InviteForm tx={tx} /></Card>;
  const feeState = (p) => (tx.onboarding_fees?.[p]?.submitted_at ? "paid" : "not paid yet");
  if (s === 3) return <Card title="Waiting for onboarding fees" text={`Sender: ${feeState("sender")} · Recipient: ${feeState("recipient")}`} />;
  if (s === 4) return <Card title="Approve both parties" text="Both onboarding fees are paid. Check their details, then approve to open the escrow."><ApproveParties tx={tx} act={act} /></Card>;
  if (s === 6) {
    const dep = tx.deposit;
    return (
      <Card title="Confirm the deposit & run AML checks" text={dep.verified_onchain ? `The deposit of ${ethExact(dep.eth_quantity)} was verified on-chain (block ${dep.block_number}). Complete the AML checks (see the Checks page).` : `The sender says they sent ${ethExact(dep.eth_quantity)} to ${dep.to_address}. Check it arrived in your wallet before completing the AML checks.`}>
        <Button data-testid="verify-deposit-button" onClick={() => act("verify_deposit", {}, "AML checks completed")}>{dep.verified_onchain ? "Complete AML checks" : "Deposit received — complete AML checks"}</Button>
      </Card>
    );
  }
  if (s === 7)
    return (
      <Card title="Release the AML report" text="Upload the AML / forensic documents on the Forensics page, then release them to the parties.">
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" data-testid="go-forensics-button" onClick={() => nav("/forensics")}>Open Forensics</Button>
          <Button data-testid="release-aml-report-button" onClick={() => act("release_aml_report", {}, "AML report released")}>Release AML report</Button>
        </div>
      </Card>
    );
  if (s === 9) return <Card title="Waiting for the escrow fees" text="Each party pays half. Confirm manual payments on the Payments page once they reach your wallet."><FeeSplit tx={tx} /></Card>;
  if (s === 10) return <ReleaseCard tx={tx} act={act} />;
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
