import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Bell, BellOff, BellRing, CheckCheck } from "lucide-react";
import clsx from "clsx";
import { api } from "@/lib/api";
import { formatDateTime } from "@/i18n/format";
import { usePushSubscription } from "@/hooks/usePushNotifications";

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
 * the caller's recent notifications from the outbox with read state, plus the
 * Web Push switch for this device.
 *
 * `sidebar`: square toggle in the always-dark sidebar, the panel opens upwards.
 * `header`: icon button in the mobile top bar, the panel opens downwards.
 */
export default function NotificationCenter({ variant = "header" }: { variant?: "sidebar" | "header" }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const push = usePushSubscription();
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
        className={clsx("relative", variant === "sidebar" ? "sidebar-toggle" : "btn-icon border-transparent")}
        aria-label={t("notifications.open", { count: unread })}
        aria-expanded={open}
        aria-haspopup="true"
        onClick={() => setOpen((value) => !value)}
      >
        <Bell className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" />
        {unread > 0 && (
          <span className="count-badge absolute -right-1.5 -top-1.5" aria-hidden="true">
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>
      {open && (
        <div
          className={clsx(
            "absolute z-50 w-80 max-w-[calc(100vw-2rem)] overflow-hidden rounded-karte border border-rand bg-flaeche text-fg shadow-tief",
            variant === "sidebar" ? "bottom-full left-0 mb-2" : "right-0 mt-2",
          )}
        >
          <div className="flex min-h-12 items-center justify-between border-b border-rand px-4 py-2">
            <h2 className="font-ui font-semibold tracking-ui">{t("notifications.title")}</h2>
            {unread > 0 && (
              <button type="button" className="flex min-h-9 items-center gap-1 text-xs font-semibold text-akzent hover:underline" onClick={() => markAll.mutate()}>
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
                      "block w-full border-b border-rand px-4 py-3 text-left text-sm last:border-0 hover:bg-flaeche-2",
                      !item.read && "bg-primary/[0.06] shadow-[inset_3px_0_0_theme(colors.primary.DEFAULT)]",
                    )}
                    onClick={() => openItem(item)}
                  >
                    <span className="flex items-center gap-2 font-medium">
                      {!item.read && <><span className="h-2 w-2 shrink-0 rounded-full bg-primary" aria-hidden="true" /><span className="sr-only">{t("notifications.unread")}</span></>}
                      {item.title}
                    </span>
                    {item.body && <span className="mt-0.5 block text-leise">{item.body}</span>}
                    <span className="mt-1 block text-xs text-leise">{formatDateTime(item.created_at)}</span>
                  </button>
                </li>
              ))
            ) : (
              <li className="px-4 py-6 text-center text-sm text-leise">{t("notifications.empty")}</li>
            )}
          </ul>
          <div className="border-t border-rand bg-flaeche-2 p-1.5">
            <button
              type="button"
              className="flex min-h-11 w-full items-center gap-2 rounded-eng px-2.5 text-left font-ui text-sm font-semibold tracking-ui text-fg hover:bg-fg/[0.06]"
              aria-pressed={push.isSubscribed}
              onClick={() => (push.isSubscribed ? push.unsubscribe.mutate() : push.subscribe.mutate())}
            >
              {push.isSubscribed ? (
                <BellRing className="h-4 w-4 text-akzent" aria-hidden="true" />
              ) : (
                <BellOff className="h-4 w-4 text-leise" aria-hidden="true" />
              )}
              {push.isSubscribed ? t("push.enabled") : t("push.enable")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
