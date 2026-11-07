import { useState } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { ArrowLeft, KeyRound, MailCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/context/AuthContext";
import { api, errMsg } from "@/lib/api";

const DEMO = [
  { role: "Admin", email: "admin@vaultbridge.demo", password: "AdminDemo#2026", org: "VaultBridge Escrow" },
  { role: "Sender", email: "sender@vaultbridge.demo", password: "SenderDemo#2026", org: "Demo Investment Entity" },
  { role: "Recipient", email: "recipient@vaultbridge.demo", password: "RecipientDemo#2026", org: "Demo Acquisition Company" },
];

const Field = ({ id, label, ...p }) => (
  <div className="space-y-1.5">
    <Label htmlFor={id}>{label}</Label>
    <Input id={id} data-testid={`${id}-input`} className="bg-[#111827]" {...p} />
  </div>
);

const Hero = () => (
  <div className="grain relative hidden overflow-hidden lg:block">
    <img src="/vault.jpg" alt="Ethereum emblem" className="absolute inset-0 h-full w-full object-cover opacity-40" />
    <div className="absolute inset-0 bg-gradient-to-t from-[#0B111E] via-[#0B111E]/70 to-[#0B111E]/30" />
    <div className="relative flex h-full flex-col justify-end p-14">
      <div className="eyebrow text-amber-300">Digital asset escrow</div>
      <h1 className="mt-4 max-w-xl text-5xl font-bold leading-tight tracking-tight text-white">VaultBridge Escrow</h1>
      <p className="mt-4 max-w-md text-sm leading-relaxed text-slate-300">
        Hold ETH safely between a sender and a recipient. Join, sign, deposit, release — in 10 simple steps.
      </p>
    </div>
  </div>
);

const Demo = ({ pick }) => (
  <div className="mt-10">
    <div className="mb-3 flex items-center gap-2 text-xs text-slate-400"><KeyRound className="h-3.5 w-3.5 text-amber-300" /> Demo accounts — tap one to fill in</div>
    <div className="space-y-2">
      {DEMO.map((d) => (
        <button key={d.role} type="button" data-testid={`demo-account-${d.role.toLowerCase()}`} onClick={() => pick(d)}
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
  </div>
);

const TITLES = {
  email: ["Welcome", "Enter your email"],
  login: ["Welcome back", "Sign in"],
  register: ["You've been invited", "Create your account"],
};

export default function Login() {
  const { user, login, register } = useAuth();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const [stage, setStage] = useState("email");
  const [role, setRole] = useState("");
  const [f, setF] = useState({ email: params.get("email") || "", password: "", confirm: "", name: "" });
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to="/" replace />;
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const run = async (fn) => {
    setBusy(true);
    try { await fn(); } catch (err) { toast.error(errMsg(err)); } finally { setBusy(false); }
  };

  const submit = (e) => {
    e.preventDefault();
    run(async () => {
      if (stage === "email") {
        const r = await api.post("/auth/check-email", { email: f.email });
        setRole(r.data.role || "");
        setStage(r.data.next);
      } else if (stage === "login") {
        await login(f.email, f.password);
        nav("/");
      } else {
        if (f.password !== f.confirm) throw new Error("Passwords don't match");
        await register({ email: f.email, password: f.password, name: f.name });
        toast.success("Account created — welcome to the escrow");
        nav("/");
      }
    });
  };

  const [eyebrow, title] = TITLES[stage];
  const btn = { email: "Continue", login: "Sign in", register: "Create account & enter escrow" }[stage];
  return (
    <div className="min-h-screen bg-[#0B111E]">
      <div className="grid min-h-screen lg:grid-cols-[1.1fr_1fr]">
        <Hero />
        <div className="flex items-center justify-center px-5 py-12">
          <div className="w-full max-w-md rise">
            <div className="eyebrow mb-3" data-testid="login-stage">{eyebrow}</div>
            <h2 className="text-3xl font-bold tracking-tight text-white">{title}</h2>
            {stage === "register" && (
              <p data-testid="register-invite-note" className="mt-3 flex items-start gap-2 text-sm text-slate-300">
                <MailCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-300" />
                This email was invited to an escrow deal as the <b className="text-white">{role}</b>. Set a password to open your account.
              </p>
            )}
            <form onSubmit={submit} className="mt-8 space-y-4" data-testid="login-form">
              <Field id="login-email" label="Email" type="email" value={f.email} onChange={set("email")} disabled={stage !== "email"} placeholder="you@company.com" required />
              {stage === "register" && <Field id="register-name" label="Your full name" value={f.name} onChange={set("name")} required />}
              {stage !== "email" && <Field id="login-password" label="Password" type="password" value={f.password} onChange={set("password")} autoFocus={stage === "login"} required />}
              {stage === "register" && <Field id="register-confirm" label="Confirm password" type="password" value={f.confirm} onChange={set("confirm")} placeholder="At least 8 characters" required />}
              <Button type="submit" disabled={busy} data-testid="login-submit-button" className="w-full">{busy ? "Please wait…" : btn}</Button>
              {stage !== "email" && (
                <button type="button" data-testid="login-change-email" onClick={() => setStage("email")} className="flex items-center gap-1 text-xs text-slate-400 hover:text-white">
                  <ArrowLeft className="h-3 w-3" /> Use a different email
                </button>
              )}
            </form>
            <Demo pick={(d) => { setF({ ...f, email: d.email, password: d.password }); setStage("login"); }} />
          </div>
        </div>
      </div>
    </div>
  );
}
