import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { UserCircle, Save, KeyRound, Mail, Download, Trash2, Bell } from "lucide-react";
import { api, restoreAccessToken } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import { useThemeStore, type Theme } from "@/store/themeStore";
import { usePushSubscription } from "@/hooks/usePushNotifications";
import i18n from "@/i18n/config";
import { passwordHint, passwordProblem } from "@/lib/passwordPolicy";
import { apiErrorMessage } from "@/lib/errors";

function downloadJson(data: unknown, filename: string) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

/** Push categories (backend: modules.dashboard.notifications.CATEGORIES). */
export type NotificationPreferences = Record<
  "match_soon" | "score_corrected" | "deadlines" | "paper_status" | "print_status" | "announcements",
  boolean
>;

const PREFERENCE_KEYS: Array<keyof NotificationPreferences> = [
  "match_soon",
  "score_corrected",
  "deadlines",
  "paper_status",
  "print_status",
  "announcements",
];

export default function ProfilePage() {
  const { t } = useTranslation("profile");
  const qc = useQueryClient();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const setAccessToken = useAuthStore((s) => s.setAccessToken);
  const logout = useAuthStore((s) => s.logout);
  const { theme, setTheme } = useThemeStore();

  const [name, setName] = useState(user?.display_name ?? "");
  const [lang, setLang] = useState(user?.preferred_language ?? "de");

  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw] = useState("");

  const [newEmail, setNewEmail] = useState("");
  const [emailPw, setEmailPw] = useState("");

  const [deletePw, setDeletePw] = useState("");

  const onErr = (e: any) => alert(apiErrorMessage(e, t("common:actionFailed")));
  const newPwProblem = newPw ? passwordProblem(newPw, user?.email) : null;

  const push = usePushSubscription();
  const prefs = useQuery<NotificationPreferences>({
    queryKey: ["notification-preferences"],
    queryFn: async () => (await api.get("/auth/me/notification-preferences")).data,
  });
  const prefsM = useMutation({
    mutationFn: async (patch: Partial<NotificationPreferences>) =>
      (await api.put("/auth/me/notification-preferences", patch)).data as NotificationPreferences,
    onSuccess: (data) => qc.setQueryData(["notification-preferences"], data),
    onError: onErr,
  });

  const saveM = useMutation({
    mutationFn: () => api.patch("/auth/me", { display_name: name, preferred_language: lang, theme }),
    onSuccess: () => { i18n.changeLanguage(lang); qc.invalidateQueries({ queryKey: ["auth", "me"] }); },
    onError: onErr,
  });

  const pwM = useMutation({
    mutationFn: () => api.post("/auth/me/password", { current_password: currentPw, new_password: newPw }),
    onSuccess: async () => {
      setCurrentPw(""); setNewPw("");
      // The change revoked every access token, this one included; the new
      // refresh cookie of this device yields a fresh one.
      const token = await restoreAccessToken();
      if (token) setAccessToken(token);
      alert(t("passwordChanged"));
    },
    onError: onErr,
  });

  const emailM = useMutation({
    mutationFn: () => api.post("/auth/me/email", { new_email: newEmail, current_password: emailPw }),
    onSuccess: () => { setNewEmail(""); setEmailPw(""); qc.invalidateQueries({ queryKey: ["auth", "me"] }); alert(t("emailChanged")); },
    onError: onErr,
  });

  const exportM = useMutation({
    mutationFn: async () => (await api.get("/auth/me/export")).data,
    onSuccess: (data) => downloadJson(data, "meine-botball-daten.json"),
    onError: onErr,
  });

  const deleteM = useMutation({
    mutationFn: () => api.delete("/auth/me", { data: { current_password: deletePw } }),
    onSuccess: () => { logout(); navigate("/login"); },
    onError: onErr,
  });

  return (
    <div className="p-6 max-w-2xl space-y-6">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
        <UserCircle className="w-6 h-6" /> {t("title")}
      </h1>

      {/* Profile */}
      <section className="card p-6 space-y-4">
        <h2 className="font-semibold text-gray-900 dark:text-white">{t("data")}</h2>
        <div>
          <label className="label" htmlFor="profile-email">{t("common:email")}</label>
          <input id="profile-email" className="input bg-gray-50 dark:bg-gray-800" value={user?.email ?? ""} disabled />
        </div>
        <div>
          <label className="label" htmlFor="profile-name">{t("displayName")}</label>
          <input id="profile-name" className="input" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="flex flex-wrap gap-4">
          <div>
            <label className="label" htmlFor="profile-language">{t("language")}</label>
            <select id="profile-language" className="input w-48" value={lang} onChange={(e) => setLang(e.target.value)}>
              <option value="de">Deutsch</option>
              <option value="en">English</option>
            </select>
          </div>
          <div>
            <label className="label" htmlFor="profile-theme">{t("theme")}</label>
            <select id="profile-theme" className="input w-48" value={theme} onChange={(e) => setTheme(e.target.value as Theme)}>
              <option value="system">{t("common:theme.system")}</option>
              <option value="light">{t("common:theme.light")}</option>
              <option value="dark">{t("common:theme.dark")}</option>
            </select>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button className="btn-primary text-sm disabled:opacity-40" disabled={!name || saveM.isPending} onClick={() => saveM.mutate()}>
            <Save className="w-4 h-4" /> {t("common:save")}
          </button>
          {saveM.isSuccess && <span className="text-sm text-green-600">{t("saved")}</span>}
        </div>
      </section>

      {/* E-mail */}
      <section className="card p-6 space-y-4">
        <h2 className="font-semibold text-gray-900 dark:text-white flex items-center gap-2">
          <Mail className="w-4 h-4" /> {t("changeEmail")}
        </h2>
        <div>
          <label className="label" htmlFor="new-email">{t("newEmail")}</label>
          <input id="new-email" className="input" type="email" value={newEmail} onChange={(e) => setNewEmail(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="email-password">{t("currentPassword")}</label>
          <input id="email-password" className="input" type="password" value={emailPw} onChange={(e) => setEmailPw(e.target.value)} />
        </div>
        <button className="btn-primary text-sm disabled:opacity-40" disabled={!newEmail || !emailPw || emailM.isPending} onClick={() => emailM.mutate()}>
          {t("changeEmailButton")}
        </button>
      </section>

      {/* Notifications */}
      <section className="card p-6 space-y-4" aria-labelledby="notification-settings">
        <h2 id="notification-settings" className="font-semibold text-gray-900 dark:text-white flex items-center gap-2">
          <Bell className="w-4 h-4" /> {t("notifications")}
        </h2>
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-gray-50 p-3 text-sm dark:bg-gray-800">
          <span>
            {t("pushOnDevice")} <strong>{push.isSubscribed ? t("pushOn") : t("pushOff")}</strong>
          </span>
          <button
            type="button"
            className="btn-secondary text-sm"
            disabled={push.subscribe.isPending || push.unsubscribe.isPending}
            onClick={() => (push.isSubscribed ? push.unsubscribe.mutate() : push.subscribe.mutate(undefined, { onError: onErr }))}
          >
            {push.isSubscribed ? t("pushDisable") : t("common:push.enable")}
          </button>
        </div>
        <p className="text-sm text-gray-500">
          {t("pushHint")}
        </p>
        <ul className="space-y-2">
          {PREFERENCE_KEYS.map((key) => (
            <li key={key}>
              <label className="flex items-start gap-3 text-sm">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={prefs.data?.[key] ?? true}
                  disabled={!prefs.data || prefsM.isPending}
                  onChange={(e) => prefsM.mutate({ [key]: e.target.checked })}
                />
                <span>
                  <span className="font-medium text-gray-900 dark:text-white">{t(`preference.${key}.label`)}</span>
                  <span className="block text-gray-500">{t(`preference.${key}.hint`)}</span>
                </span>
              </label>
            </li>
          ))}
        </ul>
      </section>

      {/* Password */}
      <section className="card p-6 space-y-4">
        <h2 className="font-semibold text-gray-900 dark:text-white flex items-center gap-2">
          <KeyRound className="w-4 h-4" /> {t("changePassword")}
        </h2>
        <div>
          <label className="label" htmlFor="current-password">{t("currentPassword")}</label>
          <input id="current-password" className="input" type="password" value={currentPw} onChange={(e) => setCurrentPw(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="new-password">{t("auth:reset.newPassword")}</label>
          <input id="new-password" className="input" type="password" value={newPw} onChange={(e) => setNewPw(e.target.value)} />
          <p className={newPwProblem ? "mt-1 text-xs text-red-600" : "mt-1 text-xs text-gray-500"}>{newPwProblem ?? passwordHint()}</p>
        </div>
        <div>
          <button className="btn-primary text-sm disabled:opacity-40"
                  disabled={!currentPw || !newPw || !!newPwProblem || pwM.isPending}
                  onClick={() => pwM.mutate()}>
            {t("changePassword")}
          </button>
        </div>
      </section>

      {/* DSGVO */}
      <section className="card p-6 space-y-4">
        <h2 className="font-semibold text-gray-900 dark:text-white">{t("privacy")}</h2>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          {t("privacyHint")}
        </p>
        <button className="btn-secondary text-sm" disabled={exportM.isPending} onClick={() => exportM.mutate()}>
          <Download className="w-4 h-4" /> {t("export")}
        </button>
        <div className="border-t pt-4 dark:border-gray-800 space-y-3">
          <label className="label" htmlFor="delete-password">{t("confirmPassword")}</label>
          <input id="delete-password" className="input" type="password" value={deletePw} onChange={(e) => setDeletePw(e.target.value)} />
          <button className="btn-danger text-sm disabled:opacity-40" disabled={!deletePw || deleteM.isPending}
                  onClick={() => { if (confirm(t("confirmDelete"))) deleteM.mutate(); }}>
            <Trash2 className="w-4 h-4" /> {t("deleteAccount")}
          </button>
        </div>
      </section>
    </div>
  );
}
