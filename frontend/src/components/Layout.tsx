import { Suspense, useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  CheckCircle2,
  CloudOff,
  LogOut,
  Menu,
  Monitor,
  Moon,
  Sun,
  UserRound,
  X,
} from "lucide-react";
import clsx from "clsx";
import { useAuthStore } from "@/store/authStore";
import { useThemeStore } from "@/store/themeStore";
import { useLogout } from "@/hooks/useAuth";
import { useOnlineStatus } from "@/hooks/useOnlineStatus";
import { useEvent, useEvents } from "@/hooks/useEvents";
import { isModuleEnabled, useEventModules } from "@/hooks/useEventModules";
import { useOfflineSync } from "@/hooks/useOfflineQueue";
import NotificationCenter from "@/components/NotificationCenter";
import ErrorBoundary from "@/components/ErrorBoundary";
import { LogoBadge, Wordmark } from "@/components/BrandMark";
import i18n, { localized } from "@/i18n/config";
import { NAV_GROUPS, navigationRoutes } from "@/core/plugins";
import { NAV_ICONS } from "@/core/navIcons";
import { api } from "@/lib/api";
import { APP_VERSION } from "@/lib/appInfo";

export default function Layout() {
  const { t } = useTranslation();
  const { eventId = "" } = useParams();
  const { user, hasPermission, setUser } = useAuthStore();
  const { theme, setTheme } = useThemeStore();
  const logout = useLogout();
  const navigate = useNavigate();
  const online = useOnlineStatus();
  const { data: events } = useEvents();
  const { data: event } = useEvent(eventId);
  const { data: modules } = useEventModules(eventId);
  // Queued offline scores are replayed on app start and on reconnect.
  const sync = useOfflineSync();
  const offlineSession = useAuthStore((state) => state.offlineSession);
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const drawerRef = useRef<HTMLDivElement>(null);

  // Mobile drawer: focus moves into it, Tab stays inside, Escape closes it and
  // focus returns to the menu button.
  useEffect(() => {
    if (!menuOpen) return;
    const drawer = drawerRef.current;
    drawer?.querySelector<HTMLElement>("button, a[href], select")?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuOpen(false);
        return;
      }
      if (event.key !== "Tab" || !drawer) return;
      const items = Array.from(drawer.querySelectorAll<HTMLElement>("button:not([disabled]), a[href], select:not([disabled])"));
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    const menuButton = menuButtonRef.current;
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      menuButton?.focus();
    };
  }, [menuOpen]);

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };
  const nextTheme = () => {
    const order = ["light", "dark", "system"] as const;
    setTheme(order[(order.indexOf(theme) + 1) % order.length]);
  };
  const language = i18n.resolvedLanguage === "en" ? "en" : "de";
  const toggleLanguage = () => {
    const next = language === "de" ? "en" : "de";
    i18n.changeLanguage(next);
    // Persist to the profile so the choice follows the user to other devices.
    if (user) {
      setUser({ ...user, preferred_language: next });
      api.patch("/auth/me", { preferred_language: next }).catch(() => undefined);
    }
  };
  const ThemeIcon = theme === "light" ? Sun : theme === "dark" ? Moon : Monitor;
  const visibleNav = navigationRoutes.filter(
    (item) => hasPermission(item.permission) && isModuleEnabled(modules, item.module),
  );
  const navGroups = NAV_GROUPS.map((group) => ({
    group,
    items: visibleNav.filter((item) => (item.group ?? "event") === group),
  })).filter((section) => section.items.length > 0);
  const roleName = user?.is_superuser
    ? t("layout.superuser")
    : user?.roles?.map((role) => role.name).join(", ");
  const profilePath = eventId ? `/events/${eventId}/profile` : "/profile";

  const syncChip = (sync.pending > 0 || sync.failed > 0) && (
    <span
      className={clsx(
        "badge max-w-full",
        sync.failed > 0 ? "border-danger/40 bg-danger/10 text-danger" : "border-warning/40 bg-warning/10 text-warning",
      )}
    >
      <CloudOff className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      <span className="truncate">
        {sync.failed > 0 ? t("syncFailed", { count: sync.failed }) : t("pendingSync", { count: sync.pending })}
      </span>
    </span>
  );

  const sidebar = (variant: "desktop" | "drawer") => (
    <aside className="flex h-full w-72 shrink-0 flex-col border-r border-white/5 bg-sidebar text-sidebar-text">
      <div className="flex items-center gap-3 px-4 pb-3 pt-5">
        <LogoBadge />
        <Wordmark onDark className="min-w-0 flex-1 truncate text-[1.2rem]" />
        {variant === "drawer" && (
          <button
            type="button"
            className="sidebar-toggle -mr-1 border-transparent"
            onClick={() => setMenuOpen(false)}
            aria-label={t("closeMenu")}
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        )}
      </div>
      <div className="px-3 pb-1">
        <label htmlFor={`event-switcher-${variant}`} className="sidebar-overline block pt-2">
          {t("event")}
        </label>
        <select
          id={`event-switcher-${variant}`}
          className="sidebar-select"
          value={eventId}
          onChange={(changeEvent) => navigate(`/events/${changeEvent.target.value}/dashboard`)}
        >
          {events?.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
        {event && (
          <p className="mt-1.5 truncate px-1 text-xs text-sidebar-leise">{event.venue || event.timezone}</p>
        )}
      </div>
      <nav className="flex-1 overflow-y-auto px-3 pb-4" aria-label={t("mainNavigation")}>
        {navGroups.map(({ group, items }) => {
          const headingId = `nav-group-${variant}-${group}`;
          return (
            <div key={group} role="group" aria-labelledby={headingId}>
              <p id={headingId} className="sidebar-overline">
                {t(`navGroup.${group}`)}
              </p>
              <ul className="space-y-0.5">
                {items.map(({ path, icon, label }) => {
                  const Icon = NAV_ICONS[icon];
                  const navigationPath = path.replace(/\/\*$/, "");
                  return (
                    <li key={path}>
                      <NavLink
                        to={eventId ? `/events/${eventId}/${navigationPath}` : `/${navigationPath}`}
                        onClick={() => setMenuOpen(false)}
                        className={({ isActive }) => clsx("sidebar-link", isActive && "sidebar-link-active")}
                      >
                        <Icon className="h-[1.15rem] w-[1.15rem] shrink-0" strokeWidth={1.75} aria-hidden="true" />
                        <span className="truncate">{localized(label)}</span>
                      </NavLink>
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </nav>
      <div className="space-y-3 border-t border-white/[0.07] px-3 pb-4 pt-3">
        {variant === "desktop" && syncChip}
        {user && (
          <NavLink
            to={profilePath}
            onClick={() => setMenuOpen(false)}
            className="flex min-h-9 items-center gap-1 truncate rounded-eng px-1 text-xs text-sidebar-leise hover:text-white"
          >
            <span className="truncate font-ui font-semibold text-white">{user.display_name}</span>
            {roleName && <span className="truncate">· {roleName}</span>}
          </NavLink>
        )}
        <div className="flex items-center gap-1.5">
          {variant === "desktop" && <NotificationCenter variant="sidebar" />}
          <button
            type="button"
            onClick={toggleLanguage}
            className="sidebar-toggle gap-0 overflow-hidden p-0"
            aria-label={t("changeLanguage")}
            title={t("languageName")}
          >
            <span className="flex h-full">
              {(["de", "en"] as const).map((code) => (
                <span
                  key={code}
                  className={clsx(
                    "grid min-w-10 place-items-center px-2",
                    code === language ? "bg-primary text-white" : "text-sidebar-text",
                  )}
                >
                  {code.toUpperCase()}
                </span>
              ))}
            </span>
          </button>
          <button
            type="button"
            onClick={nextTheme}
            className="sidebar-toggle"
            aria-label={t("changeTheme")}
            title={t(`theme.${theme}`)}
          >
            <ThemeIcon className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" />
          </button>
        </div>
        <div className="flex items-center justify-between gap-2">
          <span className="px-1 text-xs text-sidebar-leise">{t("layout.version", { version: APP_VERSION })}</span>
          <button
            type="button"
            onClick={handleLogout}
            className="inline-flex min-h-11 items-center gap-2 rounded-eng px-2 font-ui text-[0.95rem] font-semibold text-white hover:bg-white/[0.06]"
          >
            <LogOut className="h-4 w-4" aria-hidden="true" />
            {t("logout")}
          </button>
        </div>
      </div>
    </aside>
  );

  return (
    <div className="flex h-screen overflow-hidden">
      <div className="hidden md:block">{sidebar("desktop")}</div>
      {menuOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          {/* The backdrop is a mouse/touch target only; keyboard users close with Escape or the X button. */}
          <div aria-hidden="true" className="absolute inset-0 bg-tief/60 backdrop-blur-[2px]" onClick={() => setMenuOpen(false)} />
          <div
            ref={drawerRef}
            id="mobile-navigation"
            role="dialog"
            aria-modal="true"
            aria-label={t("mainNavigation")}
            className="relative h-full w-72 max-w-[85vw] shadow-tief"
          >
            {sidebar("drawer")}
          </div>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Phone top bar (mobil-startseite): menu, logo badge, status, bell, profile. */}
        <header className="flex h-16 shrink-0 items-center gap-1 border-b border-rand bg-flaeche px-2 md:hidden">
          <button
            ref={menuButtonRef}
            type="button"
            className="btn-icon border-transparent"
            onClick={() => setMenuOpen(true)}
            aria-label={t("openMenu")}
            aria-expanded={menuOpen}
            aria-controls="mobile-navigation"
          >
            <Menu className="h-6 w-6" strokeWidth={1.75} aria-hidden="true" />
          </button>
          <NavLink
            to={eventId ? `/events/${eventId}/dashboard` : "/"}
            className="flex min-w-0 flex-1 items-center gap-2 rounded-eng"
            aria-label={t("layout.home")}
          >
            <LogoBadge size="sm" />
            <span className="truncate font-ui text-sm font-semibold tracking-ui text-fg">{event?.name}</span>
          </NavLink>
          {online && !offlineSession ? (
            <span className="grid h-11 w-9 place-items-center text-success" title={t("layout.online")}>
              <CheckCircle2 className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" />
              <span className="sr-only">{t("layout.online")}</span>
            </span>
          ) : (
            <span className="grid h-11 w-9 place-items-center text-warning" title={t("layout.offline")}>
              <CloudOff className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" />
              <span className="sr-only">{t("layout.offline")}</span>
            </span>
          )}
          <NotificationCenter variant="header" />
          <NavLink to={profilePath} className="btn-icon border-transparent" aria-label={t("nav.profile")}>
            <UserRound className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" />
          </NavLink>
        </header>
        {(!online || offlineSession) && (
          <div
            role="alert"
            className="border-b border-warning/40 bg-warning/10 px-4 py-2 text-center text-sm font-medium text-warning"
          >
            {t("offlineReadOnly")}
          </div>
        )}
        {syncChip && <div className="border-b border-rand px-4 py-2 md:hidden">{syncChip}</div>}
        <main className="min-h-0 flex-1 overflow-y-auto">
          {/* A broken page keeps the navigation usable; switching pages clears the error. */}
          <ErrorBoundary resetKey={location.pathname}>
            <Suspense fallback={<div className="p-6 text-leise" role="status">{t("loadingEllipsis")}</div>}>
              <Outlet />
            </Suspense>
          </ErrorBoundary>
        </main>
      </div>
    </div>
  );
}
