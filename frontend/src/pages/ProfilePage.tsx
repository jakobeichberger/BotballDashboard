import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { UserCircle, Save, KeyRound } from "lucide-react";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

export default function ProfilePage() {
  const qc = useQueryClient();
  const user = useAuthStore((s) => s.user);

  const [name, setName] = useState(user?.display_name ?? "");
  const [lang, setLang] = useState(user?.preferred_language ?? "de");

  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw] = useState("");

  const onErr = (e: any) => alert(e?.response?.data?.detail ?? "Aktion fehlgeschlagen.");

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
