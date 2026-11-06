import { useState } from "react";
import { Shuffle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { PageHeader, Panel, StatusPill, KV, Empty, SimTag } from "@/components/common";
import { AgreementTerms } from "@/components/AgreementTerms";
import { useTx } from "@/context/TxContext";
import { useAuth } from "@/context/AuthContext";
import { cap, dt } from "@/lib/fmt";

const simWallet = () => "0x" + Array.from(crypto.getRandomValues(new Uint8Array(20))).map((b) => b.toString(16).padStart(2, "0")).join("");
const FIELDS = [
  ["legal_name", "Legal entity name (fictional)"], ["registration_number", "Registration number (fictional)"], ["jurisdiction", "Jurisdiction"],
  ["contact_name", "Authorised contact"], ["contact_email", "Contact email (fictional)"], ["beneficial_owner", "Beneficial owner (fictional)"],
];

const OnboardingForm = ({ tx, party, act }) => {
  const [f, setF] = useState({
    legal_name: tx[`${party}_name`], registration_number: `DEMO-${party === "sender" ? "INV" : "ACQ"}-${Math.floor(100000 + Math.random() * 899999)}`,
    jurisdiction: "Demonstration Jurisdiction", contact_name: "", contact_email: tx[`${party}_email`], beneficial_owner: "Demo Holding Trust (fictional)",
    business_description: "", wallet_address: simWallet(), fictional_confirmed: false,
  });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  return (
    <Panel title={party === "recipient" ? "Company onboarding (simulated)" : "Investor onboarding (simulated)"} sub="Use fictional demonstration data only" testid="onboarding-form">
      <div className="grid gap-4 md:grid-cols-2">
        {FIELDS.map(([k, label]) => (
          <div key={k} className="space-y-1.5"><Label>{label}</Label><Input data-testid={`onboarding-${k}-input`} value={f[k]} onChange={set(k)} className="bg-[#0B111E]" /></div>
        ))}
        <div className="space-y-1.5 md:col-span-2">
          <Label className="flex items-center gap-2">Demonstration wallet address <SimTag /></Label>
          <div className="flex gap-2">
            <Input data-testid="onboarding-wallet_address-input" value={f.wallet_address} onChange={set("wallet_address")} className="bg-[#0B111E] font-mono text-xs" />
            <Button type="button" variant="outline" data-testid="onboarding-generate-wallet" onClick={() => setF({ ...f, wallet_address: simWallet() })}><Shuffle className="h-4 w-4" /></Button>
          </div>
          <p className="text-[11px] text-amber-300/80">Never enter a real wallet address or private key. A random simulated address is generated for you.</p>
        </div>
        <div className="space-y-1.5 md:col-span-2"><Label>Business description</Label><Textarea data-testid="onboarding-business_description-input" value={f.business_description} onChange={set("business_description")} className="bg-[#0B111E]" /></div>
      </div>
      <label className="mt-4 flex items-start gap-3 text-sm text-slate-300">
        <Checkbox data-testid="onboarding-fictional-checkbox" checked={f.fictional_confirmed} onCheckedChange={(v) => setF({ ...f, fictional_confirmed: !!v })} className="mt-0.5" />
        I confirm all information is fictional demonstration data.
      </label>
      <Button className="mt-4" data-testid="onboarding-submit-button" onClick={() => act("submit_onboarding", f, "Simulated onboarding submitted")}>Submit onboarding</Button>
    </Panel>
  );
};

const Submitted = ({ tx, party, isAdmin, act }) => {
  const ob = tx.onboarding[party];
  const [note, setNote] = useState("");
  return (
    <Panel title={`${cap(party)} onboarding`} sub={tx[`${party}_name`]} testid={`onboarding-${party}-panel`} actions={<StatusPill status={cap(ob.status)} testid={`onboarding-${party}-status`} />}>
      {ob.status === "not_started" ? <Empty>Not yet submitted by the {party}.</Empty> : (
        <>
          {[...FIELDS, ["wallet_address", "Simulated wallet"], ["business_description", "Business description"]].map(([k, l]) => (
            <KV key={k} label={l} value={ob.data[k] || "—"} mono={k === "wallet_address"} sim={k === "wallet_address"} />
          ))}
          <KV label="Submitted" value={dt(ob.submitted_at)} />
          <KV label="Reviewed" value={dt(ob.reviewed_at)} />
          {ob.note && <KV label="Reviewer note" value={ob.note} />}
        </>
      )}
      {isAdmin && ob.status === "submitted" && (
        <div className="mt-4 space-y-2">
          <Textarea data-testid={`onboarding-${party}-review-note`} placeholder="Review note (optional)" value={note} onChange={(e) => setNote(e.target.value)} className="bg-[#0B111E]" />
          <div className="flex gap-2">
            <Button data-testid={`onboarding-${party}-approve`} onClick={() => act("review_onboarding", { party, decision: "approved", note }, "Onboarding approved (simulated)")}>Simulated approval</Button>
            <Button variant="outline" data-testid={`onboarding-${party}-reject`} onClick={() => act("review_onboarding", { party, decision: "rejected", note }, "Onboarding rejected (simulated)")}>Reject</Button>
          </div>
        </div>
      )}
    </Panel>
  );
};

export default function Onboarding() {
  const { tx, act } = useTx();
  const { user } = useAuth();
  const isAdmin = user.role === "admin";
  const party = isAdmin ? null : user.role;
  const canSubmit = party && tx.invitations[party].status === "accepted" && ["not_started", "rejected"].includes(tx.onboarding[party].status);
  const bothApproved = ["sender", "recipient"].every((p) => tx.onboarding[p].status === "approved");
  return (
    <div data-testid="onboarding-page">
      <PageHeader eyebrow="Onboarding" title="Simulated onboarding" desc="Onboarding outcomes are demonstration results only and are not real KYC/KYB approvals."
        actions={isAdmin && bothApproved && !tx.agreement.issued_at && <Button data-testid="onboarding-issue-agreement" onClick={() => act("issue_agreement", {}, "Agreement issued for review")}>Issue escrow agreement</Button>} />
      {party && !canSubmit && tx.invitations[party].status !== "accepted" && <Empty testid="onboarding-locked">Accept your escrow invitation to begin onboarding.</Empty>}
      {canSubmit && <OnboardingForm tx={tx} party={party} act={act} />}
      {party && tx.onboarding[party].status === "rejected" && <p className="mt-2 text-sm text-red-300">Your previous submission was rejected: {tx.onboarding[party].note || "no reason given"}. Please resubmit.</p>}
      <div className={`grid gap-6 ${isAdmin ? "lg:grid-cols-2" : ""} ${canSubmit ? "mt-6" : ""}`}>
        {(isAdmin ? ["sender", "recipient"] : party && !canSubmit && tx.onboarding[party].status !== "not_started" ? [party] : []).map((p) => (
          <Submitted key={p} tx={tx} party={p} isAdmin={isAdmin} act={act} />
        ))}
      </div>
      {tx.agreement.issued_at && (
        <Panel title="Escrow agreement" className="mt-6" testid="agreement-panel"
          actions={<div className="flex gap-2"><StatusPill status={tx.agreement.sender_accepted_at ? "Sender accepted" : "Sender pending"} /><StatusPill status={tx.agreement.recipient_accepted_at ? "Recipient accepted" : "Recipient pending"} /></div>}>
          <AgreementTerms tx={tx} />
        </Panel>
      )}
    </div>
  );
}
