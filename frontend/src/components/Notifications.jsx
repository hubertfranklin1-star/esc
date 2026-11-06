import { useCallback, useEffect, useState } from "react";
import { Bell, Mail } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { dt } from "@/lib/fmt";
import { useTx } from "@/context/TxContext";

export const useNotifications = () => {
  const { tick } = useTx();
  const [items, setItems] = useState([]);
  const load = useCallback(() => api.get("/notifications").then((r) => setItems(r.data)).catch(() => {}), []);
  useEffect(() => { load(); }, [load, tick]);
  return { items, load };
};

export const NotificationList = ({ items, onRead, limit, testid = "notification-list" }) => (
  <ul data-testid={testid} className="divide-y divide-[#26354D]">
    {items.slice(0, limit).map((n) => (
      <li key={n.id} data-testid={`notification-${n.id}`} onClick={() => onRead && onRead(n)}
        className={`cursor-pointer px-3 py-3 transition-colors hover:bg-[#182235] ${n.read ? "opacity-60" : ""}`}>
        <div className="flex items-center gap-2 text-sm font-medium text-white">
          {n.kind === "email" ? <Mail className="h-3.5 w-3.5 text-amber-300" /> : <span className={`h-1.5 w-1.5 rounded-full ${n.read ? "bg-slate-600" : "bg-sky-400"}`} />}
          {n.title}
        </div>
        <p className="mt-1 text-xs leading-relaxed text-slate-400">{n.body}</p>
        <div className="mt-1 font-mono text-[10px] text-slate-500">
          {n.kind === "email" ? "EMAIL · " : ""}{dt(n.created_at)}
        </div>
      </li>
    ))}
    {items.length === 0 && <li className="p-4 text-center text-sm text-slate-500">No notifications yet</li>}
  </ul>
);

export const NotificationsBell = () => {
  const { items, load } = useNotifications();
  const unread = items.filter((n) => !n.read).length;
  const readOne = async (n) => { await api.post(`/notifications/${n.id}/read`); load(); };
  const readAll = async () => { await api.post("/notifications/read-all"); load(); };
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button data-testid="notifications-bell" className="relative rounded-md border border-[#26354D] p-2 text-slate-300 transition-colors hover:bg-[#182235]">
          <Bell className="h-4 w-4" />
          {unread > 0 && (
            <span data-testid="notifications-unread-count" className="absolute -right-1.5 -top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-amber-400 px-1 font-mono text-[10px] font-bold text-[#0B111E]">{unread}</span>
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[22rem] border-[#26354D] bg-[#111827] p-0">
        <div className="flex items-center justify-between border-b border-[#26354D] px-3 py-2">
          <span className="eyebrow">Messages</span>
          <Button size="sm" variant="ghost" data-testid="notifications-read-all" onClick={readAll}>Mark all read</Button>
        </div>
        <div className="max-h-[60vh] overflow-y-auto"><NotificationList items={items} onRead={readOne} limit={30} /></div>
      </PopoverContent>
    </Popover>
  );
};
