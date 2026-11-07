import { Button } from "@/components/ui/button";
import { useTx } from "@/context/TxContext";
import { useAuth } from "@/context/AuthContext";
import { Panel, StatusPill, KV } from "@/components/common";
import { Stepper } from "@/components/Stepper";
import { NextStep } from "@/components/NextStep";
import { DepositTracker } from "@/components/DepositTracker";
import { NotificationList, useNotifications } from "@/components/Notifications";
import { usd, ethFmt } from "@/lib/fmt";

const Summary = ({ tx }) => {
  const held = tx.deposit.initiated_at && !tx.settlement.approved_at ? tx.eth_quantity : 0;
  return (
    <Panel title="Deal summary" testid="deal-summary">
      <div className="mb-3">
        <div className="eyebrow">Deal value</div>
        <div data-testid="deal-value" className="font-mono text-2xl font-semibold text-white">{usd(tx.usd_value)}</div>
        <div data-testid="deal-eth" className="font-mono text-sm text-sky-300">{ethFmt(tx.eth_quantity, 2)} @ {usd(tx.eth_price, 2)}</div>
      </div>
      <KV label="Sender" value={tx.sender_name} />
      <KV label="Recipient" value={tx.recipient_name} />
      <KV label="Network" value={tx.network} />
      <KV label="Escrow wallet" value={tx.escrow_vault_address || "Set when the escrow opens"} mono testid="escrow-wallet" />
      <KV label="Held in escrow" value={ethFmt(held, 2)} mono testid="escrow-balance" />
      {tx.onboarding.recipient.data?.wallet_address && <KV label="Release to" value={tx.onboarding.recipient.data.wallet_address} mono testid="recipient-wallet" />}
    </Panel>
  );
};

export default function Home() {
  const { tx, act } = useTx();
  const { user } = useAuth();
  const { items } = useNotifications();
  const isAdmin = user.role === "admin";
  return (
    <div data-testid="home-page" className="space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="eyebrow mb-2 text-amber-300/80">Deal</div>
          <h1 data-testid="tx-reference" className="text-3xl font-bold tracking-tight text-white sm:text-4xl">{tx.reference}</h1>
          <p className="mt-1 text-sm text-slate-400">{tx.sender_name} → {tx.recipient_name}</p>
        </div>
        <div className="flex items-center gap-2">
          <StatusPill status={tx.status} testid="deal-status" />
          {isAdmin && !tx.completed_at && (
            <Button size="sm" variant="outline" data-testid="hold-toggle-button" onClick={() => act(tx.on_hold ? "resume" : "hold", {}, tx.on_hold ? "Deal resumed" : "Deal on hold")}>{tx.on_hold ? "Resume" : "Put on hold"}</Button>
          )}
        </div>
      </div>
      <div className="panel p-5"><Stepper tx={tx} /></div>
      <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
        <div className="space-y-6">
          <NextStep />
          {tx.deposit.initiated_at && <DepositTracker tx={tx} />}
        </div>
        <div className="space-y-6">
          <Summary tx={tx} />
          <Panel title="Messages" testid="inbox-panel">
            <div className="-mx-3 max-h-[360px] overflow-y-auto"><NotificationList items={items} limit={8} testid="inbox-list" /></div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
