import { Check } from "lucide-react";

const SHORT = ["Sender joins", "Recipient joins", "Onboarding fee", "Approval", "Deposit", "AML checks", "AML report", "Request funds", "Escrow fees", "Release"];

export const Stepper = ({ tx }) => (
  <ol data-testid="deal-stepper" className="flex gap-1 overflow-x-auto pb-2">
    {tx.steps.map((s, i) => {
      const current = s.n === tx.current_step;
      return (
        <li key={s.n} data-testid={`step-${s.n}`} data-done={s.done} title={s.title} className="flex min-w-[92px] flex-1 flex-col items-center gap-2 text-center">
          <div className="flex w-full items-center">
            <div className={`h-[2px] flex-1 ${i === 0 ? "opacity-0" : s.done || current ? "bg-sky-400/60" : "bg-[#26354D]"}`} />
            <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full font-mono text-xs font-semibold transition-colors duration-300 ${
              s.done ? "bg-emerald-500 text-[#0B111E]" : current ? "pulse-ring bg-sky-400 text-[#0B111E]" : "border border-[#26354D] bg-[#111827] text-slate-500"}`}>
              {s.done ? <Check className="h-4 w-4" /> : s.n}
            </span>
            <div className={`h-[2px] flex-1 ${i === tx.steps.length - 1 ? "opacity-0" : s.done ? "bg-sky-400/60" : "bg-[#26354D]"}`} />
          </div>
          <span className={`text-[11px] leading-tight ${current ? "font-semibold text-white" : s.done ? "text-slate-300" : "text-slate-500"}`}>{SHORT[i]}</span>
        </li>
      );
    })}
  </ol>
);
