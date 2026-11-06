import { useNavigate } from "react-router-dom";
import { useTx } from "@/context/TxContext";
import { useAuth } from "@/context/AuthContext";
import { PageHeader, Panel, StatCard, StatusPill, KV, SimTag } from "@/components/common";
import { WorkflowTimeline } from "@/components/WorkflowTimeline";
import { NotificationList, useNotifications } from "@/components/Notifications";
import { usd, ethFmt, short, cap } from "@/lib/fmt";

const Balances = ({ tx }) => {
  const held = tx.deposit.initiated_at && !tx.settlement.approved_at ? tx.eth_quantity : 0;
  return (
    <Panel title="Simulated balances" sub="Fictional wallet positions" testid="balances-panel">
      <KV label="Sender wallet" value={ethFmt(tx.sender_wallet_balance, 4)} mono sim testid="sender-balance" />
      <KV label="Escrow (held)" value={ethFmt(held, 4)} mono sim testid="escrow-balance" />
      <KV label="Recipient wallet" value={ethFmt(tx.recipient_wallet_balance, 4)} mono sim testid="recipient-balance" />
    </Panel>
  );
};

const Details = ({ tx }) => (
  <Panel title="Transaction details" testid="tx-details-panel" actions={<SimTag>Fictional data</SimTag>}>
    <KV label="Reference" value={tx.reference} mono sim testid="tx-reference" />
    <KV label="Asset" value={tx.asset} />
    <KV label="Network" value={tx.network} />
    <KV label="Sender" value={tx.sender_name} />
    <KV label="Recipient" value={tx.recipient_name} />
    <KV label="Simulated escrow address" value={short(tx.escrow_vault_address)} mono sim />
    <KV label="Sender invitation" value={<StatusPill status={cap(tx.invitations.sender.status)} />} />
    <KV label="Recipient invitation" value={<StatusPill status={cap(tx.invitations.recipient.status)} />} />
  </Panel>
);

export default function Overview() {
  const { tx } = useTx();
  const { user } = useAuth();
  const { items } = useNotifications();
  const nav = useNavigate();
  const done = tx.steps.filter((s) => s.done).length;
  const roleTitle = { admin: "Administrator dashboard", sender: "Sender dashboard", recipient: "Recipient dashboard" }[user.role];
  return (
    <div data-testid="overview-page">
      <PageHeader eyebrow={roleTitle} title={tx.reference} desc={`${tx.sender_name} → ${tx.recipient_name} · ${tx.network}. All figures are fictional demonstration data.`}
        actions={<StatusPill status={tx.status} testid="overview-status" />} />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Illustrative value" value={usd(tx.usd_value)} sub="USD · fictional" accent="gold" testid="stat-usd-value" />
        <StatCard label="Simulated quantity" value={ethFmt(tx.eth_quantity, 2)} sub="ETH · simulated" testid="stat-eth-quantity" delay={60} />
        <StatCard label="Illustrative ETH price" value={usd(tx.eth_price, 2)} sub="Fixed demonstration rate" testid="stat-eth-price" delay={120} />
        <StatCard label="Workflow progress" value={`${done} / 19`} sub={tx.completed_at ? "COMPLETED — SIMULATION" : `Current: step ${tx.current_step}`} accent="gold" testid="stat-progress" delay={180} />
      </div>
      <div className="mt-6 grid gap-6 xl:grid-cols-[1fr_380px]">
        <Panel title="Transaction lifecycle" sub="Each stage requires the responsible user's action" testid="lifecycle-panel">
          <WorkflowTimeline tx={tx} />
        </Panel>
        <div className="space-y-6">
          <Balances tx={tx} />
          <Panel title="Inbox" sub="Simulated emails & alerts" testid="inbox-panel"
            actions={<button className="text-xs text-sky-300 hover:underline" onClick={() => nav("/audit")} data-testid="inbox-view-audit">Audit log →</button>}>
            <div className="-mx-3 max-h-[340px] overflow-y-auto"><NotificationList items={items} limit={8} testid="inbox-list" /></div>
          </Panel>
        </div>
      </div>
      <div className="mt-6"><Details tx={tx} /></div>
    </div>
  );
}
