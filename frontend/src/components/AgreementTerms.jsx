import { usd, ethFmt } from "@/lib/fmt";

export const AgreementTerms = ({ tx }) => (
  <div data-testid="agreement-terms" className="space-y-2 rounded-md border border-[#26354D] bg-[#0B111E] p-4 text-sm leading-relaxed text-slate-300">
    <p><b className="text-white">Who:</b> {tx.sender_name} (sender) and {tx.recipient_name} (recipient). VaultBridge Escrow holds the funds.</p>
    <p><b className="text-white">What:</b> {ethFmt(tx.eth_quantity, 2)} (about {usd(tx.usd_value)}) on {tx.network}.</p>
    <p><b className="text-white">How:</b> The recipient pays the escrow fee, the sender deposits the ETH, we check the deposit, and the funds are released to the recipient when the sender asks.</p>
  </div>
);
