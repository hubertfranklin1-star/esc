import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Download, Search, ShieldAlert, ShieldCheck, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHeader, Panel, KV, StatCard, StatusPill, Empty } from "@/components/common";
import { useTx } from "@/context/TxContext";
import { api, errMsg, download } from "@/lib/api";
import { dt, short } from "@/lib/fmt";

const n = (v, d = 4) => Number(v || 0).toLocaleString("en-US", { maximumFractionDigits: d });
const scanLink = (a) => `https://etherscan.io/address/${a}`;

const Risk = ({ r }) => (
  <Panel title="Risk assessment" testid="forensic-risk" actions={<StatusPill status={`${r.risk.band} risk`} />}>
    <div className="mb-3 flex items-end gap-2">
      <span data-testid="forensic-risk-score" className={`font-mono text-5xl font-semibold ${r.risk.score >= 50 ? "text-red-300" : r.risk.score >= 20 ? "text-amber-300" : "text-emerald-300"}`}>{r.risk.score}</span>
      <span className="pb-1 text-slate-500">/100</span>
    </div>
    <ul className="space-y-1.5 text-sm text-slate-300">{r.risk.reasons.map((x) => <li key={x} className="flex gap-2"><span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-sky-400" />{x}</li>)}</ul>
  </Panel>
);

const Screening = ({ r }) => (
  <Panel title="Sanctions & high-risk services" testid="forensic-screening">
    <div className="mb-3 flex items-center gap-2 text-sm">
      {r.sanctions.listed ? <ShieldAlert className="h-5 w-5 text-red-400" /> : <ShieldCheck className="h-5 w-5 text-emerald-400" />}
      <span data-testid="forensic-sanctions-result" className="text-white">{r.sanctions.listed ? "Wallet is on the OFAC sanctions list" : "Wallet is not on the OFAC sanctions list"}</span>
    </div>
    <KV label="Sanctioned counterparties" value={r.sanctions.counterparty_hits.length} mono />
    <KV label="Mixer / high-risk counterparties" value={r.risky_services.counterparty_hits.length} mono />
    <KV label="Wallet is a known service" value={r.risky_services.self || "No"} />
    <KV label="Addresses screened against" value={n(r.sanctions.list_size, 0)} mono />
    <p className="mt-2 text-[11px] text-slate-500">{r.sanctions.list_source}</p>
  </Panel>
);

const Activity = ({ r }) => {
  const a = r.activity;
  return (
    <Panel title="Transaction history" testid="forensic-activity">
      <KV label="First activity" value={dt(a.first_seen)} />
      <KV label="Last activity" value={dt(a.last_seen)} />
      <KV label="Normal / internal / token transfers" value={`${n(a.normal_tx, 0)} / ${n(a.internal_tx, 0)} / ${n(a.token_transfers, 0)}`} mono />
      <KV label="Total ETH received" value={`${n(a.eth_in)} ETH`} mono />
      <KV label="Total ETH sent" value={`${n(a.eth_out)} ETH`} mono />
      <KV label="Failed transactions" value={a.failed_tx} mono />
      <KV label="Unique counterparties" value={n(a.unique_counterparties, 0)} mono />
      {a.history_capped && <p className="mt-2 text-[11px] text-amber-300">Very active wallet — only the most recent records per category were available from the data provider.</p>}
    </Panel>
  );
};

const Counterparties = ({ r }) => (
  <Panel title="Top counterparties" testid="forensic-counterparties">
    {r.counterparties.length === 0 ? <Empty>No counterparties.</Empty> : (
      <div className="overflow-x-auto">
        <Table className="vb-table">
          <TableHeader><TableRow><TableHead>Address</TableHead><TableHead>Received ETH</TableHead><TableHead>Sent ETH</TableHead><TableHead>Interactions</TableHead><TableHead>Flags</TableHead></TableRow></TableHeader>
          <TableBody>
            {r.counterparties.map((c) => (
              <TableRow key={c.address}>
                <TableCell className="font-mono text-xs"><a href={scanLink(c.address)} target="_blank" rel="noreferrer" className="text-sky-300 hover:underline">{short(c.address, 6)}</a></TableCell>
                <TableCell className="font-mono text-xs">{n(c.received_eth)}</TableCell>
                <TableCell className="font-mono text-xs">{n(c.sent_eth)}</TableCell>
                <TableCell className="font-mono text-xs">{c.interactions}</TableCell>
                <TableCell className="text-xs">{c.sanctioned && <StatusPill status="OFAC sanctioned" />} {c.service && <StatusPill status={`Mixer: ${c.service}`} />}{!c.sanctioned && !c.service && <span className="text-slate-500">—</span>}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    )}
  </Panel>
);

const Tokens = ({ r }) => (
  <Panel title="Token holdings" testid="forensic-tokens">
    {r.tokens.length === 0 ? <Empty>No token activity.</Empty> : r.tokens.slice(0, 12).map((t) => (
      <KV key={t.contract} label={`${t.symbol || "?"} · ${t.transfers} transfers`} value={t.balance == null ? "—" : n(t.balance, 2)} mono />
    ))}
    <p className="mt-2 text-[11px] text-slate-500">Current balance shown for the most active tokens. Spam and airdrop-scam tokens are filtered out.</p>
  </Panel>
);

const Recent = ({ r }) => (
  <Panel title="Recent transactions" testid="forensic-recent">
    {r.recent_transactions.length === 0 ? <Empty>No transactions.</Empty> : (
      <div className="overflow-x-auto">
        <Table className="vb-table">
          <TableHeader><TableRow><TableHead>Hash</TableHead><TableHead>Time</TableHead><TableHead>From</TableHead><TableHead>To</TableHead><TableHead>ETH</TableHead><TableHead>Status</TableHead></TableRow></TableHeader>
          <TableBody>
            {r.recent_transactions.map((t) => (
              <TableRow key={t.hash}>
                <TableCell className="font-mono text-xs"><a href={`https://etherscan.io/tx/${t.hash}`} target="_blank" rel="noreferrer" className="text-sky-300 hover:underline">{short(t.hash, 6)}</a></TableCell>
                <TableCell className="whitespace-nowrap text-xs text-slate-400">{dt(t.time)}</TableCell>
                <TableCell className="font-mono text-xs">{short(t.from, 4)}</TableCell>
                <TableCell className="font-mono text-xs">{short(t.to, 4)}</TableCell>
                <TableCell className="font-mono text-xs">{n(t.value_eth)}</TableCell>
                <TableCell><StatusPill status={t.status === "Success" ? "Confirmed" : "Rejected"} /></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    )}
  </Panel>
);

const Report = ({ scan }) => {
  const r = scan.report;
  return (
    <div data-testid="forensic-report" className="space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="min-w-0">
          <div className="eyebrow">Subject wallet {scan.label && `· ${scan.label}`}</div>
          <a href={scanLink(r.address)} target="_blank" rel="noreferrer" data-testid="forensic-address" className="flex items-center gap-1.5 break-all font-mono text-sm text-white hover:text-sky-300">{r.address} <ExternalLink className="h-3.5 w-3.5 shrink-0" /></a>
          <div className="text-xs text-slate-500">{r.chain} · {r.is_contract ? "Smart contract" : r.delegated_7702 ? "Wallet (EIP-7702 delegated)" : "Externally owned account"} · {r.data_source} · {dt(r.generated_at)}</div>
        </div>
        <Button data-testid="forensic-pdf-button" className="gap-1.5" onClick={() => download(`/forensics/scans/${scan.id}/pdf`, `forensic-${r.address.slice(0, 10)}.pdf`)}><Download className="h-4 w-4" /> Download report (PDF)</Button>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="ETH balance" value={`${n(r.balance_eth)} ETH`} accent="gold" testid="forensic-balance" />
        <StatCard label="Total received" value={`${n(r.activity.eth_in, 2)} ETH`} testid="forensic-eth-in" />
        <StatCard label="Total sent" value={`${n(r.activity.eth_out, 2)} ETH`} testid="forensic-eth-out" />
        <StatCard label="Risk" value={`${r.risk.score}/100 · ${r.risk.band}`} accent="gold" testid="forensic-risk-card" />
      </div>
      <div className="grid gap-6 lg:grid-cols-3 [&>*]:min-w-0"><Risk r={r} /><Screening r={r} /><Activity r={r} /></div>
      <div className="grid gap-6 xl:grid-cols-[1fr_340px] [&>*]:min-w-0"><Counterparties r={r} /><Tokens r={r} /></div>
      <Recent r={r} />
    </div>
  );
};

export default function Forensics() {
  const { tx } = useTx();
  const [address, setAddress] = useState("");
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);
  const [scan, setScan] = useState(null);
  const [history, setHistory] = useState([]);
  const loadHistory = () => api.get("/forensics/scans").then((r) => setHistory(r.data));
  useEffect(() => { loadHistory(); }, []);
  const run = async (addr = address, lbl = label) => {
    setBusy(true);
    try {
      const r = await api.post("/forensics/scan", { address: addr.trim(), label: lbl });
      setScan(r.data);
      toast.success("Forensic analysis complete");
      loadHistory();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  const open = async (id) => { const r = await api.get(`/forensics/scans/${id}`); setScan(r.data); };
  const dealWallets = ["sender", "recipient"].map((p) => [p, tx.onboarding[p].data?.wallet_address]).filter(([, w]) => w);
  return (
    <div data-testid="forensics-page" className="space-y-6">
      <PageHeader title="Forensics" desc="Live on-chain analysis of any Ethereum wallet: balance, history, counterparties, OFAC sanctions screening and mixer exposure." />
      <Panel title="Analyse a wallet" testid="forensic-form">
        <form className="flex flex-col gap-2 md:flex-row" onSubmit={(e) => { e.preventDefault(); run(); }}>
          <Input data-testid="forensic-address-input" placeholder="0x… wallet address" value={address} onChange={(e) => setAddress(e.target.value)} className="bg-[#0B111E] font-mono text-xs md:flex-1" />
          <Input data-testid="forensic-label-input" placeholder="Label (optional)" value={label} onChange={(e) => setLabel(e.target.value)} className="bg-[#0B111E] md:w-56" />
          <Button data-testid="forensic-scan-button" disabled={busy} className="gap-1.5"><Search className="h-4 w-4" /> {busy ? "Analysing…" : "Run analysis"}</Button>
        </form>
        {dealWallets.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2 text-xs">
            <span className="text-slate-500">Deal wallets:</span>
            {dealWallets.map(([p, w]) => <button key={p} type="button" data-testid={`forensic-quick-${p}`} onClick={() => { setAddress(w); setLabel(`${tx.reference} ${p}`); }} className="rounded-sm border border-[#26354D] px-2 py-0.5 font-mono text-sky-300 hover:bg-[#182235]">{p}: {short(w, 4)}</button>)}
          </div>
        )}
        {busy && <p className="mt-3 text-xs text-slate-400">Reading the blockchain — large wallets can take up to a minute.</p>}
      </Panel>
      {scan && <Report scan={scan} />}
      <Panel title="Previous analyses" testid="forensic-history">
        {history.length === 0 ? <Empty>No analyses yet.</Empty> : history.map((h) => (
          <button key={h.id} data-testid={`forensic-history-${h.id}`} onClick={() => open(h.id)} className="flex w-full items-center justify-between gap-3 border-b border-[#26354D]/60 py-2.5 text-left last:border-0 hover:bg-[#182235]/50">
            <div className="min-w-0"><div className="truncate font-mono text-xs text-white">{h.address}</div><div className="text-[11px] text-slate-500">{h.label || "—"} · {dt(h.created_at)}</div></div>
            <div className="flex shrink-0 items-center gap-2"><span className="font-mono text-xs text-slate-300">{n(h.balance_eth, 2)} ETH</span><StatusPill status={`${h.risk.band} risk`} /></div>
          </button>
        ))}
      </Panel>
    </div>
  );
}
