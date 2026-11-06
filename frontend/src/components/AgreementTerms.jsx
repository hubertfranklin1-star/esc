import { usd, ethFmt } from "@/lib/fmt";

export const AgreementTerms = ({ tx }) => (
  <div data-testid="agreement-terms" className="space-y-3 rounded-md border border-[#26354D] bg-[#0B111E] p-4 text-sm leading-relaxed text-slate-300">
    <div className="eyebrow text-amber-300">Simulated escrow agreement — demonstration only</div>
    <p><b className="text-white">Parties.</b> {tx.sender_name} ("Sender") and {tx.recipient_name} ("Recipient"), with VaultBridge Escrow (simulated) as escrow agent.</p>
    <p><b className="text-white">Asset.</b> {ethFmt(tx.eth_quantity, 6)} (simulated) with an illustrative value of {usd(tx.usd_value)} (fictional) on {tx.network}.</p>
    <p><b className="text-white">Deposit.</b> Sender deposits the simulated ETH quantity into the simulated escrow address after the engagement invoice is confirmed as paid (simulated).</p>
    <p><b className="text-white">Release conditions.</b> Release requires 12 simulated confirmations, a simulated blockchain analysis, a completed simulated AML review, a settlement request acknowledged by the Recipient, and administrator approval.</p>
    <p><b className="text-white">Fees.</b> Demonstration fees are set by the administrator and invoiced to the responsible party. No real charges are made.</p>
    <p className="text-xs text-amber-200/80">This agreement is fictional and has no legal effect. No real assets, custody, payments or compliance approvals are involved.</p>
  </div>
);
