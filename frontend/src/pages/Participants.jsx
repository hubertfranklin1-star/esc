import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { PageHeader, Panel, StatusPill, KV } from "@/components/common";
import { useTx } from "@/context/TxContext";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { cap, dt, short } from "@/lib/fmt";

const PartyCard = ({ tx, party, isAdmin, act }) => {
  const inv = tx.invitations[party];
  const ob = tx.onboarding[party];
  return (
    <Panel title={party === "sender" ? "Sender" : "Recipient"} sub={tx[`${party}_name`]} testid={`participant-${party}`}
      actions={<StatusPill status={`Invitation ${inv.status}`} testid={`participant-${party}-invitation`} />}>
      <KV label="Entity" value={tx[`${party}_name`]} />
      <KV label="Demo account" value={tx[`${party}_email`]} mono />
      <KV label="Invitation sent" value={dt(tx.invitations_sent_at)} />
      <KV label="Responded" value={dt(inv.responded_at)} />
      <KV label="Onboarding" value={<StatusPill status={cap(ob.status)} testid={`participant-${party}-onboarding`} />} />
      <KV label="Simulated wallet" value={short(ob.data.wallet_address)} mono sim />
      {isAdmin && inv.status === "declined" && (
        <Button size="sm" className="mt-3" data-testid={`participant-resend-${party}`} onClick={() => act("resend_invitation", { party }, "Invitation re-sent")}>Re-send invitation</Button>
      )}
    </Panel>
  );
};

export default function Participants() {
  const { tx, act } = useTx();
  const { user } = useAuth();
  const isAdmin = user.role === "admin";
  const [users, setUsers] = useState([]);
  useEffect(() => {
    if (isAdmin) api.get("/users").then((r) => setUsers(r.data));
  }, [isAdmin]);
  return (
    <div data-testid="participants-page">
      <PageHeader eyebrow="Participants" title="Escrow participants" desc={`Parties to ${tx.reference}. Invitations are delivered to the in-app inbox as simulated emails.`}
        actions={isAdmin && !tx.invitations_sent_at && <Button data-testid="participants-send-invitations" onClick={() => act("send_invitations", {}, "Simulated invitations sent")}>Invite sender & recipient</Button>} />
      <div className="grid gap-6 lg:grid-cols-2">
        <PartyCard tx={tx} party="sender" isAdmin={isAdmin} act={act} />
        <PartyCard tx={tx} party="recipient" isAdmin={isAdmin} act={act} />
      </div>
      {isAdmin && (
        <Panel title="Platform demo accounts" className="mt-6" testid="platform-users">
          {users.map((u) => <KV key={u.id} label={`${u.name} · ${cap(u.role)}`} value={u.email} mono />)}
        </Panel>
      )}
    </div>
  );
}
