import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { UserCircle, Save, KeyRound, Mail, Download, Trash2 } from "lucide-react";
import { api, restoreAccessToken } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import { useThemeStore, type Theme } from "@/store/themeStore";
import i18n from "@/i18n/config";
import { PASSWORD_HINT, apiErrorMessage, passwordProblem } from "@/lib/passwordPolicy";

function downloadJson(data: unknown, filename: string) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export default function ProfilePage() {
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

  const onErr = (e: any) => alert(apiErrorMessage(e, "Aktion fehlgeschlagen."));
  const newPwProblem = newPw ? passwordProblem(newPw, user?.email) : null;

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
      alert("Passwort geändert. Alle anderen Sitzungen wurden beendet.");
    },
    onError: onErr,
  });

  const emailM = useMutation({
    mutationFn: () => api.post("/auth/me/email", { new_email: newEmail, current_password: emailPw }),
    onSuccess: () => { setNewEmail(""); setEmailPw(""); qc.invalidateQueries({ queryKey: ["auth", "me"] }); alert("E-Mail-Adresse geändert."); },
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
        <UserCircle className="w-6 h-6" /> Mein Profil
      </h1>

      {/* Profile */}
      <section className="card p-6 space-y-4">
        <h2 className="font-semibold text-gray-900 dark:text-white">Profildaten</h2>
        <div>
          <label className="label" htmlFor="profile-email">E-Mail</label>
          <input id="profile-email" className="input bg-gray-50 dark:bg-gray-800" value={user?.email ?? ""} disabled />
        </div>
        <div>
          <label className="label" htmlFor="profile-name">Anzeigename</label>
          <input id="profile-name" className="input" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="flex flex-wrap gap-4">
          <div>
            <label className="label" htmlFor="profile-language">Sprache</label>
            <select id="profile-language" className="input w-48" value={lang} onChange={(e) => setLang(e.target.value)}>
              <option value="de">Deutsch</option>
              <option value="en">English</option>
            </select>
          </div>
          <div>
            <label className="label" htmlFor="profile-theme">Darstellung</label>
            <select id="profile-theme" className="input w-48" value={theme} onChange={(e) => setTheme(e.target.value as Theme)}>
              <option value="system">System</option>
              <option value="light">Hell</option>
              <option value="dark">Dunkel</option>
            </select>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button className="btn-primary text-sm disabled:opacity-40" disabled={!name || saveM.isPending} onClick={() => saveM.mutate()}>
            <Save className="w-4 h-4" /> Speichern
          </button>
          {saveM.isSuccess && <span className="text-sm text-green-600">Gespeichert</span>}
        </div>
      </section>

      {/* E-mail */}
      <section className="card p-6 space-y-4">
        <h2 className="font-semibold text-gray-900 dark:text-white flex items-center gap-2">
          <Mail className="w-4 h-4" /> E-Mail-Adresse ändern
        </h2>
        <div>
          <label className="label" htmlFor="new-email">Neue E-Mail-Adresse</label>
          <input id="new-email" className="input" type="email" value={newEmail} onChange={(e) => setNewEmail(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="email-password">Aktuelles Passwort</label>
          <input id="email-password" className="input" type="password" value={emailPw} onChange={(e) => setEmailPw(e.target.value)} />
        </div>
        <button className="btn-primary text-sm disabled:opacity-40" disabled={!newEmail || !emailPw || emailM.isPending} onClick={() => emailM.mutate()}>
          E-Mail ändern
        </button>
      </section>

      {/* Password */}
      <section className="card p-6 space-y-4">
        <h2 className="font-semibold text-gray-900 dark:text-white flex items-center gap-2">
          <KeyRound className="w-4 h-4" /> Passwort ändern
        </h2>
        <div>
          <label className="label" htmlFor="current-password">Aktuelles Passwort</label>
          <input id="current-password" className="input" type="password" value={currentPw} onChange={(e) => setCurrentPw(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="new-password">Neues Passwort</label>
          <input id="new-password" className="input" type="password" value={newPw} onChange={(e) => setNewPw(e.target.value)} />
          <p className={newPwProblem ? "mt-1 text-xs text-red-600" : "mt-1 text-xs text-gray-500"}>{newPwProblem ?? PASSWORD_HINT}</p>
        </div>
        <div>
          <button className="btn-primary text-sm disabled:opacity-40"
                  disabled={!currentPw || !newPw || !!newPwProblem || pwM.isPending}
                  onClick={() => pwM.mutate()}>
            Passwort ändern
          </button>
        </div>
      </section>

      {/* DSGVO */}
      <section className="card p-6 space-y-4">
        <h2 className="font-semibold text-gray-900 dark:text-white">Datenschutz</h2>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          Lade alle Daten herunter, die zu deinem Konto gespeichert sind, oder lösche dein Konto.
          Beim Löschen werden deine persönlichen Daten entfernt; erfasste Ergebnisse bleiben anonym erhalten.
        </p>
        <button className="btn-secondary text-sm" disabled={exportM.isPending} onClick={() => exportM.mutate()}>
          <Download className="w-4 h-4" /> Meine Daten exportieren
        </button>
        <div className="border-t pt-4 dark:border-gray-800 space-y-3">
          <label className="label" htmlFor="delete-password">Passwort zur Bestätigung</label>
          <input id="delete-password" className="input" type="password" value={deletePw} onChange={(e) => setDeletePw(e.target.value)} />
          <button className="btn-danger text-sm disabled:opacity-40" disabled={!deletePw || deleteM.isPending}
                  onClick={() => { if (confirm("Konto endgültig löschen? Das kann nicht rückgängig gemacht werden.")) deleteM.mutate(); }}>
            <Trash2 className="w-4 h-4" /> Konto löschen
          </button>
        </div>
      </section>
    </div>
  );
}
