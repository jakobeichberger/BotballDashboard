import { Outlet, NavLink, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  LayoutDashboard,
  Users,
  Trophy,
  FileText,
  Printer,
  Settings,
  LogOut,
  Sun,
  Moon,
  Monitor,
  Globe,
} from "lucide-react";
import clsx from "clsx";
import { useAuthStore } from "@/store/authStore";
import { useThemeStore } from "@/store/themeStore";
import { useLogout } from "@/hooks/useAuth";
import i18n from "@/i18n/config";

const NAV_ITEMS = [
  { to: "/", icon: LayoutDashboard, labelKey: "nav.dashboard", roles: [] },
  { to: "/teams", icon: Users, labelKey: "nav.teams", roles: [] },
  { to: "/scoring", icon: Trophy, labelKey: "nav.scoring", roles: [] },
  { to: "/papers", icon: FileText, labelKey: "nav.papers", roles: [] },
  { to: "/printing", icon: Printer, labelKey: "nav.printing", roles: [] },
];

export default function Layout() {
  const { t } = useTranslation();
  const { user, hasRole } = useAuthStore();
  const { theme, setTheme } = useThemeStore();
  const logout = useLogout();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  const toggleLanguage = () => {
    i18n.changeLanguage(i18n.language === "de" ? "en" : "de");
  };

  const nextTheme = () => {
    const order: ("light" | "dark" | "system")[] = ["light", "dark", "system"];
    const idx = order.indexOf(theme as any);
    setTheme(order[(idx + 1) % order.length]);
  };

  const ThemeIcon = theme === "light" ? Sun : theme === "dark" ? Moon : Monitor;

  return (
    <div className="flex h-screen overflow-hidden bg-gray-50 dark:bg-gray-950">
      {/* Sidebar */}
      <aside className="w-64 flex flex-col bg-white dark:bg-gray-900 border-r shadow-sm shrink-0">
        {/* Logo */}
        <div className="h-16 flex items-center px-6 border-b">
          <span className="font-bold text-lg text-primary-700 dark:text-primary-400">
            {t("app_name")}
          </span>
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-1">
          {NAV_ITEMS.map(({ to, icon: Icon, labelKey }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                clsx(
                  "flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors",
                  isActive
                    ? "bg-primary-50 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300"
                    : "text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
                )
              }
            >
              <Icon className="w-4 h-4" />
              {t(labelKey)}
            </NavLink>
          ))}

          {(hasRole("admin") || user?.is_superuser) && (
            <>
              <div className="pt-4 pb-1 px-3">
                <span className="text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-600">
                  Admin
                </span>
              </div>
              <NavLink
                to="/settings/users"
                className={({ isActive }) =>
                  clsx(
                    "flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors",
                    isActive
                      ? "bg-primary-50 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300"
                      : "text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
                  )
                }
              >
                <Settings className="w-4 h-4" />
                {t("nav.settings")}
              </NavLink>
            </>
          )}
        </nav>

        {/* Footer */}
        <div className="border-t p-3 space-y-1">
          <button
            onClick={toggleLanguage}
            className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800"
          >
            <Globe className="w-4 h-4" />
            {i18n.language === "de" ? "Deutsch" : "English"}
          </button>
          <button
            onClick={nextTheme}
            className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800"
          >
            <ThemeIcon className="w-4 h-4" />
            {theme === "light" ? "Hell" : theme === "dark" ? "Dunkel" : "System"}
          </button>
          <button
            onClick={handleLogout}
            className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20"
          >
            <LogOut className="w-4 h-4" />
            Abmelden
          </button>
          {user && (
            <div className="px-3 py-2 text-xs text-gray-500 dark:text-gray-500 truncate">
              {user.display_name}
            </div>
          )}
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  );
}
