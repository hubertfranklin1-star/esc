import { PageHeader, Panel, KV, StatusPill, StatCard } from "@/components/common";
import { useTx } from "@/context/TxContext";
import { ethFmt, dt, cap, short } from "@/lib/fmt";

const STAGES = [16, 17, 18, 19];

export default function Settlement() {
  const { tx } = useTx();
  const st = tx.settlement;
  const held = tx.deposit.initiated_at && !st.approved_at ? tx.eth_quantity : 0;
  return (
    <div data-testid="settlement-page">
      <PageHeader eyebrow="Settlement" title="Simulated settlement" desc="Release requires a settlement request, recipient approval, and administrator authorisation. Use the action bar above for your next step."
        actions={<StatusPill status={cap(st.status === "none" ? "Not requested" : st.status.replace("_", " "))} testid="settlement-status" />} />
      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label="Simulated escrow held" value={ethFmt(held, 4)} sub="Simulated" testid="settlement-escrow-held" />
        <StatCard label="Recipient simulated balance" value={ethFmt(tx.recipient_wallet_balance, 4)} sub="Updates when the recipient accepts the release" accent="gold" testid="settlement-recipient-balance" />
        <StatCard label="Sender simulated balance" value={ethFmt(tx.sender_wallet_balance, 4)} sub="Simulated" testid="settlement-sender-balance" />
      </div>
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Panel title="Settlement stages" testid="settlement-stages">
          {STAGES.map((n) => {
            const s = tx.steps[n - 1];
            return (
              <div key={n} className="flex items-center justify-between border-b border-[#26354D]/60 py-3 last:border-0">
                <span className="text-sm text-slate-200"><span className="mr-2 font-mono text-xs text-slate-500">{n}</span>{s.title}</span>
                <StatusPill status={s.done ? "Completed" : n === tx.current_step ? "Awaiting" : "Pending"} testid={`settlement-stage-${n}`} />
              </div>
            );
          })}
        </Panel>
        <Panel title="Settlement record" testid="settlement-record">
          <KV label="Requested by" value={st.requested_by} />
          <KV label="Requested at" value={dt(st.requested_at)} />
          <KV label="Recipient approved" value={dt(st.recipient_acknowledged_at)} />
          <KV label="Administrator approved" value={dt(st.approved_at)} />
          <KV label="Simulated release hash" value={short(st.release_tx_hash)} mono sim />
          <KV label="Balance credited" value={dt(st.credited_at)} />
          {st.status === "rejected" && <KV label="Rejection note" value={st.note || "—"} />}
          <KV label="Completed" value={tx.completed_at ? `${dt(tx.completed_at)} — COMPLETED — SIMULATION` : "—"} testid="settlement-completed" />
        </Panel>
      </div>
    </div>
  );
}
