import { useEffect, useState } from "react";
import { api } from "@/lib/api";

// The ETH price the app prices deals and fees with: saved every 5 minutes from free public sources.
// Pass a value (e.g. a dialog's `open` flag) to reload it whenever that value changes.
export const useEthPrice = (reloadKey) => {
  const [p, setP] = useState(null);
  useEffect(() => {
    if (reloadKey === false) return;
    api.get("/eth-price").then((r) => setP(r.data)).catch(() => {});
  }, [reloadKey]);
  return p;
};

export const savedAt = (iso) => (iso ? new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }) : "");
