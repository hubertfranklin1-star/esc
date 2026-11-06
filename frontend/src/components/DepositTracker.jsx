import { KV, Panel, StatusPill } from "@/components/common";
import { ethFmt, dt } from "@/lib/fmt";

export const Confirmations = ({ n, required = 12 }) => (
  <div data-testid="confirmation-tracker">
    <div className="mb-2 flex items-center justify-between">
      <span className="eyebrow">Confirmations</span>
      <span data-testid="confirmation-count" className="font-mono text-sm text-white">{n}/{required}</span>
    </div>
    <div className="grid grid-cols-12 gap-1.5">
      {Array.from({ length: required }).map((_, i) => (
        <div key={i} className={`h-6 rounded-sm border transition-all duration-500 ${i < n ? "border-sky-400/70 bg-sky-400/80" : i === n ? "pulse-ring border-sky-400/40 bg-sky-400/10" : "border-[#26354D] bg-[#0B111E]"}`} />
      ))}
    </div>
  </div>
);

export const DepositTracker = ({ tx }) => {
  const dep = tx.deposit;
  const st = tx.settlement;
  return (
    <Panel title="Deposit" testid="deposit-panel" actions={<StatusPill status={dep.confirmations >= 12 ? "Confirmed" : "Confirming"} testid="deposit-status" />}>
      <Confirmations n={dep.confirmations} />
      <div className="mt-4">
        <KV label="Amount" value={ethFmt(dep.eth_quantity, 6)} mono testid="deposit-qty" />
        <KV label="From wallet" value={dep.from_address} mono testid="deposit-from" />
        <KV label="Escrow wallet" value={dep.to_address} mono testid="deposit-to" />
        <KV label="Transaction hash" value={dep.tx_hash} mono testid="deposit-hash" />
        <KV label="Block" value={dep.block_number?.toLocaleString()} mono testid="deposit-block" />
        <KV label="Network fee" value={ethFmt(dep.network_fee_eth, 6)} mono testid="deposit-fee" />
        <KV label="Time" value={dt(dep.initiated_at)} testid="deposit-timestamp" />
        {st.release_tx_hash && <KV label="Release hash" value={st.release_tx_hash} mono testid="release-hash" />}
      </div>
    </Panel>
  );
};
