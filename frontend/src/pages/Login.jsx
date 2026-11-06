import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { KeyRound, ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/context/AuthContext";
import { errMsg } from "@/lib/api";
import { SimBanner } from "@/components/AppLayout";

const DEMO = [
  { role: "Administrator", email: "admin@vaultbridge.demo", password: "AdminDemo#2026", org: "VaultBridge Escrow (Simulated)" },
  { role: "Sender", email: "sender@vaultbridge.demo", password: "SenderDemo#2026", org: "Demo Investment Entity" },
  { role: "Recipient", email: "recipient@vaultbridge.demo", password: "RecipientDemo#2026", org: "Demo Acquisition Company" },
];

export default function Login() {
  const { user, login } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to="/" replace />;

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await login(email, password);
      nav("/");
    } catch (err) {
      toast.error(errMsg(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#0B111E] pt-9">
      <SimBanner />
      <div className="grid min-h-[calc(100vh-2.25rem)] lg:grid-cols-[1.1fr_1fr]">
        <div className="grain relative hidden overflow-hidden lg:block">
          <img src="/vault.jpg" alt="Ethereum emblem" className="absolute inset-0 h-full w-full object-cover opacity-40" />
          <div className="absolute inset-0 bg-gradient-to-t from-[#0B111E] via-[#0B111E]/70 to-[#0B111E]/30" />
          <div className="relative flex h-full flex-col justify-end p-14">
            <div className="eyebrow text-amber-300">Institutional digital asset escrow · demonstration</div>
            <h1 className="mt-4 max-w-xl text-5xl font-bold leading-tight tracking-tight text-white">VaultBridge Escrow</h1>
            <p className="mt-4 max-w-md text-sm leading-relaxed text-slate-300">
              A closed simulation of a high-value ETH escrow lifecycle — invitation, onboarding, simulated deposit, compliance review and settlement. Every value is fictional.
            </p>
            <div className="mt-8 flex gap-6 font-mono text-xs text-slate-400">
              <span>19 workflow stages</span><span>3 role dashboards</span><span>0 real assets</span>
            </div>
          </div>
        </div>
        <div className="flex items-center justify-center px-5 py-12">
          <div className="w-full max-w-md rise">
            <div className="eyebrow mb-3">Secure demo sign-in</div>
            <h2 className="text-3xl font-bold tracking-tight text-white">Sign in to the simulation</h2>
            <form onSubmit={submit} className="mt-8 space-y-4" data-testid="login-form">
              <div className="space-y-1.5">
                <Label htmlFor="email">Email</Label>
                <Input id="email" data-testid="login-email-input" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@vaultbridge.demo" className="bg-[#111827]" />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="password">Password</Label>
                <Input id="password" type="password" data-testid="login-password-input" value={password} onChange={(e) => setPassword(e.target.value)} className="bg-[#111827]" />
              </div>
              <Button type="submit" disabled={busy} data-testid="login-submit-button" className="w-full">{busy ? "Signing in…" : "Sign in"}</Button>
            </form>
            <div className="mt-10">
              <div className="mb-3 flex items-center gap-2 text-xs text-slate-400"><KeyRound className="h-3.5 w-3.5 text-amber-300" /> Fictional demo accounts — click to fill</div>
              <div className="space-y-2">
                {DEMO.map((d) => (
                  <button key={d.role} type="button" data-testid={`demo-account-${d.role.toLowerCase()}`} onClick={() => { setEmail(d.email); setPassword(d.password); }}
                    className="w-full rounded-md border border-[#26354D] bg-[#111827] p-3 text-left transition-colors duration-200 hover:border-sky-400/50 hover:bg-[#182235]">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-semibold text-white">{d.role}</span>
                      <span className="text-[11px] text-slate-400">{d.org}</span>
                    </div>
                    <div className="mt-1 font-mono text-xs text-sky-300">{d.email}</div>
                    <div className="font-mono text-xs text-slate-400">{d.password}</div>
                  </button>
                ))}
              </div>
              <p className="mt-4 flex items-start gap-2 text-[11px] leading-relaxed text-slate-500">
                <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-300" />
                Demonstration credentials only. Never enter real wallet details, private keys, card or bank information.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
