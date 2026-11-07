import { usd, ethFmt } from "@/lib/fmt";

const RULES = (tx) => [
  ["Escrow wallet", `When both parties are approved, the escrow opens with VaultBridge's escrow wallet on ${tx.network}. All deposits and fees go to this wallet.`],
  ["Onboarding fee", "Each party pays a one-time onboarding fee in ETH before the escrow opens. It covers identity, company and wallet due diligence for a high-value deal."],
  ["Deposit", `The sender deposits ${ethFmt(tx.eth_quantity, 2)} (about ${usd(tx.usd_value)}) from their registered wallet. The transaction hash is checked on-chain, or the admin confirms receipt.`],
  ["AML checks", "Every deposit is screened on-chain: the sending wallet's history, its counterparties, sanctions lists and links to mixers or high-risk services."],
  ["AML report", "When the checks pass, the admin releases the AML report. Both parties can view it on the Forensics page."],
  ["Escrow fees", "When the recipient requests the funds, the escrow fees are split 50/50 between the sender and the recipient, priced in ETH at the current market price (saved every 5 minutes). Each party pays their half to the escrow wallet."],
  ["Release", "When both halves are paid, the admin releases the ETH to the recipient's registered wallet and the escrow is closed. The release is final once confirmed on-chain."],
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
