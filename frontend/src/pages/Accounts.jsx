import { useCallback, useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { AlertTriangle, Lock, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { PageHeader, Panel, Empty, KV } from "@/components/common";
import { useAuth } from "@/context/AuthContext";
import { useTx } from "@/context/TxContext";
import { api, errMsg } from "@/lib/api";
import { dt, cap } from "@/lib/fmt";

const ROLE_TONE = {
  admin: "border-amber-400/40 bg-amber-400/10 text-amber-300",
  sender: "border-sky-400/40 bg-sky-400/10 text-sky-300",
  recipient: "border-emerald-400/40 bg-emerald-400/10 text-emerald-300",
};
const RoleTag = ({ role }) => (
  <span className={`inline-flex rounded-sm border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider ${ROLE_TONE[role] || ""}`}>{role}</span>
);

const ERASED = [
  ["invoices", "invoice", "invoices"],
  ["uploaded_reports", "document", "documents"],
  ["notifications", "message", "messages"],
  ["forensic_scans", "wallet scan", "wallet scans"],
  ["audit_logs", "activity entry", "activity entries"],
];
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

const DealChip = ({ d, onOpen }) => (
  <button type="button" data-testid={`account-deal-${d.reference}`} onClick={() => onOpen(d.id)}
    className={`rounded-sm border px-2 py-1 text-left transition-colors hover:bg-[#182235] ${d.in_escrow ? "border-amber-400/50" : "border-[#26354D]"}`}>
    <div className="font-mono text-[11px] text-white">{d.reference}</div>
    <div className={`text-[10px] ${d.in_escrow ? "text-amber-300" : "text-slate-500"}`}>{d.in_escrow ? "ETH in escrow" : d.status}</div>
  </button>
);

const DeleteDialog = ({ account, onClose, onDeleted }) => {
  const [p, setP] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    if (!account) return;
    setP(null);
    setErr("");
    api.get(`/accounts/${account.id}/deletion-preview`).then((r) => setP(r.data)).catch((e) => setErr(errMsg(e)));
  }, [account]);
  const run = async () => {
    try {
      const r = await api.delete(`/accounts/${account.id}`);
      const n = r.data.counts.deals;
      toast.success(`Account deleted${n ? ` together with ${plural(n, "deal", "deals")}` : ""}`);
      await onDeleted();
      return true;
    } catch (e) {
      toast.error(errMsg(e));
      return false;
    }
  };
  const blocked = (p?.blocked || []).length > 0;
  const c = p?.counts || {};
  return (
    <ConfirmDialog open={!!account} onOpenChange={(v) => { if (!v) onClose(); }} danger testid="delete-account-dialog"
      title={`Delete ${account?.name || "this"}'s account?`} description="Everything about this account is erased for good. This can't be undone."
      confirmLabel="Delete everything" disabled={!p || blocked} onConfirm={run}
      checkLabel="I understand this permanently erases this account and every deal listed below, for both parties.">
      <div className="space-y-4">
        <div className="rounded-md border border-[#26354D] bg-[#0B111E] px-4 py-1">
          <KV label="Name" value={account?.name} />
          <KV label="Email" value={account?.email} mono />
          <KV label="Role" value={cap(account?.role)} />
        </div>
        {!p && !err && <p data-testid="delete-preview-loading" className="text-sm text-slate-400">Checking what will be deleted…</p>}
        {err && <p data-testid="delete-preview-error" className="text-sm text-red-300">{err}</p>}
        {blocked && (
          <div data-testid="delete-blocked" className="flex gap-3 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-100">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-300" />
            <div>
              <div className="font-semibold">Can't delete yet</div>
              ETH is held in escrow on {p.blocked.map((d) => d.reference).join(", ")}. Release the funds to the recipient first, then delete the account.
            </div>
          </div>
        )}
        {p && !blocked && (
          <div data-testid="delete-preview" className="space-y-3 text-sm">
            <div className="eyebrow">This permanently erases</div>
            <ul className="space-y-1.5 text-slate-200">
              <li>• Their login: they're signed out straight away and can't sign in again</li>
              <li data-testid="delete-count-deals">
                • {c.deals ? <><b className="text-white">{plural(c.deals, "deal", "deals")}</b>, completely and for both parties</> : "No deals: they aren't on any deal"}
              </li>
              {ERASED.map(([k, one, many]) => (
                <li key={k} data-testid={`delete-count-${k}`}>• {plural(c[k] || 0, one, many)}</li>
              ))}
            </ul>
            {p.deals.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {p.deals.map((d) => (
                  <span key={d.id} className="rounded-sm border border-red-500/30 bg-red-500/5 px-2 py-0.5 font-mono text-[11px] text-red-200">
                    {d.reference} · {d.sender_name} → {d.recipient_name}
                  </span>
                ))}
              </div>
            )}
            <p className="text-xs text-slate-400">
              Their email can be invited again as a brand-new person. Activity keeps one note, “A {account?.role} account was deleted”, with no name or email.
            </p>
          </div>
        )}
      </div>
    </ConfirmDialog>
  );
};

