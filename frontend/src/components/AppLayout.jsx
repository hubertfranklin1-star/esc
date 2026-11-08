import { useState } from "react";
import { NavLink, Outlet, Navigate, useLocation, useNavigate } from "react-router-dom";
import {
  Home, ArrowLeftRight, ShieldCheck, Receipt, FileText, ScrollText, Settings, LogOut, Menu, ScanSearch, Users, Inbox,
} from "lucide-react";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";
import { TxProvider, useTx } from "@/context/TxContext";
import { NotificationsBell } from "@/components/Notifications";
import { StatusPill } from "@/components/common";

const NAV = [
  ["/", "Home", Home], ["/deals", "Deals", ArrowLeftRight], ["/payments", "Payments", Receipt],
  ["/documents", "Documents", FileText], ["/forensics", "Forensics", ScanSearch], ["/checks", "Checks", ShieldCheck, "admin"],
  ["/accounts", "Accounts", Users, "admin"], ["/activity", "Activity", ScrollText], ["/settings", "Settings", Settings],
];
const ROLE_LABEL = { admin: "Admin", sender: "Sender", recipient: "Recipient" };
// Pages that still work when no deal is selected (e.g. right after the last deal was deleted).
const NO_DEAL_PAGES = { admin: ["/deals", "/accounts", "/activity", "/settings"], party: ["/settings"] };

const SideNav = ({ onNavigate }) => {
  const { user, logout } = useAuth();
  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-[#26354D] px-5 py-5">
        <div className="flex items-center gap-2.5">
          <img src="/tmx-logo.png" alt="TMX" className="h-9 w-9 rounded-md bg-white object-contain p-0.5" />
          <div>
            <div className="text-sm font-bold tracking-[0.18em] text-white">TSX TRUST</div>
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
      <Select value={selectedId} onValueChange={select} disabled={!list.length}>
        <SelectTrigger data-testid="transaction-selector" className="w-[220px] border-[#26354D] bg-[#111827] font-mono text-[11px] sm:w-[260px] sm:text-xs">
          <SelectValue placeholder={list.length ? "Select deal" : "No deals"} />
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

const NoDeals = () => {
  const { user } = useAuth();
  const nav = useNavigate();
  const isAdmin = user.role === "admin";
  return (
    <section data-testid="no-deals" className="panel rise mx-auto max-w-xl p-8 text-center">
      <Inbox className="mx-auto h-8 w-8 text-sky-300" />
      <h2 className="mt-3 text-xl font-semibold text-white">No deals yet</h2>
      <p className="mt-1 text-sm text-slate-400">
        {isAdmin ? "Create a deal to invite a sender and a recipient." : "You're not on any deal right now. You'll receive an invitation email when the admin adds you to one."}
      </p>
      {isAdmin && <Button className="mt-5" data-testid="no-deals-go-deals" onClick={() => nav("/deals")}>Go to Deals</Button>}
    </section>
  );
};

const Shell = () => {
  const [open, setOpen] = useState(false);
  const { tx, list, loaded } = useTx();
  const { user } = useAuth();
  const { pathname } = useLocation();
  const free = NO_DEAL_PAGES[user.role === "admin" ? "admin" : "party"].includes(pathname);
  const empty = loaded && list.length === 0;
  let body = <div className="text-sm text-slate-400">Loading…</div>;
  if (tx || (free && loaded)) body = <Outlet />;
  else if (empty) body = <NoDeals />;
  return (
    <div className="min-h-screen bg-[#0B111E]">
      <aside className="fixed bottom-0 left-0 top-0 z-40 hidden w-64 border-r border-[#26354D] bg-[#0D1422] lg:block"><SideNav /></aside>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="left" className="w-64 border-[#26354D] bg-[#0D1422] p-0"><SheetTitle className="sr-only">Navigation</SheetTitle><SideNav onNavigate={() => setOpen(false)} /></SheetContent>
      </Sheet>
      <div className="lg:pl-64">
        <TopBar onMenu={() => setOpen(true)} />
        <main className="mx-auto max-w-[1400px] px-4 py-8 md:px-8 md:py-10">{body}</main>
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
