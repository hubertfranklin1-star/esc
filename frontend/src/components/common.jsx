const tone = (s = "") => {
  const v = s.toLowerCase();
  if (/(severe|high risk|ofac|mixer)/.test(v)) return "border-red-500/40 bg-red-500/10 text-red-300";
  if (/low risk/.test(v)) return "border-emerald-500/40 bg-emerald-500/10 text-emerald-300";
  if (/medium risk/.test(v)) return "border-amber-500/40 bg-amber-500/10 text-amber-300";
  if (/(unpaid|payment sent|more info|waiting|awaiting)/.test(v)) return "border-amber-500/40 bg-amber-500/10 text-amber-300";
  if (/(approval|approved|accepted|paid|completed|confirmed|released|credited)/.test(v)) return "border-emerald-500/40 bg-emerald-500/10 text-emerald-300";
  if (/(rejection|rejected|declined|hold)/.test(v)) return "border-red-500/40 bg-red-500/10 text-red-300";
  if (/(additional|pending confirmation|submitted|awaiting)/.test(v)) return "border-amber-500/40 bg-amber-500/10 text-amber-300";
  if (/(review|progress|confirming|issued|requested)/.test(v)) return "border-sky-500/40 bg-sky-500/10 text-sky-300";
  return "border-slate-500/40 bg-slate-500/10 text-slate-300";
};

export const StatusPill = ({ status, testid }) => (
  <span data-testid={testid} className={`inline-flex items-center whitespace-nowrap rounded-full border px-2.5 py-0.5 text-[11px] font-semibold ${tone(status)}`}>
    {status}
  </span>
);

export const StatCard = ({ label, value, sub, accent = "blue", testid, delay = 0 }) => (
  <div data-testid={testid} className="panel rise relative overflow-hidden p-5" style={{ animationDelay: `${delay}ms` }}>
    <div className={`absolute left-0 top-0 h-full w-[3px] ${accent === "gold" ? "bg-amber-400" : "bg-sky-400"}`} />
    <div className="eyebrow">{label}</div>
    <div className="mt-2 font-mono text-xl font-semibold text-white sm:text-2xl">{value}</div>
    {sub && <div className="mt-1 text-xs text-slate-400">{sub}</div>}
  </div>
);

export const PageHeader = ({ eyebrow, title, desc, actions }) => (
  <div className="mb-8 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
    <div>
      {eyebrow && <div className="eyebrow mb-2 text-amber-300/80">{eyebrow}</div>}
      <h1 className="text-3xl font-bold tracking-tight text-white sm:text-4xl">{title}</h1>
      {desc && <p className="mt-2 max-w-2xl text-sm text-slate-400">{desc}</p>}
    </div>
    {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
  </div>
);

export const Panel = ({ title, actions, children, className = "", testid, sub }) => (
  <section data-testid={testid} className={`panel rise p-5 ${className}`}>
    {(title || actions) && (
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-base font-semibold text-white md:text-lg">{title}</h2>
          {sub && <p className="text-xs text-slate-400">{sub}</p>}
        </div>
        {actions}
      </div>
    )}
    {children}
  </section>
);

export const KV = ({ label, value, mono, testid }) => (
  <div className="flex flex-col gap-1 border-b border-[#26354D]/60 py-2.5 last:border-0 sm:flex-row sm:items-center sm:justify-between">
    <span className="text-xs text-slate-400">{label}</span>
    <span data-testid={testid} className={`flex items-center gap-2 break-all text-sm text-slate-100 ${mono ? "font-mono" : ""}`}>
      {value ?? "—"}
    </span>
  </div>
);

export const Empty = ({ children, testid }) => (
  <div data-testid={testid} className="rounded-md border border-dashed border-[#26354D] p-6 text-center text-sm text-slate-400">{children}</div>
);
