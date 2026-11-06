import { useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";

export const ConfirmDialog = ({ open, onOpenChange, title, description, children, checkLabel, confirmLabel = "Confirm", onConfirm, testid = "confirm-dialog" }) => {
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
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={testid} className="max-h-[85vh] overflow-y-auto border-[#26354D] bg-[#111827] sm:max-w-xl">
        <DialogHeader>
          <DialogTitle className="text-white">{title}</DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>
        {children}
        {checkLabel && (
          <label className="flex items-start gap-3 rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-sm text-amber-100">
            <Checkbox data-testid={`${testid}-checkbox`} checked={checked} onCheckedChange={(v) => setChecked(!!v)} className="mt-0.5" />
            {checkLabel}
          </label>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid={`${testid}-cancel`}>Cancel</Button>
          <Button onClick={run} disabled={busy || (checkLabel && !checked)} data-testid={`${testid}-submit`}>{busy ? "Processing…" : confirmLabel}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
