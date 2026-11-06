import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHeader, Panel, StatusPill } from "@/components/common";
import { useTx } from "@/context/TxContext";
import { useAuth } from "@/context/AuthContext";
import { dt } from "@/lib/fmt";

const STATUSES = ["Pending", "Under Review", "More Info Needed", "Approved", "Rejected"];

export default function Checks() {
  const { tx, act } = useTx();
  const { user } = useAuth();
  const editable = user.role === "admin" && !tx.aml.completed_at;
  return (
    <div data-testid="checks-page">
      <PageHeader title="Checks" desc={tx.aml.completed_at ? `All checks approved on ${dt(tx.aml.completed_at)}.` : "Checks are approved together when you verify the deposit. You can change any one here first."} />
      <Panel>
        <div className="overflow-x-auto">
          <Table className="vb-table">
            <TableHeader><TableRow><TableHead>Check</TableHead><TableHead>Status</TableHead><TableHead>Updated</TableHead></TableRow></TableHeader>
            <TableBody>
              {Object.entries(tx.compliance).map(([k, c]) => (
                <TableRow key={k} data-testid={`check-row-${k}`}>
                  <TableCell className="text-sm text-white">{c.label}</TableCell>
                  <TableCell>
                    {editable ? (
                      <Select value={c.status} onValueChange={(v) => act("set_compliance", { check: k, status: v }, `${c.label}: ${v}`)}>
                        <SelectTrigger data-testid={`check-status-select-${k}`} className="w-[200px] bg-[#0B111E] text-xs"><SelectValue /></SelectTrigger>
                        <SelectContent>{STATUSES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
                      </Select>
                    ) : <StatusPill status={c.status} testid={`check-status-${k}`} />}
                  </TableCell>
                  <TableCell className="text-xs text-slate-500">{dt(c.updated_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Panel>
    </div>
  );
}
