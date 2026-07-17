import { useState } from "react";
import { NavLink, Outlet, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  Bell,
  BellOff,
  CalendarDays,
  FileText,
  Globe,
  LayoutDashboard,
  LogOut,
  Menu,
  Monitor,
  Moon,
  Printer,
  ScanLine,
  Settings,
  Sun,
  Trophy,
  Users,
  X,
} from "lucide-react";
import clsx from "clsx";
import { useAuthStore } from "@/store/authStore";
import { useThemeStore } from "@/store/themeStore";
import { useLogout } from "@/hooks/useAuth";
import { usePushSubscription } from "@/hooks/usePushNotifications";
import { useOnlineStatus } from "@/hooks/useOnlineStatus";
import { useEvent, useEvents } from "@/hooks/useEvents";
import i18n from "@/i18n/config";
import { navigationRoutes } from "@/core/plugins";

const ICONS = { dashboard: LayoutDashboard, teams: Users, schedule: CalendarDays, scoring: Trophy, scans: ScanLine, papers: FileText, printing: Printer, settings: Settings };

export default function Layout() {
  const { t } = useTranslation();
  const { eventId = "" } = useParams();
  const { user, hasPermission } = useAuthStore();
  const { theme, setTheme } = useThemeStore();
  const logout = useLogout();
  const navigate = useNavigate();
  const push = usePushSubscription();
  const online = useOnlineStatus();
  const { data: events } = useEvents();
  const { data: event } = useEvent(eventId);
  const [menuOpen, setMenuOpen] = useState(false);

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };
  const nextTheme = () => {
    const order = ["light", "dark", "system"] as const;
    setTheme(order[(order.indexOf(theme) + 1) % order.length]);
  };
  const ThemeIcon = theme === "light" ? Sun : theme === "dark" ? Moon : Monitor;
  const visibleNav = navigationRoutes.filter((item) => hasPermission(item.permission));

  const sidebar = (
    <aside className="flex h-full w-72 shrink-0 flex-col border-r bg-white shadow-sm dark:border-gray-800 dark:bg-gray-900">
      <div className="flex h-16 items-center justify-between border-b px-5 dark:border-gray-800">
        <span className="font-bold text-primary-700 dark:text-primary-400">{t("app_name")}</span>
        <button className="md:hidden" onClick={() => setMenuOpen(false)} aria-label={t("closeMenu")}><X /></button>
      </div>
      <div className="border-b p-3 dark:border-gray-800">
        <label htmlFor="event-switcher" className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">{t("event")}</label>
        <select
          id="event-switcher"
          className="input w-full"
          value={eventId}
          onChange={(e) => navigate(`/events/${e.target.value}/dashboard`)}
        >
          {events?.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select>
        {event && <p className="mt-1 truncate text-xs text-gray-500">{event.venue || event.timezone}</p>}
      </div>
      <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4" aria-label={t("mainNavigation")}>
        {visibleNav.map(({ path, icon, label }) => {
          const Icon = ICONS[icon];
          return (
          <NavLink
            key={path}
            to={`/events/${eventId}/${path}`}
            onClick={() => setMenuOpen(false)}
            className={({ isActive }) => clsx(
              "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
              isActive ? "bg-primary-50 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300" : "text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
            )}
          ><Icon className="h-4 w-4" />{i18n.language === "en" ? label.en : label.de}</NavLink>
          );
        })}
      </nav>
      <div className="space-y-1 border-t p-3 dark:border-gray-800">
        <button onClick={() => push.isSubscribed ? push.unsubscribe.mutate() : push.subscribe.mutate()} className="sidebar-action">
          {push.isSubscribed ? <Bell className="h-4 w-4" /> : <BellOff className="h-4 w-4" />}{push.isSubscribed ? t("push.enabled") : t("push.enable")}
        </button>
        <button onClick={() => i18n.changeLanguage(i18n.language === "de" ? "en" : "de")} className="sidebar-action"><Globe className="h-4 w-4" />{i18n.language === "de" ? "Deutsch" : "English"}</button>
        <button onClick={nextTheme} className="sidebar-action"><ThemeIcon className="h-4 w-4" />{theme}</button>
        <button onClick={handleLogout} className="sidebar-action text-red-600"><LogOut className="h-4 w-4" />{t("logout")}</button>
        <div className="truncate px-3 pt-2 text-xs text-gray-500">{user?.display_name}</div>
      </div>
    </aside>
  );

  return (
    <div className="flex h-screen overflow-hidden bg-gray-50 dark:bg-gray-950">
      <div className="hidden md:block">{sidebar}</div>
      {menuOpen && <div className="fixed inset-0 z-40 md:hidden"><button aria-label={t("closeMenu")} className="absolute inset-0 bg-black/40" onClick={() => setMenuOpen(false)} /> <div className="relative h-full">{sidebar}</div></div>}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b bg-white px-4 dark:border-gray-800 dark:bg-gray-900 md:hidden">
          <button onClick={() => setMenuOpen(true)} aria-label={t("openMenu")}><Menu /></button><span className="truncate font-semibold">{event?.name}</span>
        </header>
        {!online && <div role="alert" className="bg-amber-100 px-4 py-2 text-center text-sm font-medium text-amber-900">{t("offlineReadOnly")}</div>}
        <main className="min-h-0 flex-1 overflow-y-auto"><Outlet /></main>
      </div>
    </div>
  );
}
