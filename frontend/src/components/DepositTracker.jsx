import { KV, Panel, StatusPill } from "@/components/common";
import { ethExact, dt } from "@/lib/fmt";

const Hash = ({ h, testid }) => (
  <a data-testid={testid} href={`https://etherscan.io/tx/${h}`} target="_blank" rel="noreferrer" className="break-all font-mono text-xs text-sky-300 underline">{h}</a>
);

export const DepositTracker = ({ tx }) => {
  const dep = tx.deposit;
  const st = tx.settlement;
  const status = dep.verified_onchain ? "Verified on-chain" : dep.confirmed_at ? "Confirmed" : "Awaiting confirmation";
  return (
    <Panel title="Deposit" testid="deposit-panel" actions={<StatusPill status={status} testid="deposit-status" />}>
      <KV label="Amount" value={ethExact(dep.eth_quantity)} mono testid="deposit-qty" />
      <KV label="From wallet" value={dep.from_address} mono testid="deposit-from" />
      <KV label="Escrow wallet" value={dep.to_address} mono testid="deposit-to" />
      {dep.tx_hash && <KV label="Transaction" value={<Hash h={dep.tx_hash} testid="deposit-hash" />} />}
      {dep.block_number && <KV label="Block" value={dep.block_number.toLocaleString()} mono testid="deposit-block" />}
      <KV label="Sent" value={dt(dep.initiated_at)} testid="deposit-timestamp" />
      {st.release_tx_hash && <KV label="Release" value={<Hash h={st.release_tx_hash} testid="release-hash" />} />}
    </Panel>
  );
};
