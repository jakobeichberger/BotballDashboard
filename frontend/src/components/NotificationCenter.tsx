import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Bell, CheckCheck } from "lucide-react";
import clsx from "clsx";
import { api } from "@/lib/api";

export interface NotificationItem {
  id: string;
  event_id: string | null;
  event_type: string;
  category: string | null;
  title: string;
  body: string;
  url: string | null;
  created_at: string;
  read: boolean;
}

interface NotificationList {
  items: NotificationItem[];
  unread: number;
}

const QUERY_KEY = ["notifications"];

/**
 * In-app notification center (spec 09 fallback when Web Push is unavailable):
 * the caller's recent notifications from the outbox with read state.
 */
export default function NotificationCenter() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const panel = useRef<HTMLDivElement>(null);
  const { data } = useQuery<NotificationList>({
    queryKey: QUERY_KEY,
    queryFn: async () => (await api.get("/dashboard/notifications", { params: { limit: 20 } })).data,
    refetchInterval: 60_000,
  });
  const markRead = useMutation({
    mutationFn: async (ids: string[]) => api.post("/dashboard/notifications/read", { ids }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: QUERY_KEY }),
  });
  const markAll = useMutation({
    mutationFn: async () => api.post("/dashboard/notifications/read-all"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: QUERY_KEY }),
  });

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent | KeyboardEvent) => {
      if (event instanceof KeyboardEvent ? event.key === "Escape" : !panel.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  const unread = data?.unread ?? 0;
  const openItem = (item: NotificationItem) => {
    if (!item.read) markRead.mutate([item.id]);
    const target = item.url ?? (item.event_id ? `/events/${item.event_id}/dashboard` : null);
    setOpen(false);
    if (target) navigate(target);
  };

  return (
    <div className="relative" ref={panel}>
      <button
        type="button"
        className="relative rounded-lg p-2 text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800"
        aria-label={t("notifications.open", { count: unread })}
        aria-expanded={open}
        aria-haspopup="true"
        onClick={() => setOpen((value) => !value)}
      >
        <Bell className="h-5 w-5" aria-hidden="true" />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 min-w-[1.25rem] rounded-full bg-red-600 px-1 text-center text-xs font-semibold leading-5 text-white" aria-hidden="true">
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 z-50 mt-2 w-80 max-w-[calc(100vw-2rem)] rounded-xl border bg-white shadow-xl dark:border-gray-700 dark:bg-gray-900">
          <div className="flex items-center justify-between border-b px-4 py-2 dark:border-gray-700">
            <h2 className="font-semibold">{t("notifications.title")}</h2>
            {unread > 0 && (
              <button type="button" className="flex items-center gap-1 text-xs text-primary-700 hover:underline dark:text-primary-300" onClick={() => markAll.mutate()}>
                <CheckCheck className="h-3 w-3" aria-hidden="true" />
                {t("notifications.markAllRead")}
              </button>
            )}
          </div>
          <ul className="max-h-96 overflow-y-auto">
            {data?.items.length ? (
              data.items.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    className={clsx(
                      "block w-full border-b px-4 py-3 text-left text-sm last:border-0 hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800",
                      !item.read && "bg-primary-50/60 dark:bg-primary-900/20",
                    )}
                    onClick={() => openItem(item)}
                  >
                    <span className="flex items-center gap-2 font-medium">
                      {!item.read && <><span className="h-2 w-2 shrink-0 rounded-full bg-primary-600" aria-hidden="true" /><span className="sr-only">ungelesen:</span></>}
                      {item.title}
                    </span>
                    {item.body && <span className="mt-0.5 block text-gray-600 dark:text-gray-400">{item.body}</span>}
                    <span className="mt-1 block text-xs text-gray-400">{new Date(item.created_at).toLocaleString()}</span>
                  </button>
                </li>
              ))
            ) : (
              <li className="px-4 py-6 text-center text-sm text-gray-500">{t("notifications.empty")}</li>
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
