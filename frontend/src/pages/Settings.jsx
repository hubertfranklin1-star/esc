import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { PageHeader, Panel, KV } from "@/components/common";
import { useAuth } from "@/context/AuthContext";
import { useTx } from "@/context/TxContext";
import { api, errMsg } from "@/lib/api";
import { cap } from "@/lib/fmt";

export default function SettingsPage() {
  const { user } = useAuth();
  const { loadList, select } = useTx();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const reset = async () => {
    try {
      await api.post("/admin/reset");
      const l = await loadList();
      select(l[0].id);
      toast.success("Demo reset — VB-ETH-2026-001 is back at the start");
      nav("/");
      return true;
    } catch (e) { toast.error(errMsg(e)); return false; }
  };
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
      <ConfirmDialog open={open} onOpenChange={setOpen} testid="reset-dialog" title="Reset the demo?" description="Everything is cleared and the starting deal is created again. Accounts are kept."
        checkLabel="I understand all history will be cleared." confirmLabel="Reset demo" onConfirm={reset} />
    </div>
  );
}
