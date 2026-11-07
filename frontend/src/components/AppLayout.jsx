import { useState } from "react";
import { NavLink, Outlet, Navigate } from "react-router-dom";
import {
  Home, ArrowLeftRight, ShieldCheck, Receipt, FileText, ScrollText, Settings, LogOut, Menu, ScanSearch,
} from "lucide-react";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAuth } from "@/context/AuthContext";
import { TxProvider, useTx } from "@/context/TxContext";
import { NotificationsBell } from "@/components/Notifications";
import { StatusPill } from "@/components/common";

const NAV = [
  ["/", "Home", Home], ["/deals", "Deals", ArrowLeftRight], ["/payments", "Payments", Receipt],
  ["/documents", "Documents", FileText], ["/forensics", "Forensics", ScanSearch], ["/checks", "Checks", ShieldCheck, "admin"], ["/activity", "Activity", ScrollText], ["/settings", "Settings", Settings],
];
const ROLE_LABEL = { admin: "Admin", sender: "Sender", recipient: "Recipient" };

const SideNav = ({ onNavigate }) => {
  const { user, logout } = useAuth();
  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-[#26354D] px-5 py-5">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-sm border border-amber-400/50 bg-amber-400/10 font-mono text-sm font-bold text-amber-300">VB</div>
          <div>
            <div className="text-sm font-bold tracking-[0.18em] text-white">VAULTBRIDGE</div>
            <div className="font-mono text-[10px] tracking-[0.3em] text-sky-300">ESCROW</div>
          </div>
        </div>
      </div>
      <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-4">
        {NAV.filter((n) => !n[3] || n[3] === user.role).map(([to, label, Icon]) => (
          <NavLink key={to} to={to} end={to === "/"} onClick={onNavigate} data-testid={`nav-${label.toLowerCase()}`}
            className={({ isActive }) => `flex items-center gap-3 rounded-md px-3 py-2.5 text-sm transition-colors duration-200 ${isActive ? "bg-sky-500/10 text-white shadow-[inset_2px_0_0_#38BDF8]" : "text-slate-400 hover:bg-[#182235] hover:text-slate-200"}`}>
            <Icon className="h-4 w-4" /> {label}
          </NavLink>
        ))}
      </nav>
      <div className="border-t border-[#26354D] p-4">
        <div data-testid="current-user-name" className="truncate text-sm font-medium text-white">{user.name}</div>
        <div className="truncate text-xs text-slate-400">{user.email}</div>
        <div className="mt-2 flex items-center justify-between">
          <span data-testid="current-user-role" className="rounded-sm bg-amber-400/10 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-amber-300">{ROLE_LABEL[user.role]}</span>
          <button data-testid="logout-button" onClick={logout} className="flex items-center gap-1 text-xs text-slate-400 transition-colors hover:text-white"><LogOut className="h-3.5 w-3.5" /> Sign out</button>
        </div>
      </div>
    </div>
  );
};

const TopBar = ({ onMenu }) => {
  const { list, tx, selectedId, select } = useTx();
  return (
    <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-[#26354D] bg-[#0B111E]/85 px-4 py-3 backdrop-blur-xl md:px-8">
      <button data-testid="mobile-menu-button" onClick={onMenu} className="rounded-md border border-[#26354D] p-2 lg:hidden"><Menu className="h-4 w-4" /></button>
      <Select value={selectedId} onValueChange={select}>
        <SelectTrigger data-testid="transaction-selector" className="w-[220px] border-[#26354D] bg-[#111827] font-mono text-[11px] sm:w-[260px] sm:text-xs">
          <SelectValue placeholder="Select deal" />
        </SelectTrigger>
        <SelectContent>
          {list.map((t) => <SelectItem key={t.id} value={t.id} data-testid={`transaction-option-${t.reference}`} className="font-mono text-xs">{t.reference}</SelectItem>)}
        </SelectContent>
      </Select>
      {tx && <div className="hidden md:block"><StatusPill status={tx.status} testid="topbar-tx-status" /></div>}
      <div className="ml-auto"><NotificationsBell /></div>
    </header>
  );
};

const Shell = () => {
  const [open, setOpen] = useState(false);
  const { tx } = useTx();
  return (
    <div className="min-h-screen bg-[#0B111E]">
      <aside className="fixed bottom-0 left-0 top-0 z-40 hidden w-64 border-r border-[#26354D] bg-[#0D1422] lg:block"><SideNav /></aside>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="left" className="w-64 border-[#26354D] bg-[#0D1422] p-0"><SheetTitle className="sr-only">Navigation</SheetTitle><SideNav onNavigate={() => setOpen(false)} /></SheetContent>
      </Sheet>
      <div className="lg:pl-64">
        <TopBar onMenu={() => setOpen(true)} />
        <main className="mx-auto max-w-[1400px] px-4 py-8 md:px-8 md:py-10">
          {tx ? <Outlet /> : <div className="text-sm text-slate-400">Loading…</div>}
        </main>
      </div>
    </div>
  );
};

export default function AppLayout() {
  const { user, ready } = useAuth();
  if (!ready) return null;
  if (!user) return <Navigate to="/login" replace />;
  return <TxProvider key={user.id}><Shell /></TxProvider>;
}
