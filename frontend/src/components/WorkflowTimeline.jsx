import { Check } from "lucide-react";

const actorLabel = { admin: "Admin", sender: "Sender", recipient: "Recipient", both: "Both parties", network: "Sim. network" };

export const WorkflowTimeline = ({ tx }) => (
  <ol data-testid="workflow-timeline" className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
    {tx.steps.map((s) => {
      const current = s.n === tx.current_step;
      return (
        <li
          key={s.n}
          data-testid={`workflow-step-${s.n}`}
          data-done={s.done}
          className={`flex items-start gap-3 rounded-md border p-3 transition-colors duration-300 ${
            current ? "border-sky-400/60 bg-sky-500/10" : s.done ? "border-emerald-500/20 bg-emerald-500/[0.04]" : "border-[#26354D] bg-[#0B111E]/60"
          }`}
        >
          <span
            className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full font-mono text-[11px] font-semibold ${
              s.done ? "bg-emerald-500 text-[#0B111E]" : current ? "pulse-ring bg-sky-400 text-[#0B111E]" : "bg-[#182235] text-slate-400"
            }`}
          >
            {s.done ? <Check className="h-3.5 w-3.5" /> : s.n}
          </span>
          <div className="min-w-0">
            <div className={`text-sm leading-snug ${s.done ? "text-slate-300" : current ? "text-white" : "text-slate-500"}`}>{s.title}</div>
            <div className="mt-0.5 font-mono text-[10px] uppercase tracking-wider text-slate-500">{actorLabel[s.actor]}</div>
          </div>
        </li>
      );
    })}
  </ol>
);