export default function Accounts() {
  const { user } = useAuth();
  const { select, resync } = useTx();
  const nav = useNavigate();
  const [rows, setRows] = useState(null);
  const [q, setQ] = useState("");
  const [target, setTarget] = useState(null);
  const isAdmin = user.role === "admin";
  const load = useCallback(() => api.get("/accounts").then((r) => setRows(r.data)).catch((e) => toast.error(errMsg(e))), []);
  useEffect(() => { if (isAdmin) load(); }, [isAdmin, load]);
  if (!isAdmin) return <Navigate to="/" replace />;

  const open = (id) => { select(id); nav("/"); };
  const shown = (rows || []).filter((a) => !q || `${a.name} ${a.email} ${a.organisation} ${a.role}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <div data-testid="accounts-page">
      <PageHeader eyebrow="Admin" title="Accounts" desc="Everyone who can sign in. Deleting a sender or recipient erases their account and every deal they're on, for both parties." />
      <Input data-testid="accounts-search-input" placeholder="Search name, email or company…" value={q} onChange={(e) => setQ(e.target.value)} className="mb-4 max-w-sm bg-[#111827]" />
      <Panel testid="accounts-list" title={rows ? `${shown.length} account${shown.length === 1 ? "" : "s"}` : "Accounts"}>
        {!rows ? <div className="text-sm text-slate-400">Loading…</div> : shown.length === 0 ? <Empty testid="accounts-empty">No accounts match your search.</Empty> : (
          <div>
            <div className="hidden border-b border-[#26354D] pb-2 text-[11px] uppercase tracking-wider text-slate-500 md:flex">
              <div className="w-[34%]">Account</div><div className="w-[12%]">Role</div><div className="flex-1">Deals</div><div className="w-[140px] text-right">Action</div>
            </div>
            {shown.map((a) => (
              <div key={a.id} data-testid={`account-row-${a.email}`} className="flex flex-col gap-3 border-b border-[#26354D]/60 py-4 last:border-0 md:flex-row md:items-center">
                <div className="min-w-0 md:w-[34%] md:pr-4">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-medium text-white">{a.name}</span>
                    {a.is_you && <span className="rounded-sm bg-sky-400/10 px-1.5 py-0.5 text-[10px] text-sky-300">You</span>}
                  </div>
                  <div className="truncate font-mono text-xs text-slate-400">{a.email}</div>
                  <div className="truncate text-[11px] text-slate-500">{a.organisation} · joined {dt(a.created_at)}</div>
                </div>
                <div className="md:w-[12%]"><RoleTag role={a.role} /></div>
                <div className="flex min-w-0 flex-1 flex-wrap gap-1.5">
                  {a.deals.length ? a.deals.map((d) => <DealChip key={d.id} d={d} onOpen={open} />) : <span className="text-xs text-slate-500">{a.role === "admin" ? "Runs all deals" : "No deals"}</span>}
                </div>
                <div className="md:w-[140px] md:text-right">
                  {a.deletable ? (
                    <Button size="sm" variant="outline" data-testid={`account-delete-${a.email}`} onClick={() => setTarget(a)}
                      className="gap-1.5 border-red-500/40 text-red-300 hover:bg-red-500/10 hover:text-red-200">
                      <Trash2 className="h-3.5 w-3.5" /> Delete
                    </Button>
                  ) : (
                    <span data-testid={`account-protected-${a.email}`} className="inline-flex items-center gap-1 text-xs text-slate-500"><Lock className="h-3.5 w-3.5" /> {a.is_you ? "Your account" : "Protected"}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>
      <DeleteDialog account={target} onClose={() => setTarget(null)} onDeleted={async () => { await load(); await resync(); }} />
    </div>
  );
}
