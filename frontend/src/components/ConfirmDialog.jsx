import { useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";

export const ConfirmDialog = ({ open, onOpenChange, title, description, children, checkLabel, confirmLabel = "Confirm", onConfirm, testid = "confirm-dialog", disabled = false, danger = false }) => {
  const [checked, setChecked] = useState(false);
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    const ok = await onConfirm();
    setBusy(false);
    if (ok !== false) {
      setChecked(false);
      onOpenChange(false);
    }
  };
  const tone = danger ? "border-red-500/30 bg-red-500/5 text-red-100" : "border-amber-500/30 bg-amber-500/5 text-amber-100";
  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) setChecked(false); onOpenChange(v); }}>
      <DialogContent data-testid={testid} className="max-h-[85vh] overflow-y-auto border-[#26354D] bg-[#111827] sm:max-w-xl">
        <DialogHeader>
          <DialogTitle className="text-white">{title}</DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>
        {children}
        {checkLabel && !disabled && (
          <label className={`flex items-start gap-3 rounded-md border p-3 text-sm ${tone}`}>
            <Checkbox data-testid={`${testid}-checkbox`} checked={checked} onCheckedChange={(v) => setChecked(!!v)} className="mt-0.5" />
            {checkLabel}
          </label>
        )}
        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid={`${testid}-cancel`}>Cancel</Button>
          <Button variant={danger ? "destructive" : "default"} onClick={run} disabled={busy || disabled || (checkLabel && !checked)} data-testid={`${testid}-submit`}>{busy ? "Processing…" : confirmLabel}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
