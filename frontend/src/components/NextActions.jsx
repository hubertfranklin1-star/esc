import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ArrowRight, CheckCircle2, Hourglass } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useTx } from "@/context/TxContext";
import { useAuth } from "@/context/AuthContext";
import { api, errMsg } from "@/lib/api";
import { AgreementDialog, DepositDialog, EngagementPayDialog, SettlementDecisionDialog } from "@/components/ActionDialogs";

export const ENGAGEMENT_ITEMS = ["recipient_onboarding", "escrow_admin", "blockchain_analytics", "compliance", "custody_admin", "settlement_admin"];
const actorLabel = { admin: "the administrator", sender: "the sender", recipient: "the recipient", both: "both parties", network: "the simulated network" };

const adminItems = (tx, s, act, nav, setDlg, apiCall) => {
  const out = [];
  const add = (label, testid, onClick, variant) => out.push({ label, testid, onClick, variant });
  if (tx.on_hold) return [{ label: "Resume transaction", testid: "action-resume", onClick: () => act("resume", {}, "Transaction resumed") }];
  if (s === 2) add("Send invitations", "action-send-invitations", () => act("send_invitations", {}, "Simulated invitation emails sent"));
  ["sender", "recipient"].forEach((p) => tx.invitations[p].status === "declined" && add(`Re-send ${p} invitation`, `action-resend-${p}`, () => act("resend_invitation", { party: p }, "Invitation re-sent")));
  if (["sender", "recipient"].some((p) => tx.onboarding[p].status === "submitted")) add("Review onboarding", "action-review-onboarding", () => nav("/onboarding"));
  if (s === 6 && ["sender", "recipient"].every((p) => tx.onboarding[p].status === "approved")) add("Issue escrow agreement", "action-issue-agreement", () => act("issue_agreement", {}, "Agreement issued for review"));
  if (s === 8) add("Generate engagement invoice", "action-generate-engagement", () => apiCall(() => api.post("/invoices", { transaction_id: tx.id, party: "recipient", kind: "engagement", items: ENGAGEMENT_ITEMS }), "Engagement invoice issued to recipient"));
  if (s === 10) add("Confirm simulated payment", "action-confirm-payment", () => apiCall(() => api.post(`/invoices/${tx.payment.invoice_id}/confirm`), "Simulated payment confirmed"));
  if (s === 13) add("Generate blockchain analysis", "action-generate-analysis", () => act("generate_analysis", {}, "Simulated blockchain analysis generated"));
  if (s === 14) add("Open compliance review", "action-open-compliance", () => nav("/compliance"));
  if (s === 16 && !tx.settlement.requested_at) add("Initiate settlement request", "action-request-settlement", () => act("request_settlement", {}, "Settlement request initiated"));
  if (s === 17) {
    add("Approve simulated release", "action-approve-release", () => setDlg("release"));
    add("Reject settlement", "action-reject-settlement", () => setDlg("reject"), "outline");
  }
  if (s === 19) add("Mark COMPLETED — SIMULATION", "action-complete", () => act("complete", {}, "Transaction completed (simulation)"));
  return out;
};

const partyItems = (tx, s, party, act, nav, setDlg) => {
  const out = [];
  const add = (label, testid, onClick, variant) => out.push({ label, testid, onClick, variant });
  if (tx.on_hold) return out;
  const inv = tx.invitations[party];
  if (tx.invitations_sent_at && inv.status === "pending") {
    add("Accept invitation", "action-accept-invitation", () => act("accept_invitation", {}, "Invitation accepted"));
    add("Decline", "action-decline-invitation", () => act("decline_invitation", {}, "Invitation declined"), "outline");
  }
  if (inv.status === "accepted" && ["not_started", "rejected"].includes(tx.onboarding[party].status)) add("Complete onboarding", "action-go-onboarding", () => nav("/onboarding"));
  if (s === 7 && !tx.agreement[`${party}_accepted_at`]) add("Review & accept agreement", "action-review-agreement", () => setDlg("agreement"));
  if (party === "recipient" && s === 9) add("Pay engagement invoice (simulated)", "action-pay-engagement", () => setDlg("pay"));
  if (party === "sender" && s === 11) add("Initiate simulated ETH deposit", "action-initiate-deposit", () => setDlg("deposit"));
  if (s === 15 && !tx.report_access[party]) add("Access verification reports", "action-go-reports", () => nav("/reports"));
  if (party === "sender" && s === 16 && !tx.settlement.requested_at) add("Initiate settlement request", "action-request-settlement", () => act("request_settlement", {}, "Settlement request initiated"));
  if (party === "recipient" && s === 16 && tx.settlement.requested_at && !tx.settlement.recipient_acknowledged_at) add("Approve settlement request", "action-ack-settlement", () => act("acknowledge_settlement", {}, "Settlement request approved"));
  if (party === "recipient" && s === 18) add("Accept simulated ETH balance", "action-accept-balance", () => act("accept_balance", {}, "Simulated balance credited"));
  return out;
};

export const NextActions = () => {
  const { tx, act, refresh, loadList } = useTx();
  const { user } = useAuth();
  const nav = useNavigate();
  const [dlg, setDlg] = useState(null);
  if (!tx) return null;
  const s = tx.current_step;
  const apiCall = async (fn, ok) => {
    try { await fn(); toast.success(ok); await refresh(); loadList(); } catch (e) { toast.error(errMsg(e)); }
  };
  const items = user.role === "admin" ? adminItems(tx, s, act, nav, setDlg, apiCall) : partyItems(tx, s, user.role, act, nav, setDlg);
  const step = tx.steps[s - 1];
  const close = (o) => !o && setDlg(null);
  return (
    <div data-testid="next-actions-bar" className="panel mb-8 flex flex-col gap-3 border-l-2 border-l-amber-400 p-4 md:flex-row md:items-center md:justify-between">
      <div className="flex items-start gap-3">
        {tx.completed_at ? <CheckCircle2 className="mt-0.5 h-5 w-5 text-emerald-400" /> : <Hourglass className="mt-0.5 h-5 w-5 text-amber-300" />}
        <div>
          <div className="eyebrow">{tx.completed_at ? "Lifecycle complete" : `Step ${s} of 19`}</div>
          <div data-testid="next-actions-message" className="text-sm text-slate-200">
            {tx.completed_at ? "COMPLETED — SIMULATION. Final completion report is available in Reports."
              : tx.on_hold ? "This transaction is on hold by the administrator."
              : items.length ? step.title : `Waiting on ${actorLabel[step.actor]}: ${step.title}`}
          </div>
        </div>
      </div>
      {items.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {items.map((i) => (
            <Button key={i.testid} data-testid={i.testid} variant={i.variant || "default"} onClick={i.onClick} className="gap-1.5">
              {i.label} {!i.variant && <ArrowRight className="h-3.5 w-3.5" />}
            </Button>
          ))}
        </div>
      )}
      <AgreementDialog open={dlg === "agreement"} onOpenChange={close} />
      <DepositDialog open={dlg === "deposit"} onOpenChange={close} />
      <EngagementPayDialog open={dlg === "pay"} onOpenChange={close} />
      <SettlementDecisionDialog open={dlg === "release"} onOpenChange={close} decision="approved" />
      <SettlementDecisionDialog open={dlg === "reject"} onOpenChange={close} decision="rejected" />
    </div>
  );
};
