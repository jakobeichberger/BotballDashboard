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

const NAV_ITEMS = [
  { path: "dashboard", icon: LayoutDashboard, label: "Dashboard", permission: "dashboard:read" },
  { path: "teams", icon: Users, label: "Teams", permission: "teams:read" },
  { path: "schedule", icon: CalendarDays, label: "Zeitplan", permission: "events:read" },
  { path: "scoring", icon: Trophy, label: "Wertung", permission: "scoring:read" },
  { path: "scans", icon: ScanLine, label: "OCR-Prüfung", permission: "scoring:read" },
  { path: "papers", icon: FileText, label: "Paper-Review", permission: "papers:read" },
  { path: "printing", icon: Printer, label: "3D-Druck", permission: "printing:read" },
];

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
  const visibleNav = NAV_ITEMS.filter((item) => hasPermission(item.permission));

  const sidebar = (
    <aside className="flex h-full w-72 shrink-0 flex-col border-r bg-white shadow-sm dark:border-gray-800 dark:bg-gray-900">
      <div className="flex h-16 items-center justify-between border-b px-5 dark:border-gray-800">
        <span className="font-bold text-primary-700 dark:text-primary-400">{t("app_name")}</span>
        <button className="md:hidden" onClick={() => setMenuOpen(false)} aria-label="Menü schließen"><X /></button>
      </div>
      <div className="border-b p-3 dark:border-gray-800">
        <label htmlFor="event-switcher" className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Event</label>
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
      <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4" aria-label="Hauptnavigation">
        {visibleNav.map(({ path, icon: Icon, label }) => (
          <NavLink
            key={path}
            to={`/events/${eventId}/${path}`}
            onClick={() => setMenuOpen(false)}
            className={({ isActive }) => clsx(
              "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
              isActive ? "bg-primary-50 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300" : "text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
            )}
          ><Icon className="h-4 w-4" />{label}</NavLink>
        ))}
        {hasPermission("events:write") && (
          <NavLink to={`/events/${eventId}/settings`} className={({ isActive }) => clsx("flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium", isActive ? "bg-primary-50 text-primary-700" : "text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800")}>
            <Settings className="h-4 w-4" />Event-Verwaltung
          </NavLink>
        )}
      </nav>
      <div className="space-y-1 border-t p-3 dark:border-gray-800">
        <button onClick={() => push.isSubscribed ? push.unsubscribe.mutate() : push.subscribe.mutate()} className="sidebar-action">
          {push.isSubscribed ? <Bell className="h-4 w-4" /> : <BellOff className="h-4 w-4" />}{push.isSubscribed ? "Push aktiv" : "Push aktivieren"}
        </button>
        <button onClick={() => i18n.changeLanguage(i18n.language === "de" ? "en" : "de")} className="sidebar-action"><Globe className="h-4 w-4" />{i18n.language === "de" ? "Deutsch" : "English"}</button>
        <button onClick={nextTheme} className="sidebar-action"><ThemeIcon className="h-4 w-4" />{theme}</button>
        <button onClick={handleLogout} className="sidebar-action text-red-600"><LogOut className="h-4 w-4" />Abmelden</button>
        <div className="truncate px-3 pt-2 text-xs text-gray-500">{user?.display_name}</div>
      </div>
    </aside>
  );

  return (
    <div className="flex h-screen overflow-hidden bg-gray-50 dark:bg-gray-950">
      <div className="hidden md:block">{sidebar}</div>
      {menuOpen && <div className="fixed inset-0 z-40 md:hidden"><button aria-label="Menü schließen" className="absolute inset-0 bg-black/40" onClick={() => setMenuOpen(false)} /> <div className="relative h-full">{sidebar}</div></div>}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b bg-white px-4 dark:border-gray-800 dark:bg-gray-900 md:hidden">
          <button onClick={() => setMenuOpen(true)} aria-label="Menü öffnen"><Menu /></button><span className="truncate font-semibold">{event?.name}</span>
        </header>
        {!online && <div role="alert" className="bg-amber-100 px-4 py-2 text-center text-sm font-medium text-amber-900">Keine Verbindung – Änderungen sind bis zur Wiederverbindung gesperrt.</div>}
        <main className="min-h-0 flex-1 overflow-y-auto"><Outlet /></main>
      </div>
    </div>
  );
}
