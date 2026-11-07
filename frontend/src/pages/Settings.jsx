import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { PageHeader, Panel, KV } from "@/components/common";
import { useAuth } from "@/context/AuthContext";
import { cap } from "@/lib/fmt";

export default function SettingsPage() {
  const { user } = useAuth();
  const nav = useNavigate();
  return (
    <div data-testid="settings-page">
      <PageHeader eyebrow="Settings" title="Settings" />
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Account" testid="settings-account">
          <KV label="Name" value={user.name} />
          <KV label="Email" value={user.email} mono />
          <KV label="Role" value={cap(user.role)} />
          <KV label="Organisation" value={user.organisation} />
        </Panel>
        <Panel title="Escrow settings" testid="settings-params">
          <KV label="Deal pricing" value="Live ETH price when a deal is created" />
          <KV label="Escrow fees" value="Split 50/50, live ETH price" />
          <KV label="Network" value="Ethereum Mainnet" />
          {user.role === "admin" && <Button variant="outline" size="sm" className="mt-3" data-testid="settings-go-fees" onClick={() => nav("/payments")}>Edit fees</Button>}
        </Panel>
      </div>
    </div>
  );
}
