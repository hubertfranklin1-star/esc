import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";

const TxCtx = createContext(null);

export const TxProvider = ({ children }) => {
  const [list, setList] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [selectedId, setSelectedId] = useState(localStorage.getItem("vb_tx") || "");
  const [tx, setTx] = useState(null);
  const [tick, setTick] = useState(0);

  const loadList = useCallback(async () => {
    const r = await api.get("/transactions");
    setList(r.data);
    setLoaded(true);
    return r.data;
  }, []);

  const select = (id) => {
    localStorage.setItem("vb_tx", id);
    setSelectedId(id);
  };

  // Keep the selected deal valid: fall back to the latest deal, or to none when the list is empty.
  const keepValid = useCallback((l, current) => {
    if (l.find((t) => t.id === current)) return;
    const next = l.length ? l[l.length - 1].id : "";
    if (!next) setTx(null);
    localStorage.setItem("vb_tx", next);
    setSelectedId(next);
  }, []);

  useEffect(() => {
    loadList().then((l) => keepValid(l, selectedId)).catch(() => {});
  }, [loadList, keepValid, selectedId]);

  const resync = useCallback(async () => {
    try {
      const l = await loadList();
      keepValid(l, selectedId);
    } catch (e) { /* ignore */ }
  }, [loadList, keepValid, selectedId]);

  const refresh = useCallback(async () => {
    if (!selectedId) return;
    try {
      const r = await api.get(`/transactions/${selectedId}`);
      setTx(r.data);
      setTick((t) => t + 1);
    } catch (e) {
      if (e?.response?.status === 404) {
        setTx(null);
        await resync();
      }
    }
  }, [selectedId, resync]);

  useEffect(() => { refresh(); }, [refresh]);

  useEffect(() => {
    const id = setInterval(refresh, 5000);
    return () => { clearInterval(id); };
  }, [refresh]);

  const act = async (action, data = {}, success = "Done") => {
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
    <TxCtx.Provider value={{ list, loaded, tx, selectedId, select, refresh, resync, act, loadList, tick }}>{children}</TxCtx.Provider>
  );
};

export const useTx = () => useContext(TxCtx);
