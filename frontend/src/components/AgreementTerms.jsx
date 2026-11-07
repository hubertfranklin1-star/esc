import { usd, ethFmt } from "@/lib/fmt";

const RULES = (tx) => [
  ["Escrow wallet", `VaultBridge holds the deposit in a dedicated escrow wallet on ${tx.network}. Neither party can move it alone.`],
  ["Onboarding fee", "Each party pays a one-time onboarding fee in ETH before the escrow opens. It covers identity, company and wallet due diligence for a high-value deal."],
  ["Deposit", `The sender deposits ${ethFmt(tx.eth_quantity, 2)} (about ${usd(tx.usd_value)}). The deposit counts as received after 12 block confirmations.`],
  ["AML checks", "Every deposit is screened on-chain: the sending wallet's history, its counterparties, sanctions lists and links to mixers or high-risk services."],
  ["AML report", "When the checks pass, the admin releases the AML report. Both parties can view it on the Forensics page."],
  ["Withdrawal", "The recipient requests the funds. A withdrawal AML check is run on the receiving wallet, and the escrow fees are settled at this point, not before."],
  ["Release", "After withdrawal AML and fees are complete, the admin releases the ETH to the recipient's wallet. The release is final once confirmed on-chain."],
  ["Disputes", "If a check fails or details are wrong, the admin can pause the deal, ask a party to update their details, or decline the release."],
];

export const AgreementTerms = ({ tx }) => (
  <div data-testid="agreement-terms" className="space-y-2 rounded-md border border-[#26354D] bg-[#0B111E] p-4 text-sm leading-relaxed text-slate-300">
    <div className="eyebrow mb-1">Escrow rules — {tx.reference}</div>
    <p><b className="text-white">Parties:</b> {tx.sender_name} (sender) and {tx.recipient_name} (recipient).</p>
    <ol className="list-decimal space-y-1.5 pl-5">
      {RULES(tx).map(([k, v]) => <li key={k}><b className="text-white">{k}:</b> {v}</li>)}
    </ol>
  </div>
);
