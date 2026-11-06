import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";

const TxCtx = createContext(null);

export const TxProvider = ({ children }) => {
  const [list, setList] = useState([]);
  const [selectedId, setSelectedId] = useState(localStorage.getItem("vb_tx") || "");
  const [tx, setTx] = useState(null);
  const [tick, setTick] = useState(0);

  const loadList = useCallback(async () => {
    const r = await api.get("/transactions");
    setList(r.data);
    return r.data;
  }, []);

  const select = (id) => {
    localStorage.setItem("vb_tx", id);
    setSelectedId(id);
  };

  useEffect(() => {
    loadList().then((l) => {
      if (l.length && !l.find((t) => t.id === selectedId)) select(l[0].id);
    }).catch(() => {});
  }, [loadList, selectedId]);

  const refresh = useCallback(async () => {
    if (!selectedId) return;
    try {
      const r = await api.get(`/transactions/${selectedId}`);
      setTx(r.data);
      setTick((t) => t + 1);
    } catch (e) { /* handled by interceptor */ }
  }, [selectedId]);

  useEffect(() => { refresh(); }, [refresh]);

  const confirming = tx?.deposit?.initiated_at && tx.deposit.confirmations < 12;
  useEffect(() => {
    const id = setInterval(refresh, confirming ? 1500 : 5000);
    return () => { clearInterval(id); };
  }, [refresh, confirming]);

  const act = async (action, data = {}, success = "Simulated action recorded") => {
    try {
      const r = await api.post(`/transactions/${tx.id}/actions/${action}`, { data });
      setTx(r.data);
      setTick((t) => t + 1);
      toast.success(success);
      loadList();
      return true;
    } catch (e) {
      toast.error(errMsg(e));
      return false;
    }
  };

  return (
    <TxCtx.Provider value={{ list, tx, selectedId, select, refresh, act, loadList, tick }}>{children}</TxCtx.Provider>
  );
};

export const useTx = () => useContext(TxCtx);
