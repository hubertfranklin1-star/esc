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
      toast.success("Demo reset — VB-ETH-2026-001 restored to Awaiting onboarding");
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
        <Panel title="Simulation parameters" testid="settings-params">
          <KV label="Mode" value="SIMULATION ONLY" />
          <KV label="Illustrative ETH price" value="$2,350.00 (fixed, fictional)" mono />
          <KV label="Required simulated confirmations" value="12" mono />
          <KV label="Network" value="Ethereum Mainnet (simulated only)" />
          <KV label="Real wallets, payments or blockchain" value="Never connected" />
          {user.role === "admin" && <Button variant="outline" size="sm" className="mt-3" data-testid="settings-go-fees" onClick={() => nav("/invoices")}>Configure demonstration fees</Button>}
        </Panel>
        {user.role === "admin" && (
          <Panel title="Reset demonstration" sub="Deletes all simulated transactions, invoices, notifications, uploads and logs, restores default fees, and re-creates VB-ETH-2026-001." testid="settings-reset" className="lg:col-span-2">
            <Button variant="destructive" data-testid="reset-demo-button" onClick={() => setOpen(true)} className="gap-1.5"><RotateCcw className="h-4 w-4" /> Reset demo</Button>
          </Panel>
        )}
      </div>
      <ConfirmDialog open={open} onOpenChange={setOpen} testid="reset-dialog" title="Reset the demonstration?" description="All simulated records will be removed and the default transaction restored. Demo accounts are kept."
        checkLabel="I understand all simulated history will be cleared." confirmLabel="Reset demo" onConfirm={reset} />
    </div>
  );
}
