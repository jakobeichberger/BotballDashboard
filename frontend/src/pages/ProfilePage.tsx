import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { UserCircle, Save, KeyRound, Bell } from "lucide-react";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import { usePushSubscription } from "@/hooks/usePushNotifications";

/** Push categories (backend: modules.dashboard.notifications.CATEGORIES). */
export type NotificationPreferences = Record<
  "match_soon" | "score_corrected" | "deadlines" | "paper_status" | "print_status" | "announcements",
  boolean
>;

const PREFERENCE_LABELS: Array<[keyof NotificationPreferences, string, string]> = [
  ["match_soon", "Match beginnt bald", "Aufruf und Zeitplanänderungen deiner Matches"],
  ["score_corrected", "Score korrigiert", "Wenn eine Wertung nachträglich geändert wird"],
  ["deadlines", "Deadlines & Erinnerungen", "Abgabefristen und Review-Erinnerungen"],
  ["paper_status", "Paper-Status", "Einreichung, Zuweisung und Entscheidungen zu Papers"],
  ["print_status", "Druckaufträge", "Genehmigt, gestartet, fertig oder fehlgeschlagen"],
  ["announcements", "Ankündigungen", "Veröffentlichte Ankündigungen der Organisation"],
];

export default function ProfilePage() {
  const qc = useQueryClient();
  const user = useAuthStore((s) => s.user);

  const [name, setName] = useState(user?.display_name ?? "");
  const [lang, setLang] = useState(user?.preferred_language ?? "de");

  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw] = useState("");

  const onErr = (e: any) => alert(e?.response?.data?.detail ?? "Aktion fehlgeschlagen.");

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
    mutationFn: () => api.patch("/auth/me", { display_name: name, preferred_language: lang }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["auth", "me"] }),
    onError: onErr,
  });

  const pwM = useMutation({
    mutationFn: () => api.post("/auth/me/password", { current_password: currentPw, new_password: newPw }),
    onSuccess: () => { setCurrentPw(""); setNewPw(""); alert("Passwort geändert."); },
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
          <label className="label">E-Mail</label>
          <input className="input bg-gray-50 dark:bg-gray-800" value={user?.email ?? ""} disabled />
        </div>
        <div>
          <label className="label">Anzeigename</label>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div>
          <label className="label">Sprache</label>
          <select className="input w-48" value={lang} onChange={(e) => setLang(e.target.value)}>
            <option value="de">Deutsch</option>
            <option value="en">English</option>
          </select>
        </div>
        <div className="flex items-center gap-3">
          <button className="btn-primary text-sm disabled:opacity-40" disabled={!name || saveM.isPending} onClick={() => saveM.mutate()}>
            <Save className="w-4 h-4" /> Speichern
          </button>
          {saveM.isSuccess && <span className="text-sm text-green-600">Gespeichert</span>}
        </div>
      </section>

      {/* Notifications */}
      <section className="card p-6 space-y-4" aria-labelledby="notification-settings">
        <h2 id="notification-settings" className="font-semibold text-gray-900 dark:text-white flex items-center gap-2">
          <Bell className="w-4 h-4" /> Benachrichtigungen
        </h2>
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-gray-50 p-3 text-sm dark:bg-gray-800">
          <span>
            Push auf diesem Gerät: <strong>{push.isSubscribed ? "aktiv" : "aus"}</strong>
          </span>
          <button
            type="button"
            className="btn-secondary text-sm"
            disabled={push.subscribe.isPending || push.unsubscribe.isPending}
            onClick={() => (push.isSubscribed ? push.unsubscribe.mutate() : push.subscribe.mutate(undefined, { onError: onErr }))}
          >
            {push.isSubscribed ? "Push deaktivieren" : "Push aktivieren"}
          </button>
        </div>
        <p className="text-sm text-gray-500">
          Welche Meldungen als Push kommen sollen. Alle Meldungen bleiben zusätzlich im Benachrichtigungscenter (Glocke oben) sichtbar.
        </p>
        <ul className="space-y-2">
          {PREFERENCE_LABELS.map(([key, label, hint]) => (
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
                  <span className="font-medium text-gray-900 dark:text-white">{label}</span>
                  <span className="block text-gray-500">{hint}</span>
                </span>
              </label>
            </li>
          ))}
        </ul>
      </section>

      {/* Password */}
      <section className="card p-6 space-y-4">
        <h2 className="font-semibold text-gray-900 dark:text-white flex items-center gap-2">
          <KeyRound className="w-4 h-4" /> Passwort ändern
        </h2>
        <div>
          <label className="label">Aktuelles Passwort</label>
          <input className="input" type="password" value={currentPw} onChange={(e) => setCurrentPw(e.target.value)} />
        </div>
        <div>
          <label className="label">Neues Passwort (min. 8)</label>
          <input className="input" type="password" value={newPw} onChange={(e) => setNewPw(e.target.value)} />
        </div>
        <div>
          <button className="btn-primary text-sm disabled:opacity-40"
                  disabled={!currentPw || newPw.length < 8 || pwM.isPending}
                  onClick={() => pwM.mutate()}>
            Passwort ändern
          </button>
        </div>
      </section>
    </div>
  );
}
